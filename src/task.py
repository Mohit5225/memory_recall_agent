import os
import logging
import asyncio
import threading
from datetime import datetime, timezone
from celery_config.Celery_app import celery_app01
from src.db.mongo import get_schedule_by_id, update_schedule_by_id, find_schedules_for_dispatch, get_user_config
from src.models.schedule import ScheduleStatus, ScheduleType  # Only import what we actually use
from src.core.schedular import RRuleGenerator
from src.llm.gemini import get_gemini_response_async

logger = logging.getLogger(__name__)

# Thread-safe event loop manager for Celery tasks
class EventLoopManager:
    """Manages a single event loop for all Celery async operations."""
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._loop = None
                    cls._instance._thread = None
                    cls._instance._ready_event = None
                    cls._instance._shutdown_requested = False
        return cls._instance
    
    def get_loop(self):
        """Get or create the event loop for async operations."""
        with self._lock:
            if self._loop is None or self._loop.is_closed():
                self._setup_loop()
            return self._loop
    
    def _setup_loop(self):
        """Set up a new event loop in a background thread."""
        # Clean shutdown of existing thread if needed
        if self._thread and self._thread.is_alive():
            logger.warning("Event loop thread already running, skipping setup")
            return
            
        self._shutdown_requested = False
        self._ready_event = threading.Event()
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="EventLoopManager")
        self._thread.start()
        
        # Wait for loop to be ready with timeout
        if not self._ready_event.wait(timeout=5.0):
            logger.error("Event loop failed to start within 5 seconds")
            raise RuntimeError("Event loop initialization timeout")
        
        logger.info("Event loop manager initialized successfully")
    
    def _run_loop(self):
        """Run the event loop in the background thread."""
        try:
            asyncio.set_event_loop(self._loop)
            self._ready_event.set()  # Signal that loop is ready
            logger.debug("Event loop started in background thread")
            self._loop.run_forever()
        except Exception as e:
            logger.error(f"Event loop crashed: {e}")
            self._ready_event.set()  # Ensure waiting threads don't hang
        finally:
            logger.debug("Event loop thread exiting")
    
    def run_async(self, coro, timeout=30):
        """Run an async coroutine and return the result."""
        try:
            loop = self.get_loop()
            if loop.is_closed():
                raise RuntimeError("Event loop is closed")
                
            future = asyncio.run_coroutine_threadsafe(coro, loop)
            return future.result(timeout=timeout)
            
        except asyncio.TimeoutError:
            logger.error(f"Async operation timed out after {timeout} seconds")
            raise
        except Exception as e:
            logger.error(f"Async execution failed: {e}")
            raise
    
    def shutdown(self):
        """Gracefully shutdown the event loop and thread."""
        with self._lock:
            if self._shutdown_requested:
                return
                
            self._shutdown_requested = True
            logger.info("Shutting down event loop manager...")
            
            if self._loop and not self._loop.is_closed():
                # Schedule loop shutdown from within the loop thread
                self._loop.call_soon_threadsafe(self._loop.stop)
                
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=5.0)
                if self._thread.is_alive():
                    logger.warning("Event loop thread did not shutdown cleanly")
                    
            logger.info("Event loop manager shutdown complete")

# Global event loop manager
event_loop_manager = EventLoopManager()

# Register cleanup handler for Celery worker shutdown
import atexit
atexit.register(event_loop_manager.shutdown)

def _send_sms_placeholder(to_number: str, message_body: str, schedule_id: str):
    """Placeholder for sending SMS. In a real app, this would use Twilio."""
    logger.info(f"[Schedule ID: {schedule_id}] Attempting to send SMS to {to_number}: '{message_body}'")
    logger.info(f"SMS to {to_number} for schedule {schedule_id} with message '{message_body}' would be sent here.")
    return True


async def _generate_reminder_content(user_id: str, schedule_name: str, schedule_notes: str = None) -> str:
    """
    Generate LLM-powered reminder content based on user's configuration.
    Falls back to static content if LLM generation fails.
    
    Args:
        user_id: The user's ID to fetch their configured topic/prompt
        schedule_name: The name of the schedule
        schedule_notes: Optional notes for the schedule
    
    Returns:
        Generated reminder content string
    """
    try:
        logger.info(f"Generating LLM reminder content for user {user_id}, schedule: {schedule_name}")
        
        # Fetch user's configured topic/prompt
        user_config = await get_user_config(user_id)
        
        if not user_config or not user_config.strip():
            logger.warning(f"No user config found for {user_id}. Using static reminder.")
            return f"Reminder: {schedule_name}"
        
        # Prepare context for LLM
        context_notes = f" (Notes: {schedule_notes})" if schedule_notes else ""
        
        prompt = f"""
        Based on the user's learning configuration below, generate a personalized reminder message for their schedule '{schedule_name}'{context_notes}.
        
        User's Configuration:
        {user_config}
        
        Generate a helpful, motivating reminder message (2-3 sentences max) that relates to their configured topic and encourages them to engage with the scheduled activity.
        """
        
        # Call Gemini LLM
        llm_response, response_context = await get_gemini_response_async(prompt)
        
        if llm_response and response_context.get("processing_status") == "completed":
            logger.info(f"LLM-generated reminder for user {user_id}: '{llm_response[:100]}...'")
            return llm_response.strip()
        else:
            logger.warning(f"LLM generation failed for user {user_id}. Error: {response_context.get('error_details', 'Unknown')}")
            return f"Reminder: {schedule_name}"
            
    except Exception as e:
        logger.error(f"Error generating reminder content for user {user_id}: {e}", exc_info=True)
        return f"Reminder: {schedule_name}"


@celery_app01.task(name="src.task.send_reminder_notification")
def send_reminder_notification(schedule_id: str):
    """
    Celery task to send a reminder notification for a given schedule ID.
    """
    logger.info(f"Executing send_reminder_notification for schedule_id: {schedule_id}")

    async def _async_send_reminder():
        # Retrieve the schedule from the database
        schedule = await get_schedule_by_id(schedule_id)
        if not schedule:
            logger.error(f"Schedule with ID {schedule_id} not found. Cannot send reminder.")
            return

        # Check if the schedule is active
        if schedule.status != ScheduleStatus.ACTIVE:
            logger.warning(f"Schedule {schedule_id} ({schedule.name}) is not active (status: {schedule.status}). Skipping reminder.")
            return

        # Placeholder: Get user's phone number based on schedule.user_id
        user_phone_number = "+10000000000" # Example placeholder
        if hasattr(schedule, 'user_phone_override') and schedule.user_phone_override:
            user_phone_number = schedule.user_phone_override
        logger.info(f"User phone for {schedule.user_id} (schedule {schedule_id}): {user_phone_number} (placeholder)")
        
        logger.info(f"Preparing to send reminder for schedule: {schedule.name} (ID: {schedule_id}) to user {schedule.user_id}")
          # Generate LLM-powered reminder content based on user's configured topic/prompt
        # Use getattr to safely access 'notes' attribute with a default value if it doesn't exist
        schedule_notes = getattr(schedule, 'notes', None)
        reminder_message = await _generate_reminder_content(schedule.user_id, schedule.name, schedule_notes)
        logger.info(f"Generated reminder content for schedule {schedule_id}: '{reminder_message[:150]}...'")
        
        # Send the SMS (using placeholder)
        sms_sent_successfully = _send_sms_placeholder(user_phone_number, reminder_message, schedule_id)

        if not sms_sent_successfully:
            logger.error(f"SMS sending failed for schedule {schedule_id}. Not updating schedule state.")
            return

        now_utc = datetime.now(timezone.utc)
        processed_at_time = schedule.next_run_at if schedule.next_run_at else now_utc
        updates = {"last_run_at": processed_at_time}

        if schedule.schedule_type == ScheduleType.ONCE:
            updates["status"] = ScheduleStatus.COMPLETED
            logger.info(f"Marking one-time schedule {schedule_id} ({schedule.name}) as COMPLETED.")
        elif schedule.schedule_type in [ScheduleType.DAILY, ScheduleType.WEEKLY, ScheduleType.MONTHLY, ScheduleType.INTERVAL]:
            if not schedule.rrule_params:
                logger.error(f"Recurring schedule {schedule_id} ({schedule.name}) missing rrule_params! Schedule type: {schedule.schedule_type}")
                updates["status"] = ScheduleStatus.FAILED
                updates["error_details"] = f"Missing rrule_params for {schedule.schedule_type} schedule"
            else:
                logger.info(f"Processing recurring schedule {schedule_id} ({schedule.name}). Type: {schedule.schedule_type}")
                current_next_run_at = schedule.next_run_at or datetime.now(timezone.utc)
                
                try:
                    rrule_gen = RRuleGenerator(schedule.schedule_type.value, schedule.schedule_value)
                    next_occurrence = rrule_gen.calculate_initial_next_run_at(start_time=current_next_run_at)
                    
                    if next_occurrence:
                        updates["next_run_at"] = next_occurrence
                        logger.info(f"✅ Recurring schedule {schedule_id} ({schedule.name}) updated. Next run at: {next_occurrence.isoformat()}")
                    else:
                        logger.warning(f"No future occurrence found for schedule {schedule_id}. Marking as COMPLETED.")
                        updates["status"] = ScheduleStatus.COMPLETED
                        
                except Exception as e:
                    logger.error(f"Error processing recurring schedule {schedule_id}: {e}", exc_info=True)
                    updates["status"] = ScheduleStatus.FAILED
                    updates["error_details"] = f"Recurring schedule processing failed: {str(e)}"
        else:
            logger.warning(f"Schedule {schedule_id} ({schedule.name}) has unknown type {schedule.schedule_type}. Marking as COMPLETED.")
            updates["status"] = ScheduleStatus.COMPLETED

        await update_schedule_by_id(schedule_id, updates)
        logger.info(f"Successfully processed and updated schedule {schedule_id} ({schedule.name}). Updates: {updates}")

    try:
        # Use the thread-safe event loop manager with timeout
        event_loop_manager.run_async(_async_send_reminder(), timeout=60)
    except Exception as e:
        logger.error(f"Error in send_reminder_notification for schedule_id {schedule_id}: {e}", exc_info=True)


@celery_app01.task(name="src.task.dispatch_due_reminders")
def dispatch_due_reminders():
    """
    Celery Beat task to find due schedules and enqueue send_reminder_notification for each.
    """
    logger.info(f"Executing dispatch_due_reminders at {datetime.now(timezone.utc).isoformat()}")

    async def _async_dispatch():
        schedules_due = await find_schedules_for_dispatch()
        
        if not schedules_due:
            logger.info("No schedules due for dispatch at this time.")
            return

        logger.info(f"Found {len(schedules_due)} schedule(s) due for dispatch.")
        
        for schedule_doc in schedules_due:
            schedule_id = str(schedule_doc['_id'])
            schedule_name = schedule_doc.get('name', 'N/A')
            logger.info(f"Enqueueing send_reminder_notification for schedule ID: {schedule_id}, Name: {schedule_name}")
            send_reminder_notification.delay(schedule_id)

    try:
        # Use the thread-safe event loop manager with timeout
        event_loop_manager.run_async(_async_dispatch(), timeout=120)
    except Exception as e:
        logger.error(f"Error in dispatch_due_reminders: {e}", exc_info=True)


# Example of how to manually test a task (optional, for development)
if __name__ == '__main__':
    # To test send_reminder_notification with a specific schedule ID:
    # python -c "from src.task import send_reminder_notification; send_reminder_notification('your_schedule_id_here')"
    pass
