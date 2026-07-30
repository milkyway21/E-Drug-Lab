"""
SDF 分子文件解析器 - 使用 RDKit 解析 SDF 文件，提取分子结构和理化属性
"""
import os
import hashlib
import logging
from typing import Optional
from rdkit import Chem
from rdkit.Chem import AllChem, Descriptors, Lipinski, QED, rdMolDescriptors
from app.services.sa_score import compute_sa_score

logger = logging.getLogger(__name__)


class SDFParseResult:
    def __init__(self):
        self.name: Optional[str] = None
        self.smiles: Optional[str] = None
        self.inchi: Optional[str] = None
        self.inchikey: Optional[str] = None
        self.molecular_formula: Optional[str] = None
        self.molecular_weight: Optional[float] = None
        self.num_atoms: int = 0
        self.num_heavy_atoms: int = 0
        self.num_rotatable_bonds: int = 0
        self.num_h_bond_donors: int = 0
        self.num_h_bond_acceptors: int = 0
        self.logp: Optional[float] = None
        self.tpsa: Optional[float] = None
        self.qed: Optional[float] = None
        self.sa_score: Optional[float] = None
        self.sdf_properties: dict = {}
        self.warnings: list[str] = []
        self.error: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


def parse_sdf_file(file_path: str) -> list[SDFParseResult]:
    results = []
    if not os.path.exists(file_path):
        logger.warning(f"SDF 文件不存在：{file_path}")
        return results
    try:
        supplier = Chem.SDMolSupplier(file_path, removeHs=False)
        conformers = [mol for mol in supplier if mol is not None]
        if not conformers:
            logger.warning(f"SDF 文件中未读取到有效分子：{file_path}")
            return results
        for idx, mol in enumerate(conformers):
            result = SDFParseResult()
            try:
                mol_name = mol.GetProp('_Name') if mol.HasProp('_Name') else f"Molecule_{idx+1}"
                if not mol_name.strip() or mol_name == f"Molecule_{idx+1}":
                    for name_key in ['PUBCHEM_COMPOUND_CID', 'DRUGBANK_ID', 'ZINC_ID', 'ID', 'NAME']:
                        if mol.HasProp(name_key):
                            mol_name = mol.GetProp(name_key)
                            break
                result.name = mol_name
                try:
                    Chem.AssignStereochemistry(mol, cleanIt=True, force=True)
                except Exception:
                    pass
                try:
                    mol_no_h = Chem.RemoveHs(mol)
                    result.smiles = Chem.MolToSmiles(mol_no_h, canonical=True)
                    result.inchi = Chem.MolToInchi(mol_no_h)
                    result.inchikey = Chem.MolToInchiKey(mol_no_h)
                    result.molecular_formula = rdMolDescriptors.CalcMolFormula(mol_no_h)
                except Exception as e:
                    result.warnings.append(f"SMILES/InChI 生成失败：{e}")
                    result.smiles = Chem.MolToSmiles(mol, canonical=True)
                try:
                    result.molecular_weight = Descriptors.ExactMolWt(mol)
                except Exception:
                    result.molecular_weight = Descriptors.MolWt(mol)
                result.num_atoms = mol.GetNumAtoms()
                result.num_heavy_atoms = Lipinski.HeavyAtomCount(mol)
                result.num_rotatable_bonds = Lipinski.NumRotatableBonds(mol)
                result.num_h_bond_donors = Lipinski.NumHDonors(mol)
                result.num_h_bond_acceptors = Lipinski.NumHAcceptors(mol)
                try:
                    result.logp = Descriptors.MolLogP(mol)
                except Exception:
                    result.warnings.append("LogP 计算失败")
                try:
                    result.tpsa = Descriptors.TPSA(mol)
                except Exception:
                    result.warnings.append("TPSA 计算失败")
                try:
                    result.qed = QED.qed(mol)
                except Exception:
                    result.warnings.append("QED 计算失败")
                try:
                    result.sa_score = compute_sa_score(mol)
                except Exception:
                    result.warnings.append("SA Score 计算失败")
                prop_names = list(mol.GetPropNames())
                sdf_props = {}
                for prop_name in prop_names:
                    if prop_name != '_Name':
                        try:
                            val = mol.GetProp(prop_name)
                            try:
                                val = float(val)
                                if val == int(val):
                                    val = int(val)
                            except (ValueError, TypeError):
                                pass
                            sdf_props[prop_name] = val
                        except Exception:
                            pass
                result.sdf_properties = sdf_props
            except Exception as e:
                result.error = f"解析构象 {idx} 时出错：{e}"
                logger.error(f"解析 {file_path} 第 {idx} 个构象失败：{e}")
            results.append(result)
    except Exception as e:
        logger.error(f"无法打开/读取 SDF 文件 {file_path}：{e}")
        result = SDFParseResult()
        result.error = f"文件读取失败：{e}"
        results.append(result)
    return results


def compute_file_hash(file_path: str) -> str:
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


def scan_sdf_directory(sdf_dir: str) -> list[dict]:
    files_info = []
    if not os.path.isdir(sdf_dir):
        logger.warning(f"SDF 目录不存在：{sdf_dir}")
        return files_info
    for root, dirs, files in os.walk(sdf_dir):
        for fname in files:
            if fname.lower().endswith('.sdf'):
                full_path = os.path.abspath(os.path.join(root, fname))
                try:
                    fhash = compute_file_hash(full_path)
                    fsize = os.path.getsize(full_path)
                    files_info.append({"filename": fname, "file_path": full_path, "file_hash": fhash, "file_size_bytes": fsize})
                except Exception as e:
                    logger.error(f"无法读取文件 {full_path}：{e}")
    return files_info
