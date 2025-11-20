"""Celery application configuration."""

from __future__ import annotations

import os

from celery import Celery

broker_url = os.getenv("CELERY_BROKER_URL", "memory://")
backend_url = os.getenv("CELERY_RESULT_BACKEND", "cache+memory://")

celery_app = Celery("test_automation", broker=broker_url, backend=backend_url)

celery_app.conf.task_always_eager = os.getenv("CELERY_TASK_ALWAYS_EAGER", "1").lower() in {
    "1",
    "true",
    "yes",
}
celery_app.conf.task_eager_propagates = True
celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.accept_content = ["json"]

# Timeout settings (in seconds)
celery_app.conf.task_soft_time_limit = int(os.getenv("CELERY_TASK_SOFT_TIMEOUT", "300"))  # 5 minutes
celery_app.conf.task_time_limit = int(os.getenv("CELERY_TASK_HARD_TIMEOUT", "360"))  # 6 minutes
celery_app.conf.worker_max_tasks_per_child = int(os.getenv("CELERY_MAX_TASKS_PER_CHILD", "100"))

# Graceful shutdown
celery_app.conf.worker_shutdown_timeout = int(os.getenv("CELERY_SHUTDOWN_TIMEOUT", "10"))  # 10 seconds

