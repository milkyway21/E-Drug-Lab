"""Celery 应用配置"""
from celery import Celery
from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "edrug_lab",
    broker=settings.celery.broker_url,
    backend=settings.celery.result_backend,
)

celery_app.conf.update(
    task_serializer=settings.celery.task_serializer,
    result_serializer=settings.celery.result_serializer,
    timezone=settings.celery.timezone,
    task_track_started=True,
    task_time_limit=3600,
    task_soft_time_limit=3000,
)
