"""
SDF 数据库同步服务 - 自动检测 SDF 文件夹变化，解析并同步到 PostgreSQL
"""
import os
import logging
from sqlalchemy.orm import Session
from app.repositories.models import SDFMolecule
from app.services.sdf_parser import parse_sdf_file, scan_sdf_directory

logger = logging.getLogger(__name__)


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


def sync_sdf_library(db: Session, sdf_dir: str) -> SyncResult:
    result = SyncResult()
    sdf_files = scan_sdf_directory(sdf_dir)
    result.total_files = len(sdf_files)
    if not sdf_files:
        logger.info("SDF 文件夹中没有找到 .sdf 文件")
        return result
    current_hashes = {f["file_hash"] for f in sdf_files}
    existing_records = db.query(SDFMolecule).all()
    existing_by_hash: dict[str, list[SDFMolecule]] = {}
    for rec in existing_records:
        existing_by_hash.setdefault(rec.sdf_file_hash, []).append(rec)
    for file_info in sdf_files:
        fhash = file_info["file_hash"]
        file_path = file_info["file_path"]
        filename = file_info["filename"]
        try:
            if fhash in existing_by_hash:
                result.unchanged_files += 1
                for rec in existing_by_hash[fhash]:
                    if rec.sdf_file_path != file_path:
                        rec.sdf_file_path = file_path
                        rec.sdf_filename = filename
                        rec.file_size_bytes = file_info["file_size_bytes"]
                        result.updated_files += 1
                label = "unchanged" if result.updated_files == 0 else "updated path"
                result.files_processed.append(f"{filename} ({label})")
            else:
                logger.info(f"发现新 SDF 文件：{filename}")
                result.new_files += 1
                parsed_mols = parse_sdf_file(file_path)
                if not parsed_mols:
                    result.errors.append({"file": filename, "error": "无法解析任何有效分子"})
                    continue
                total_conformers = len(parsed_mols)
                for idx, mol_data in enumerate(parsed_mols):
                    if mol_data.error:
                        result.errors.append({"file": filename, "conformer": idx, "error": mol_data.error})
                        continue
                    db_mol = SDFMolecule(
                        sdf_filename=filename, sdf_file_path=file_path,
                        sdf_file_hash=fhash, file_size_bytes=file_info["file_size_bytes"],
                        conformer_index=idx, total_conformers=total_conformers,
                        name=mol_data.name, smiles=mol_data.smiles,
                        inchi=mol_data.inchi, inchikey=mol_data.inchikey,
                        molecular_formula=mol_data.molecular_formula,
                        molecular_weight=mol_data.molecular_weight,
                        num_atoms=mol_data.num_atoms, num_heavy_atoms=mol_data.num_heavy_atoms,
                        num_rotatable_bonds=mol_data.num_rotatable_bonds,
                        num_h_bond_donors=mol_data.num_h_bond_donors,
                        num_h_bond_acceptors=mol_data.num_h_bond_acceptors,
                        logp=mol_data.logp, tpsa=mol_data.tpsa, qed=mol_data.qed,
                        sdf_properties=mol_data.sdf_properties,
                    )
                    db.add(db_mol)
                    result.total_conformers_added += 1
                result.files_processed.append(f"{filename} (new, {total_conformers} conformers)")
        except Exception as e:
            logger.error(f"处理文件 {filename} 时出错：{e}")
            result.errors.append({"file": filename, "error": str(e)})
    orphan_hashes = set(existing_by_hash.keys()) - current_hashes
    for orphan_hash in orphan_hashes:
        deleted = db.query(SDFMolecule).filter(SDFMolecule.sdf_file_hash == orphan_hash).delete(synchronize_session=False)
        result.deleted_records += deleted
        if orphan_hash in existing_by_hash:
            fname = existing_by_hash[orphan_hash][0].sdf_filename
            result.files_processed.append(f"{fname} (removed - file deleted)")
    try:
        db.commit()
        logger.info(f"SDF 同步完成：{result.total_files} 文件，{result.new_files} 新增，{result.total_conformers_added} 构象添加，{result.deleted_records} 记录清理")
    except Exception as e:
        db.rollback()
        logger.error(f"SDF 同步数据库提交失败：{e}")
        raise
    return result


def get_sdf_molecule_count(db: Session) -> int:
    return db.query(SDFMolecule).count()


def get_sdf_file_count(db: Session) -> int:
    return db.query(SDFMolecule.sdf_file_hash).distinct().count()
