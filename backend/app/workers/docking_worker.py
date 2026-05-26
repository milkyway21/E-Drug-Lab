"""AutoDock Vina 对接 Worker"""
import logging
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=2)
def run_docking(self, receptor_path: str, ligand_path: str, output_path: str, **kwargs):
    logger.info(f"开始对接任务：receptor={receptor_path}, ligand={ligand_path}")
    try:
        # TODO: 实际执行 AutoDock Vina
        self.update_state(state="PROGRESS", meta={"progress": 50})
        return {"status": "completed", "output": output_path}
    except Exception as e:
        logger.error(f"对接失败：{e}")
        self.retry(exc=e, countdown=60)
