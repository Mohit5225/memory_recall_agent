import os
import logging
import asyncio
import threading
from datetime import datetime, timezone, timedelta
from celery_config.Celery_app import celery_app01
from src.db.mongo import get_schedule_by_id, update_schedule_by_id, find_schedules_for_dispatch, get_user_config
from src.models.schedule import ScheduleStatus, ScheduleType  # Only import what we actually use
from src.core.schedular import RRuleGenerator
from src.llm.gemini import get_gemini_response_async
from bson import ObjectId

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

# Simple processing status helpers
async def _check_and_mark_processing(schedule_id: str, task_id: str) -> bool:
    """Check if schedule is being processed and mark it if not."""
    try:
        from src.db.mongo import get_schedule_collection
        collection = await get_schedule_collection()
        
        # Check if already being processed
        schedule = await collection.find_one(
            {"_id": ObjectId(schedule_id)},
            {"processing_task_id": 1, "processing_started_at": 1}
        )
        
        if schedule:
            existing_task = schedule.get('processing_task_id')
            processing_started = schedule.get('processing_started_at')
            
            # If processing started more than 10 minutes ago, consider it stale
            if existing_task and processing_started:
                if datetime.now(timezone.utc) - processing_started > timedelta(minutes=10):
                    logger.warning(f"Stale processing status for schedule {schedule_id}, clearing...")
                    await _clear_processing_status(schedule_id, existing_task)
                else:
                    logger.warning(f"Schedule {schedule_id} already being processed by task {existing_task}")
                    return False
            
            # Mark as processing
            await collection.update_one(
                {"_id": ObjectId(schedule_id)},
                {
                    "$set": {
                        "processing_task_id": task_id,
                        "processing_started_at": datetime.now(timezone.utc)
                    }
                }
            )
            return True
        
        return False
    except Exception as e:
        logger.error(f"Error checking processing status: {e}")
        return True  # Allow processing if check fails

async def _clear_processing_status(schedule_id: str, task_id: str):
    """Clear processing status for a schedule."""
    try:
        from src.db.mongo import get_schedule_collection
        collection = await get_schedule_collection()
        await collection.update_one(
            {"_id": ObjectId(schedule_id), "processing_task_id": task_id},
            {"$unset": {"processing_task_id": "", "processing_started_at": ""}}
        )
    except Exception as e:
        logger.error(f"Error clearing processing status: {e}")

def _send_sms_placeholder(to_number: str, message_body: str, schedule_id: str):
    """Send WhatsApp message via Twilio."""
    try:
        from twilio.rest import Client
        import os
        
        # Get credentials from environment variables
        account_sid = os.getenv('TWILIO_ACCOUNT_SID')
        auth_token = os.getenv('TWILIO_AUTH_TOKEN')
        twilio_number = os.getenv('TWILIO_WHATSAPP_NUMBER', 'whatsapp:+14155238886')
        
        if not account_sid or not auth_token:
            logger.error("❌ Twilio credentials not found in environment")
            return False
            
        client = Client(account_sid, auth_token)
          # 🔧 FORCE YOUR NUMBER FOR TESTING
        actual_number = "+918469043310"  # Always use your number
          # 🔍 TRUNCATE MESSAGE FOR WHATSAPP LIMITS
        WHATSAPP_LIMIT = 1600
        TRUNCATE_SUFFIX = "\n\n[Message truncated for WhatsApp]"
        if len(message_body) > WHATSAPP_LIMIT:
            # Reserve space for the suffix
            max_content_length = WHATSAPP_LIMIT - len(TRUNCATE_SUFFIX)
            message_body = message_body[:max_content_length] + TRUNCATE_SUFFIX
        
        # 🔍 LOG WHAT'S ACTUALLY HAPPENING
        logger.info(f"[Schedule ID: {schedule_id}] SENDING WhatsApp to {actual_number}")
        logger.info(f"Message length: {len(message_body)} characters")
        
        try:
            message = client.messages.create(
                from_=twilio_number,
                body=message_body,
                to=f'whatsapp:{actual_number}'  # Use your actual number
            )
            # --- Log Twilio API response details ---
            logger.info(f"Twilio message SID: {message.sid}")
            logger.info(f"Twilio message status: {message.status}")
            if getattr(message, 'error_code', None):
                logger.error(f"Twilio error code: {message.error_code}")
                logger.error(f"Twilio error message: {message.error_message}")
            else:
                logger.info("No Twilio error code returned.")
            return True
        except Exception as twilio_exc:
            logger.error(f"❌ Exception during Twilio send: {twilio_exc}", exc_info=True)
            return False
    except Exception as e:
        logger.error(f"❌ Unexpected error in _send_sms_placeholder: {e}", exc_info=True)
        return False
from typing import Optional

async def _generate_reminder_content(user_id: str, schedule_name: str, schedule_notes: Optional[str] = None) -> str:
    """
    Generate LLM-powered reminder content based on user's configuration.
    Falls back to static content if LLM generation fails.
    """
    try:
        logger.info(f"Generating LLM reminder content for user {user_id}, schedule: {schedule_name}")
        
        # Fetch user's configured topic/prompt
        user_config = await get_user_config(user_id)
    
        if not user_config:
            logger.warning(f"No user config found for {user_id}. Using static reminder.")
            return f"{datetime.now(timezone.utc).strftime('%H:%M')}  Reminder: {schedule_name}"

        current_time = datetime.now(timezone.utc).strftime('%H:%M')
        
        # 🧠 INTELLIGENT, FLEXIBLE PROMPT - Let LLM think and explain
        prompt = f"""
        You are an intelligent educational reminder system. Your task is to create engaging, informative reminder content.

        USER'S LEARNING PREFERENCES:
        {user_config}

        SCHEDULE CONTEXT:
        - Schedule Name: {schedule_name}
        - Additional Notes: {schedule_notes if schedule_notes else 'None'}
        - Current Time: {current_time}

        INSTRUCTIONS:
        1. **Think First**: Analyze the user's configured topic and style preferences
        2. **Be Intelligent**: Use your knowledge to select relevant, interesting content about their topic
        3. **Create Educational Content**: Provide genuine learning value, not just a notification
        4. **Format**: Start with "{current_time}  Reminder:" then continue with your content
        5. **Length**: Write 25-35 lines of educational content (introduction, explanation, examples, use cases)
        6. **Adapt Your Style**: Match the tone/style specified in their configuration
        7. **Be Specific**: Include concrete examples, methods, concepts, or practical applications
        8. **Think Contextually**: Consider what would be most valuable to learn about this topic right now

        CONTENT STRUCTURE (adapt to the topic):
        - Brief introduction to today's focus
        - Core concept explanation
        - Practical examples or use cases
        - Key methods/techniques/principles
        - Why this matters or how to apply it
        - Optional: Quick tip or best practice

        **CRITICAL**: Do NOT use placeholders like [insert...] or [example...]. Use your intelligence to provide actual, specific content about their topic. Think about what someone learning this topic would benefit from knowing.

        Generate the educational reminder content now:
        """

        # Multiple retry attempts for LLM generation with validation
        max_retries = 3
        for attempt in range(max_retries):
            try:
                logger.info(f"Sending prompt to Gemini (attempt {attempt + 1}/{max_retries}): {prompt[:150]}...")
                response, context = await get_gemini_response_async(prompt)
                
                if response and "[insert" not in response.lower() and "example]" not in response.lower():
                    # Validate it's educational content (reasonable length)
                    word_count = len(response.split())
                    if word_count >= 50:  # Ensure substantial content
                        logger.info(f"✅ Generated substantial LLM reminder content ({word_count} words) for {user_id}")
                        return response.strip()
                    else:
                        logger.warning(f"LLM returned too brief content ({word_count} words), retrying...")
                else:
                    logger.warning(f"LLM returned placeholder content (attempt {attempt + 1}): {response[:100] if response else 'None'}")
                    
                if attempt < max_retries - 1:
                    continue
                    
            except Exception as e:
                logger.error(f"LLM generation attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    continue
                    
        # If we get here, all attempts failed
        logger.error("All LLM generation attempts failed, using fallback")
        return f"{current_time}  Reminder: {schedule_name} - Check your learning materials for today's topic."
            
    except Exception as e:
        logger.error(f"Error generating reminder content for user {user_id}: {e}", exc_info=True)
        return f"{datetime.now(timezone.utc).strftime('%H:%M')}  Reminder: {schedule_name}"

@celery_app01.task(
        name="src.task.send_reminder_notification",
        bind=True,                              # Bind task instance
        autoretry_for=(Exception,),             # Auto-retry on exceptions
        retry_backoff=True,                     # Exponential backoff
        retry_kwargs={'max_retries': 3},        # Max retry attempts
        acks_late=True                          # Acknowledge after completion
)
def send_reminder_notification(self, schedule_id: str):
    """
    Celery task to send a reminder notification for a given schedule ID.
    """
    task_id = self.request.id
    logger.info(f"Task {task_id} executing send_reminder_notification for schedule_id: {schedule_id}")

    async def _async_send_reminder():
        # Check if this schedule is already being processed
        can_process = await _check_and_mark_processing(schedule_id, task_id)
        if not can_process:
            logger.info(f"Task {task_id} skipped - schedule {schedule_id} already being processed")
            return "Skipped - already processing"
        
        try:
            # Retrieve the schedule from the database
            schedule = await get_schedule_by_id(schedule_id)
            if not schedule:
                logger.error(f"Schedule with ID {schedule_id} not found. Cannot send reminder.")
                return

            # Check if the schedule is active
            if schedule.status != ScheduleStatus.ACTIVE:
                logger.warning(f"Schedule {schedule_id} ({schedule.name}) is not active (status: {schedule.status}). Skipping reminder.")
                return
                  # 🔧 HARDCODED: Use your actual WhatsApp number
            user_phone_number = "+918469043310"  # Your verified WhatsApp number
            logger.info(f"User phone for {schedule.user_id} (schedule {schedule_id}): {user_phone_number} (hardcoded)")
            
            logger.info(f"Preparing to send reminder for schedule: {schedule.name} (ID: {schedule_id}) to user {schedule.user_id}")
            
            # Generate LLM-powered reminder content based on user's configured topic/prompt
            # Use getattr to safely access 'notes' attribute with a default value if it doesn't exist
            schedule_notes = getattr(schedule, 'notes', None)
            reminder_message = await _generate_reminder_content(schedule.user_id, schedule.name, schedule_notes)
            logger.info(f"Generated reminder content for schedule {schedule_id}: '{reminder_message[:150]}...'")            # Send the SMS (using placeholder)
            sms_sent_successfully = _send_sms_placeholder(user_phone_number, reminder_message, schedule_id)

            if not sms_sent_successfully:
                logger.error(f"SMS sending failed for schedule {schedule_id}. Not updating schedule state.")
                return
                
            now_utc = datetime.now(timezone.utc)
            processed_at_time = now_utc  # Always use current time for last_run_at
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
                    if schedule.next_run_at:
                        if schedule.next_run_at.tzinfo is None:
                            current_next_run_at = schedule.next_run_at.replace(tzinfo=timezone.utc)
                        else:
                            current_next_run_at = schedule.next_run_at
                    else:
                        current_next_run_at = datetime.now(timezone.utc)
                    
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
            
        except Exception as e:
            logger.error(f"Error processing schedule {schedule_id}: {e}", exc_info=True)
            raise
        finally:
            # Clear processing status
            await _clear_processing_status(schedule_id, task_id)

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