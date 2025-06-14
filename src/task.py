import os
import logging
import asyncio # Added asyncio
from datetime import datetime, timezone
from celery_config.Celery_app import celery_app01
from src.db.mongo import get_schedule_by_id, update_schedule_by_id, find_schedules_for_dispatch
from src.models.schedule import Schedule, ScheduleStatus, ScheduleType
from src.core.schedular import RRuleGenerator # Added RRuleGenerator

logger = logging.getLogger(__name__)

# Placeholder for Twilio client and send_sms function
# In a real scenario, these would be properly initialized and used.
# from twilio.rest import Client
# TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
# TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
# TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
# twilio_client = None
# if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_PHONE_NUMBER:
#     twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

def _send_sms_placeholder(to_number: str, message_body: str, schedule_id: str):
    """Placeholder for sending SMS. In a real app, this would use Twilio."""
    logger.info(f"[Schedule ID: {schedule_id}] Attempting to send SMS to {to_number}: '{message_body}'")
    logger.info(f"SMS to {to_number} for schedule {schedule_id} with message '{message_body}' would be sent here.")
    return True


@celery_app01.task(name="src.task.send_reminder_notification")
def send_reminder_notification(schedule_id: str):
    """
    Celery task to send a reminder notification for a given schedule_id.
    It also updates the schedule's last_run_at, status (if one-time or finished),
    and next_run_at (if recurring).
    """
    logger.info(f"Executing send_reminder_notification for schedule_id: {schedule_id}")
    try:
        schedule_doc = asyncio.run(get_schedule_by_id(schedule_id))
        if not schedule_doc:
            logger.error(f"Schedule {schedule_id} not found. Cannot send reminder.")
            return

        schedule = Schedule(**schedule_doc)

        if schedule.status != ScheduleStatus.ACTIVE:
            logger.warning(f"Schedule {schedule_id} ({schedule.name}) is not active (status: {schedule.status}). Skipping reminder.")
            return

        # Placeholder: Get user's phone number based on schedule.user_id
        # This should be replaced with actual logic to fetch user details, including phone number.
        # For now, using a hardcoded placeholder.
        user_phone_number = "+10000000000" # Example placeholder
        if hasattr(schedule, 'user_phone_override') and schedule.user_phone_override: # Hypothetical field
             user_phone_number = schedule.user_phone_override
        logger.info(f"User phone for {schedule.user_id} (schedule {schedule_id}): {user_phone_number} (placeholder)")
        
        reminder_message = f"Reminder: {schedule.name}"
        if schedule.notes:
            reminder_message += f" - Notes: {schedule.notes}"

        logger.info(f"Preparing to send reminder for schedule: {schedule.name} (ID: {schedule_id}) to user {schedule.user_id}")
        
        # Send the SMS (using placeholder)
        sms_sent_successfully = _send_sms_placeholder(user_phone_number, reminder_message, schedule_id)

        if not sms_sent_successfully:
            logger.error(f"SMS sending failed for schedule {schedule_id}. Not updating schedule state.")
            # Optionally, implement retry logic or mark as failed attempt
            return

        now_utc = datetime.now(timezone.utc)
        
        # The time this instance was due and processed
        processed_at_time = schedule.next_run_at if schedule.next_run_at else now_utc


        updates = {"last_run_at": processed_at_time} # Update last_run_at to the time it was due

        if schedule.schedule_type == ScheduleType.ONCE:
            updates["status"] = ScheduleStatus.COMPLETED
            logger.info(f"Marking one-time schedule {schedule_id} ({schedule.name}) as COMPLETED.")
        elif schedule.schedule_type == ScheduleType.RECURRING and schedule.rrule:
            logger.info(f"Processing recurring schedule {schedule_id} ({schedule.name}). Original next_run_at: {schedule.next_run_at}")
            # Calculate the next occurrence based on the current next_run_at
            # Ensure schedule.next_run_at is a datetime object
            current_next_run_at = schedule.next_run_at
            if not isinstance(current_next_run_at, datetime):
                logger.warning(f"schedule.next_run_at for {schedule_id} is not a datetime object. Using now_utc as base.")
                current_next_run_at = now_utc # Fallback, though ideally next_run_at is always correctly set

            next_occurrence = RRuleGenerator.calculate_next_occurrence(
                rrule_str=schedule.rrule,
                after_datetime=current_next_run_at 
            )
            if next_occurrence:
                updates["next_run_at"] = next_occurrence
                logger.info(f"Recurring schedule {schedule_id} ({schedule.name}) updated. Next run at: {next_occurrence.isoformat()}")
            else:
                updates["status"] = ScheduleStatus.COMPLETED
                logger.info(f"Recurring schedule {schedule_id} ({schedule.name}) has no more occurrences. Marking as COMPLETED.")
        else:
            logger.warning(f"Schedule {schedule_id} ({schedule.name}) is of type {schedule.schedule_type} but missing rrule for recurrence. Treating as if completed after this run if not ONCE.")
            if schedule.schedule_type != ScheduleType.ONCE: # Avoid re-marking if already ONCE
                 updates["status"] = ScheduleStatus.COMPLETED


        asyncio.run(update_schedule_by_id(schedule_id, updates))
        logger.info(f"Successfully processed and updated schedule {schedule_id} ({schedule.name}). Updates: {updates}")

    except Exception as e:
        logger.error(f"Error in send_reminder_notification for schedule_id {schedule_id}: {e}", exc_info=True)


@celery_app01.task(name="src.task.dispatch_due_reminders")
def dispatch_due_reminders():
    """
    Celery Beat task to find due schedules and enqueue send_reminder_notification for each.
    """
    logger.info(f"Executing dispatch_due_reminders at {datetime.now(timezone.utc).isoformat()}")
    try:
        due_schedules = asyncio.run(find_schedules_for_dispatch()) # Fetches schedules with status ACTIVE and next_run_at <= now
        
        if not due_schedules:
            logger.info("No schedules are due for dispatch at this time.")
            return

        logger.info(f"Found {len(due_schedules)} schedules due for dispatch.")
        for schedule_doc in due_schedules:
            schedule_id = str(schedule_doc['_id']) # Ensure ID is a string
            schedule_name = schedule_doc.get('name', 'N/A')
            logger.info(f"Enqueueing send_reminder_notification for schedule ID: {schedule_id}, Name: {schedule_name}, Due: {schedule_doc.get('next_run_at')}")
            send_reminder_notification.delay(schedule_id)
            
            # Small safeguard: After dispatching, update its status to PENDING_DISPATCH or similar
            # to prevent re-dispatch if this task runs again before the worker picks up the reminder.
            # Or, ensure next_run_at is updated promptly by send_reminder_notification.
            # For now, relying on send_reminder_notification to update next_run_at or status.
            # A more robust system might use a temporary "locked" status.
            # Example of an immediate update to prevent re-queueing if desired:
            # asyncio.run(update_schedule_by_id(schedule_id, {"status": ScheduleStatus.PENDING_DISPATCH}))
            # However, this adds an extra DB write and might be overly cautious if workers are reasonably fast.

    except Exception as e:
        logger.error(f"Error in dispatch_due_reminders: {e}", exc_info=True)

# Example of how to manually test a task (optional, for development)
if __name__ == '__main__':
    # This block is for direct execution testing, not for Celery worker
    logging.basicConfig(level=logging.INFO)
    logger.info("Manual task testing (not via Celery worker)")
    
    # To test send_reminder_notification, you'd need a valid schedule_id from your DB
    # test_schedule_id = "your_schedule_id_here" 
    # if test_schedule_id != "your_schedule_id_here":
    #     logger.info(f"Manually calling send_reminder_notification for {test_schedule_id}")
    #     send_reminder_notification(test_schedule_id)
    # else:
    #     logger.info("Skipping manual send_reminder_notification, no test_schedule_id provided.")

    # To test dispatch_due_reminders
    # logger.info("Manually calling dispatch_due_reminders")
    # dispatch_due_reminders()
    pass
