# src/celery_app.py
from celery import Celery
from .config.settings import CELERY_BROKER_URL, CELERY_RESULT_BACKEND
import logging

logger = logging.getLogger(__name__)

# Create Celery Application Instance
# The first argument is the main module's name.
# broker and backend specify the URLs for the message broker and result backend.
celery_app = Celery(
    'memory_recall_agent', # Name of the celery app
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND
)

# Configure Celery App
# You can set various configuration options here.
# See https://docs.celeryq.dev/en/stable/userguide/configuration.html
celery_app.conf.update(
    # Example configuration: enable Celery Beat for scheduling
    # This requires running 'celery -A src.celery_app beat' separately
    enable_utc=True, # Use UTC for time zones
    timezone='UTC', # Set default timezone
    # task_serializer='json', # How tasks are serialized (json is common)
    # accept_content=['json'], # What content types are accepted
    # result_serializer='json', # How results are serialized
    # broker_connection_retry_on_startup=True, # Retry connection on startup
    # task_track_started=True, # Track when tasks start
    # task_time_limit=300, # Tasks time out after 5 minutes
    # task_soft_time_limit=240, # Soft time limit before exception
)


# Optional: Auto-discover tasks in specified modules/packages
# This makes Celery automatically find tasks decorated with @celery_app.task
# in the listed modules. We'll add a tasks file later.
# celery_app.autodiscover_tasks(['src']) # Discover tasks in 'src' package

# Note: Tasks will be defined in a separate file (e.g., src/tasks.py) and imported/auto-discovered.

# Example of how to run Celery components:
# To run a Celery worker: celery -A src.celery_app worker -l info
# To run Celery Beat (the scheduler): celery -A src.celery_app beat -l info
# To run both: celery -A src.celery_app worker -l info -B

logger.info("✅ Celery application instance created and configured.")