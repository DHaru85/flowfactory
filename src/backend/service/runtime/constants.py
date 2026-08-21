"""运行时常量。"""

TASK_RUN = "service.celery_app.tasks.run_langgraph_flow"
TASK_RESUME = "service.celery_app.tasks.resume_langgraph_flow"
TASK_BEAT = "service.celery_app.tasks.dispatch_beat_tasks"
TASK_EXPIRE_HITL = "service.celery_app.tasks.expire_hitl_pending"
TASK_EXPIRE_CHILD = "service.celery_app.tasks.expire_child_run_pending"
TASK_INGEST = "service.celery_app.tasks.ingest_knowledge_doc"
TASK_LDAP_SYNC = "service.celery_app.tasks.sync_ldap_directory"
TASK_PURGE_SOFT_DELETED = "service.celery_app.tasks.purge_soft_deleted"

RUN_PENDING = "pending"
RUN_RUNNING = "running"
RUN_INTERRUPTED = "interrupted"
RUN_WAITING_CHILD = "waiting_child"
RUN_COMPLETED = "completed"
RUN_FAILED = "failed"
RUN_CANCELLED = "cancelled"

HITL_PENDING = "pending"
HITL_APPROVED = "approved"
HITL_REJECTED = "rejected"
HITL_EXPIRED = "expired"

CHILD_PENDING = "pending"
CHILD_RESUMED = "resumed"
CHILD_PARENT_CANCELLED = "parent_cancelled"

CELERY_QUEUED = "queued"
CELERY_STARTED = "started"
CELERY_RETRY = "retry"
CELERY_SUCCESS = "success"
CELERY_FAILURE = "failure"

NODE_PASSTHROUGH = "passthrough"
NODE_INTERRUPT = "interrupt"
NODE_LLM = "llm"

END_ALIASES = frozenset({"END", "__end__", "end"})
