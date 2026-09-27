from __future__ import annotations

import importlib
import threading

from flask import current_app


def _resolve(path: str):
    module_name, func_name = path.rsplit(".", 1)
    return getattr(importlib.import_module(module_name), func_name)


def enqueue(path: str, *args, timeout=1800, **kwargs):
    """Enfileira em Redis/RQ; em desenvolvimento pode cair para thread local."""
    redis_url = current_app.config.get("REDIS_URL", "")
    eager = bool(current_app.config.get("TASKS_EAGER"))

    if eager:
        return _resolve(path)(*args, **kwargs)

    if redis_url:
        from redis import Redis
        from rq import Queue
        conn = Redis.from_url(redis_url)
        q = Queue("default", connection=conn, default_timeout=timeout)
        return q.enqueue(path, *args, **kwargs, job_timeout=timeout, result_ttl=3600, failure_ttl=86400)

    # Fallback útil para desenvolvimento / beta em um único serviço.
    fn = _resolve(path)
    thread = threading.Thread(target=fn, args=args, kwargs=kwargs, daemon=True)
    thread.start()
    return thread
