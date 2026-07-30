"""
AutoDock Vina 1.2.x 对接服务
支持：
  - 受体/配体文件准备
  - 配置文件生成（config.txt）
  - Vina 命令行调用
  - 输出解析（affinity + rmsd）
"""
import asyncio
import logging
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from app.services.tool_manager import ToolManager

logger = logging.getLogger(__name__)


# ── 数据结构 ──────────────────────────────────────────────

@dataclass
class VinaBox:
    """对接口袋定义（center + size）"""
    center_x: float
    center_y: float
    center_z: float
    size_x: float = 20.0
    size_y: float = 20.0
    size_z: float = 20.0

    def to_config_lines(self) -> list[str]:
        return [
            f"center_x = {self.center_x}",
            f"center_y = {self.center_y}",
            f"center_z = {self.center_z}",
            f"size_x = {self.size_x}",
            f"size_y = {self.size_y}",
            f"size_z = {self.size_z}",
        ]


@dataclass
class VinaParams:
    """Vina 对接参数"""
    receptor_path: str                    # 受体 PDBQT 文件路径
    ligand_path: str                      # 配体 PDBQT 文件路径
    box: VinaBox                          # 对接口袋
    exhaustiveness: int = 8               # 搜索穷尽度（默认 8）
    num_modes: int = 10                   # 输出构象数
    energy_range: float = 3.0             # 能量范围 (kcal/mol)
    cpu: int = 0                          # CPU 核心数（0 = 全部）
    seed: int = 0                         # 随机种子（0 = 随机）
    spacing: float = 1.0                  # 格点间距 (Å)
    verbosity: int = 1                    # 输出详细度


@dataclass
class VinaPose:
    """单个对接构象结果"""
    mode: int
    affinity: float          # kcal/mol, 越低越好
    rmsd_lb: float           # RMSD lower bound
    rmsd_ub: float           # RMSD upper bound


@dataclass
class VinaResult:
    """Vina 对接完整结果"""
    receptor_path: str
    ligand_path: str
    output_pdbqt_path: Optional[str] = None
    poses: list[VinaPose] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    return_code: int = -1
    success: bool = False
    best_affinity: Optional[float] = None
    command: list[str] = field(default_factory=list)


# ── Vina 输出解析 ──────────────────────────────────────────

# Vina 输出格式示例：
# -----+------------+----------+----------
#    1         -8.1      0.000      0.000
#    2         -7.9      1.234      2.345
_MODE_RE = re.compile(
    r"^\s*(\d+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s*$"
)
_AFFINITY_HEADER_RE = re.compile(r"^\s*\d+\s+[-\d.]+\s+[-\d.]+\s+[-\d.]+\s*$")


def parse_vina_output(stdout: str) -> list[VinaPose]:
    """解析 Vina stdout 中的对接结果表格"""
    poses: list[VinaPose] = []
    in_table = False
    for line in stdout.splitlines():
        # 表头分隔线之后开始解析
        if "-----+------------" in line:
            in_table = True
            continue
        if in_table:
            m = _MODE_RE.match(line)
            if m:
                poses.append(VinaPose(
                    mode=int(m.group(1)),
                    affinity=float(m.group(2)),
                    rmsd_lb=float(m.group(3)),
                    rmsd_ub=float(m.group(4)),
                ))
            elif line.strip() == "":
                # 空行结束表格
                continue
    return poses


# ── 配置文件生成 ────────────────────────────────────────────

def generate_vina_config(
    receptor_path: str,
    ligand_path: str,
    out_path: str,
    box: VinaBox,
    params: VinaParams,
    output_path: Optional[str] = None,
) -> str:
    """生成 Vina 配置文件（config.txt）并返回路径"""
    lines = [
        f"receptor = {receptor_path}",
        f"ligand = {ligand_path}",
        "",
        *box.to_config_lines(),
        "",
        f"exhaustiveness = {params.exhaustiveness}",
        f"num_modes = {params.num_modes}",
        f"energy_range = {params.energy_range}",
    ]
    if params.spacing != 1.0:
        lines.append(f"spacing = {params.spacing}")
    if params.cpu > 0:
        lines.append(f"cpu = {params.cpu}")
    if params.seed > 0:
        lines.append(f"seed = {params.seed}")
    if output_path:
        lines.append(f"out = {output_path}")
    lines.append(f"verbosity = {params.verbosity}")

    content = "\n".join(lines) + "\n"
    config_path = Path(out_path)
    config_path.write_text(content, encoding="utf-8")
    logger.info(f"Vina config written to {config_path}")
    return str(config_path)


# ── 服务类 ──────────────────────────────────────────────────

class VinaService:
    """AutoDock Vina 1.2.x 对接服务"""

    def __init__(self, tool_manager: ToolManager, work_dir: Optional[str] = None):
        self.tool_manager = tool_manager
        self.work_dir = work_dir or os.path.join(tempfile.gettempdir(), "vina_docking")
        os.makedirs(self.work_dir, exist_ok=True)

    def _ensure_work_dir(self, subdir: str = "") -> str:
        path = os.path.join(self.work_dir, subdir) if subdir else self.work_dir
        os.makedirs(path, exist_ok=True)
        return path

    def _build_args(self, config_path: str) -> list[str]:
        """构建 Vina 命令行参数"""
        return ["--config", config_path]

    async def run_docking(
        self,
        params: VinaParams,
        job_id: str = "default",
        timeout: int = 1800,
    ) -> VinaResult:
        """
        执行 Vina 对接任务
        1. 生成 config 文件
        2. 调用 vina 可执行文件
        3. 解析输出
        """
        job_dir = self._ensure_work_dir(job_id)
        job_dir = os.path.abspath(job_dir)

        # 确定输出路径
        output_pdbqt = os.path.join(job_dir, "docking_out.pdbqt")
        config_path = os.path.join(job_dir, "config.txt")
        log_path = os.path.join(job_dir, "docking.log")

        # 生成配置文件（全部使用绝对路径，避免 cwd 影响）
        generate_vina_config(
            receptor_path=os.path.abspath(params.receptor_path),
            ligand_path=os.path.abspath(params.ligand_path),
            out_path=config_path,
            box=params.box,
            params=params,
            output_path=output_pdbqt,
        )

        # cwd=job_dir 时仅传 config 文件名
        args = self._build_args("config.txt")

        result = VinaResult(
            receptor_path=params.receptor_path,
            ligand_path=params.ligand_path,
            output_pdbqt_path=output_pdbqt,
            command=["vina"] + args,
        )

        try:
            logger.info(f"Running Vina docking: {' '.join(result.command)}")
            proc = await self.tool_manager.async_execute(
                "autodock_vina",
                args,
                timeout=timeout,
                cwd=job_dir,
            )
            result.return_code = proc.returncode
            result.stdout = proc.stdout
            result.stderr = proc.stderr

            # 保存日志文件
            try:
                Path(log_path).write_text(proc.stdout or "", encoding="utf-8")
            except Exception:
                pass

            if proc.returncode == 0:
                result.success = True
                result.poses = parse_vina_output(proc.stdout)
                if result.poses:
                    result.best_affinity = min(p.affinity for p in result.poses)
                logger.info(
                    f"Vina docking completed: {len(result.poses)} poses, "
                    f"best affinity = {result.best_affinity} kcal/mol"
                )
            else:
                logger.error(f"Vina failed (rc={proc.returncode}): {proc.stderr[:500]}")

        except FileNotFoundError as e:
            logger.error(f"Vina executable not found: {e}")
            result.stderr = str(e)
        except asyncio.TimeoutError:
            logger.error("Vina docking timed out (%ss)", timeout)
            result.stderr = f"Docking timed out after {timeout} seconds"
        except Exception as e:
            logger.error(f"Vina docking error: {e}")
            result.stderr = str(e)

        return result

    async def run_batch_docking(
        self,
        receptor_path: str,
        ligand_paths: list[str],
        box: VinaBox,
        params: Optional[VinaParams] = None,
        concurrency: int = 4,
    ) -> list[VinaResult]:
        """
        批量对接多个配体
        使用信号量控制并发数
        """
        semaphore = asyncio.Semaphore(concurrency)
        base_params = params or VinaParams(
            receptor_path=receptor_path,
            ligand_path="",  # 每个任务覆盖
            box=box,
        )

        async def _dock_one(idx: int, ligand: str) -> VinaResult:
            async with semaphore:
                job_params = VinaParams(
                    receptor_path=receptor_path,
                    ligand_path=ligand,
                    box=box,
                    exhaustiveness=base_params.exhaustiveness,
                    num_modes=base_params.num_modes,
                    energy_range=base_params.energy_range,
                    cpu=base_params.cpu,
                    seed=base_params.seed,
                    spacing=base_params.spacing,
                    verbosity=base_params.verbosity,
                )
                return await self.run_docking(job_params, job_id=f"batch_{idx}")

        tasks = [_dock_one(i, lig) for i, lig in enumerate(ligand_paths)]
        return await asyncio.gather(*tasks)

    def get_version_info(self) -> Optional[str]:
        """获取 Vina 版本信息"""
        try:
            proc = self.tool_manager.execute("autodock_vina", ["--version"], timeout=10)
            return proc.stdout.strip() or proc.stderr.strip()
        except Exception:
            return None
