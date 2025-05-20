from celery_config.Celery_app import celery_app01
from src.core.schedular import schedule_reminder_task
from src.db.mongo import get_schedule_definitions
import logging

logger = logging.getLogger(__name__)

@celery_app01.task
def generate_reminder_batch_task():
    """
    Celery task to process due schedules and trigger reminders.
    """
    logger.info("Running generate_reminder_batch_task")
    try:
        schedules = get_schedule_definitions()
        results = []
        for schedule in schedules:
            result = schedule_reminder_task(schedule.user_id, schedule.parsed_parameters_raw.get('user_input', ''))
            results.append({"schedule_id": str(schedule.id), "result": result})
            logger.info(f"Processed schedule {schedule.id}: {result}")
        return {"status": "success", "processed": len(schedules), "results": results}
    except Exception as e:
        logger.error(f"Error in generate_reminder_batch_task: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}