from celery import Celery
from celery.schedules import crontab
import os
from dotenv import load_dotenv
from kombu import Queue
import tasks

load_dotenv()

celery_app = Celery(
    "scanner",
    broker=os.getenv("CELERY_BROKER_URL"),
    backend=os.getenv("CELERY_RESULT_BACKEND"),
)

celery_app.conf.update(
    task_routes={
        'tasks.scan_worker_and_self_images': {'queue': 'scanner_queue'},
    },
    task_queues=(
        Queue('scanner_queue', routing_key='scanner.#'),
    ),
    task_default_queue='scanner_queue',
    task_default_routing_key='scanner.default',
    timezone="UTC",
    beat_schedule={
        "scan-worker-image-every-hour": {
            "task": "tasks.scan_worker_and_self_images",
            # Executes every X minutes
            # "schedule": crontab(minute=0, hour='*/1'),
            "schedule": crontab(minute='*/6'),  # Executes every 6 minutes
        },
    },
    result_persistent=True,  # Make result messages persistent
    result_backend=os.getenv("CELERY_RESULT_BACKEND"),
    result_extended=True,  # Extend the result backend with additional fields
)
