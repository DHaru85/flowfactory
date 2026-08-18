"""运行时常量。"""

TASK_RUN = "service.celery_app.tasks.run_langgraph_flow"
TASK_RESUME = "service.celery_app.tasks.resume_langgraph_flow"
TASK_BEAT = "service.celery_app.tasks.dispatch_beat_tasks"
TASK_EXPIRE_HITL = "service.celery_app.tasks.expire_hitl_pending"

RUN_PENDING = "pending"
RUN_RUNNING = "running"
RUN_INTERRUPTED = "interrupted"
RUN_COMPLETED = "completed"
RUN_FAILED = "failed"
RUN_CANCELLED = "cancelled"

HITL_PENDING = "pending"
HITL_APPROVED = "approved"
HITL_REJECTED = "rejected"
HITL_EXPIRED = "expired"

CELERY_QUEUED = "queued"
CELERY_STARTED = "started"
CELERY_RETRY = "retry"
CELERY_SUCCESS = "success"
CELERY_FAILURE = "failure"

NODE_PASSTHROUGH = "passthrough"
NODE_INTERRUPT = "interrupt"
NODE_LLM = "llm"

END_ALIASES = frozenset({"END", "__end__", "end"})
