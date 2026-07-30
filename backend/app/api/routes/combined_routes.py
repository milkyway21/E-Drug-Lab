"""向后兼容：从独立模块重新导出。"""
from app.api.routes.screening import router as screening_router
from app.api.routes.admet import router as admet_router
from app.api.routes.affinity import router as affinity_router
from app.api.routes.molecules import router as molecules_router
from app.api.routes.tasks import router as tasks_router
