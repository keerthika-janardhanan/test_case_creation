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

