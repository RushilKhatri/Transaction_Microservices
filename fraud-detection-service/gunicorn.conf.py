"""
Gunicorn settings for the fraud detection service.
"""

import os
import shutil

from prometheus_client import multiprocess

bind = f"0.0.0.0:{os.getenv('PORT', '5002')}"
workers = int(os.getenv("GUNICORN_WORKERS", "2"))
timeout = int(os.getenv("GUNICORN_TIMEOUT", "60"))


def on_starting(server):
    multiproc_dir = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    if multiproc_dir:
        shutil.rmtree(multiproc_dir, ignore_errors=True)
        os.makedirs(multiproc_dir, exist_ok=True)


def child_exit(server, worker):
    multiprocess.mark_process_dead(worker.pid)
