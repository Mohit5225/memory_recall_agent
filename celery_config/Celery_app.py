import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv
from celery import Celery


# Set up project root dynamically
project_root = str(Path(__file__).resolve().parents[1])  # Adjust path to find the correct project root
if project_root not in sys.path:
    sys.path.insert(0, project_root)  # Ensure project root is in path

# Load environment variables
load_dotenv()

# Configure detailed logging with no truncation
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

# Configure root logger to not truncate messages
root_logger = logging.getLogger()
for handler in root_logger.handlers:
    handler.formatter._style._fmt = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    # No need to set _ext_record_factory; this attribute does not exist and is not required.

logger = logging.getLogger(__name__)

# Retrieve broker and backend URLs from environment variables, ensuring flexibility
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")  # Uses env or fallback
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", CELERY_BROKER_URL)  # Ensures consistency

# Create Celery Application Instance (maintaining original variable name)
celery_app01 = Celery(
    'memory_recall_agent',
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=['src.task']  # Includes tasks from src/task.py dynamically
)

# Configure Celery App with standard settings for reliability
celery_app01.conf.update(
    enable_utc=True,
    timezone='UTC',
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    broker_connection_retry_on_startup=True,
    task_track_started=True,
    task_time_limit=300,  # Hard limit on task execution
    task_soft_time_limit=240,  # Soft limit before timeout exception
    
    # Anti-duplicate processing settings
    task_acks_late=True,  # Acknowledge tasks only after completion
    worker_prefetch_multiplier=1,  # Each worker takes only 1 task at a time
    task_reject_on_worker_lost=True,  # Reject tasks if worker dies
    
    worker_log_format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    worker_task_log_format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    worker_log_color=False  # Disable color to prevent truncation issues
)

# Celery Beat Settings
celery_app01.conf.beat_schedule = {
    'dispatch-due-reminders-every-50-seconds': {
        'task': 'src.task.dispatch_due_reminders',  # Task to run
        'schedule': 50.0,  # Run every 30 seconds
    },
}
celery_app01.conf.timezone = 'UTC'  # Set timezone for scheduled tasks

logger.info("✅ Celery application instance successfully created and configured.")