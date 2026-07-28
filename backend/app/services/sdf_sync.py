"""
SDF 数据库同步服务 - 基于 file_hash 的增量同步，分批提交避免大事务
"""
import logging
from sqlalchemy.orm import Session
from sqlalchemy import select, delete
from app.repositories.models import SDFMolecule
from app.services.sdf_parser import parse_sdf_file, scan_sdf_directory

logger = logging.getLogger(__name__)

BATCH_COMMIT_SIZE = 100


class SyncResult:
    def __init__(self):
        self.total_files: int = 0
        self.new_files: int = 0
        self.updated_files: int = 0
        self.unchanged_files: int = 0
        self.deleted_records: int = 0
        self.total_conformers_added: int = 0
        self.errors: list[dict] = []
        self.files_processed: list[str] = []

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


def _get_existing_state(db: Session) -> tuple[dict[str, str], set[str]]:
    """一次查询返回 (file_path→file_hash 映射, hash 集合)。"""
    rows = db.execute(
        select(SDFMolecule.sdf_file_path, SDFMolecule.sdf_file_hash).distinct()
    ).all()
    paths = {r[0]: r[1] for r in rows}
    return paths, set(paths.values())


def _delete_by_hash(db: Session, file_hash: str) -> int:
    """按 hash 删除所有相关记录，返回删除数量。"""
    result = db.execute(
        delete(SDFMolecule).where(SDFMolecule.sdf_file_hash == file_hash)
    )
    return result.rowcount


def _delete_by_path(db: Session, file_path: str) -> int:
    """按 file_path 删除所有相关记录。"""
    result = db.execute(
        delete(SDFMolecule).where(SDFMolecule.sdf_file_path == file_path)
    )
    return result.rowcount


def _delete_orphans(db: Session, orphan_hashes: set[str], result: SyncResult) -> SyncResult:
    """批量删除 orphan 记录（单条 DELETE … WHERE hash IN (…) + 一次 commit）。"""
    batch_result = db.execute(
        delete(SDFMolecule).where(SDFMolecule.sdf_file_hash.in_(orphan_hashes))
    )
    result.deleted_records = batch_result.rowcount
    db.commit()
    return result


def _insert_molecules(db: Session, file_info: dict, parsed_mols: list, result: SyncResult):
    """解析并插入分子，每 BATCH_COMMIT_SIZE 个 conformer 提交一次。"""
    total_conformers = len(parsed_mols)
    batch_count = 0
    for idx, mol_data in enumerate(parsed_mols):
        if mol_data.error:
            result.errors.append({"file": file_info["filename"], "conformer": idx, "error": mol_data.error})
            continue
        db_mol = SDFMolecule(
            sdf_filename=file_info["filename"],
            sdf_file_path=file_info["file_path"],
            sdf_file_hash=file_info["file_hash"],
            file_size_bytes=file_info["file_size_bytes"],
            conformer_index=idx,
            total_conformers=total_conformers,
            name=mol_data.name, smiles=mol_data.smiles,
            inchi=mol_data.inchi, inchikey=mol_data.inchikey,
            molecular_formula=mol_data.molecular_formula,
            molecular_weight=mol_data.molecular_weight,
            num_atoms=mol_data.num_atoms, num_heavy_atoms=mol_data.num_heavy_atoms,
            num_rotatable_bonds=mol_data.num_rotatable_bonds,
            num_h_bond_donors=mol_data.num_h_bond_donors,
            num_h_bond_acceptors=mol_data.num_h_bond_acceptors,
            logp=mol_data.logp, tpsa=mol_data.tpsa, qed=mol_data.qed,
            sa_score=mol_data.sa_score,
            sdf_properties=mol_data.sdf_properties,
        )
        db.add(db_mol)
        result.total_conformers_added += 1
        batch_count += 1
        if batch_count >= BATCH_COMMIT_SIZE:
            db.commit()
            batch_count = 0
    if batch_count > 0:
        db.commit()


def sync_sdf_library(db: Session, sdf_dir: str) -> SyncResult:
    result = SyncResult()
    sdf_files = scan_sdf_directory(sdf_dir)
    result.total_files = len(sdf_files)
    if not sdf_files:
        logger.info("SDF 文件夹中没有找到 .sdf 文件")
        return result

    existing_paths, existing_hashes = _get_existing_state(db)
    current_hashes = {f["file_hash"] for f in sdf_files}

    for file_info in sdf_files:
        fhash = file_info["file_hash"]
        file_path = file_info["file_path"]
        filename = file_info["filename"]

        try:
            if fhash in existing_hashes:
                # hash 匹配 → 文件未变化，跳过
                result.unchanged_files += 1
                result.files_processed.append(f"{filename} (unchanged)")
            elif file_path in existing_paths:
                # 同路径但 hash 不同 → 文件已修改，删除旧记录重新解析
                old_hash = existing_paths[file_path]
                deleted = _delete_by_hash(db, old_hash)
                result.updated_files += 1
                logger.info(f"SDF 文件已更新：{filename}（删除 {deleted} 条旧记录）")
                parsed_mols = parse_sdf_file(file_path)
                if not parsed_mols:
                    result.errors.append({"file": filename, "error": "无法解析任何有效分子"})
                    continue
                _insert_molecules(db, file_info, parsed_mols, result)
                result.files_processed.append(f"{filename} (updated, {len(parsed_mols)} conformers)")
            else:
                # 全新文件
                result.new_files += 1
                parsed_mols = parse_sdf_file(file_path)
                if not parsed_mols:
                    result.errors.append({"file": filename, "error": "无法解析任何有效分子"})
                    continue
                _insert_molecules(db, file_info, parsed_mols, result)
                result.files_processed.append(f"{filename} (new, {len(parsed_mols)} conformers)")
        except Exception as e:
            logger.error(f"处理文件 {filename} 时出错：{e}")
            result.errors.append({"file": filename, "error": str(e)})

    # 清理 orphan 记录：文件已删除但 hash 仍在 db 中
    orphan_hashes = existing_hashes - current_hashes
    if orphan_hashes:
        result = _delete_orphans(db, orphan_hashes, result)
        logger.info(f"清理 {len(orphan_hashes)} 个 orphan 文件组，共 {result.deleted_records} 条记录")

    logger.info(
        f"SDF 同步完成：{result.total_files} 文件，{result.new_files} 新增，"
        f"{result.total_conformers_added} 构象添加，{result.deleted_records} 记录清理"
    )
    return result


def get_sdf_molecule_count(db: Session) -> int:
    return db.query(SDFMolecule).count()


def get_sdf_file_count(db: Session) -> int:
    return db.query(SDFMolecule.sdf_file_hash).distinct().count()
