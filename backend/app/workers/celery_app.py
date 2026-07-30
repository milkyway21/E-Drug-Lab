"""Celery 应用配置 — 延迟初始化，避免 import 时触发 .env 读取。"""
import celery


class _CeleryAppProxy:
    """延迟代理：首次属性访问时才初始化真正的 Celery 实例。"""
    _real: celery.Celery | None = None

    def _ensure(self) -> celery.Celery:
        if self._real is None:
            from app.config import get_settings
            settings = get_settings()
            self._real = celery.Celery(
                "edrug_lab",
                broker=settings.celery.broker_url,
                backend=settings.celery.result_backend,
            )
            self._real.conf.update(
                task_serializer=settings.celery.task_serializer,
                result_serializer=settings.celery.result_serializer,
                timezone=settings.celery.timezone,
                task_track_started=True,
                task_time_limit=3600,
                task_soft_time_limit=3000,
            )
        return self._real

    def __getattr__(self, name):
        return getattr(self._ensure(), name)

    def __call__(self, *args, **kwargs):
        return self._ensure()(*args, **kwargs)

    def task(self, *args, **kwargs):
        return self._ensure().task(*args, **kwargs)


celery_app = _CeleryAppProxy()
