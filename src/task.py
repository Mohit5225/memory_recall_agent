"""Celery tasks for background processing."""
from celery_config import celery_app01
from celery.schedules import crontab
from src.core.message_queue import process_failed_messages
import asyncio

@celery_app01.task(name="retry_failed_messages")
def retry_failed_messages():
    """Celery task to retry failed message processing."""
    # Run the async function in an event loop
    loop = asyncio.get_event_loop()
    loop.run_until_complete(process_failed_messages())

# Schedule the task to run every 15 minutes
celery_app01.conf.beat_schedule = {
    'retry-failed-messages': {
        'task': 'retry_failed_messages',
        'schedule': crontab(minute='*/15'),  # Every 15 minutes
    },
}