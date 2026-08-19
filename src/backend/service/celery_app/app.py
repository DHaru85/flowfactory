"""Celery 应用实例。"""

from celery import Celery

from settings.config import get_settings


def create_celery_app() -> Celery:
    cfg = get_settings()
    app = Celery(
        "flowfactory",
        broker=cfg.celery_broker_url,
        backend="cache+memory://",
    )
    app.conf.update(
        task_always_eager=cfg.celery_eager,
        task_eager_propagates=True,
        task_ignore_result=True,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        worker_concurrency=cfg.celery_worker_concurrency,
        task_time_limit=cfg.celery_task_time_limit,
        task_soft_time_limit=cfg.celery_task_soft_time_limit,
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="Asia/Shanghai",
        enable_utc=True,
        task_default_queue=cfg.celery_queue_run,
        task_create_missing_queue=True,
        broker_connection_retry_on_startup=True,
        beat_schedule={
            "dispatch-beat-tasks": {
                "task": "service.celery_app.tasks.dispatch_beat_tasks",
                "schedule": float(cfg.beat_tick_seconds),
            },
            "expire-hitl-pending": {
                "task": "service.celery_app.tasks.expire_hitl_pending",
                "schedule": float(cfg.beat_tick_seconds),
            },
        },
        task_routes={
            "service.celery_app.tasks.run_langgraph_flow": {"queue": cfg.celery_queue_run},
            "service.celery_app.tasks.resume_langgraph_flow": {"queue": cfg.celery_queue_run},
            "service.celery_app.tasks.dispatch_beat_tasks": {"queue": cfg.celery_queue_beat},
            "service.celery_app.tasks.expire_hitl_pending": {"queue": cfg.celery_queue_beat},
            "service.celery_app.tasks.ingest_knowledge_doc": {"queue": cfg.celery_queue_ingest},
        },
    )
    return app


celery_app = create_celery_app()
