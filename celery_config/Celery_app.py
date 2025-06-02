import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from celery import Celery
import logging

# Set up project root dynamically
project_root = str(Path(__file__).resolve().parents[1])  # Adjust path to find the correct project root
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

# Retrieve broker and backend URLs from environment variables, ensuring flexibility
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")  # Uses env or fallback
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", CELERY_BROKER_URL)  # Ensures consistency

# Create Celery Application Instance (maintaining original variable name)
celery_app01 = Celery(
    'memory_recall_agent',
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=[]  # Includes tasks from src/task.py dynamically
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
)

logger.info("✅ Celery application instance successfully created and configured.")