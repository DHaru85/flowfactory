"""Celery 调度设施。"""

from service.celery_app import signals as _signals  # noqa: F401
from service.celery_app import tasks as _tasks  # noqa: F401
from service.celery_app.app import celery_app

__all__ = ["celery_app"]
