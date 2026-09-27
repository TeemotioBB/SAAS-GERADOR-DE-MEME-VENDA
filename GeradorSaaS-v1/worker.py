import os

from redis import Redis
from rq import Queue, Worker

redis_url = os.getenv("REDIS_URL", "").strip()
if not redis_url:
    raise SystemExit("Defina REDIS_URL para iniciar o worker.")

connection = Redis.from_url(redis_url)
worker = Worker([Queue("default", connection=connection)], connection=connection)
worker.work(with_scheduler=False)
