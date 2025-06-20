# src/core/scheduler.py
from celery_config.Celery_app import celery_app01
from src.db.mongo import create_schedule_definition, get_schedule_by_id, find_schedules, update_schedule_by_id, delete_schedule_by_id, deactivate_schedule_by_id, DatabaseError, get_user_config, save_user_config, normalize_user_config
from src.models.schedule import Schedule, PyObjectId, ScheduleType, ScheduleStatus # Import all relevant enums/models
from src.llm.gemini import get_gemini_response_async # Assuming this is available and works
import logging
from datetime import datetime, timedelta, timezone
import json
import dateparser
from typing import Optional, Dict, Any, List, Tuple
from dateutil.rrule import rrule, rrulestr, YEARLY, MONTHLY, WEEKLY, DAILY, HOURLY, MINUTELY, SECONDLY, MO, TU, WE, TH, FR, SA, SU
import pytz # For timezone conversions
from bson import ObjectId
import uuid
logger = logging.getLogger(__name__)

# --- Custom Exception for Clarification Needed ---
class ScheduleClarificationNeeded(Exception):
    """Custom exception raised when more information is needed to define a schedule."""
    def __init__(self, message: str, missing_field: str, clarification_prompt_key: str = None):
        super().__init__(message)
        self.message = message  # Store message as instance attribute
        self.missing_field = missing_field
        self.clarification_prompt_key = clarification_prompt_key or missing_field # Key for specific LLM prompt

# --- LLM Prompt for Unified Config and Schedule Extraction ---
UNIFIED_EXTRACTION_PROMPT_TEMPLATE = """
You are a unified extraction system for a personal reminder agent that handles both user configuration and schedule creation.
Your task is to analyze the user's request and extract BOTH configuration preferences and scheduling details.

{context_instruction}

example schema for schedule , you should replace the requested information but adopt following structure while returning config according to user request :
{{{{
  "config": {{{{
    "full_instruction_prompt": "string (the complete user preferences for reminder content, tone, topics, style - merge with existing config if provided, or create new if not)",
    "message_limit": "number (max messages to keep in history, default: 10)",
    "timezone": "string (user's preferred timezone, e.g., 'UTC', 'Asia/Kolkata', 'America/New_York' - use IANA format)"
  }}}},
  "schedule": {{{{
    "name": "string (a concise, human-readable name for the reminder, e.g., 'Daily AI Update', 'Tuesday Meeting Reminder')",
    "schedule_type": "string (one of: daily, weekly, monthly, once, interval, none_other - based on frequency or specific dates)",
    "schedule_value": "object (details for the schedule_type, e.g., {{{{"time": "10:00"}}}} for daily, {{{{"day_of_week": "Monday", "time": "09:00"}}}} for weekly, {{{{"date": "2025-12-31", "time": "14:00"}}}} for once, {{{{"interval": 2, "unit": "days"}}}} for interval. Empty object if not specified)",
    "timezone": "string (e.g., 'UTC', 'Asia/Kolkata', 'America/New_York' - inherit from config or infer from context)",
    "reminder_content_prompt_id": "string (Optional - The MongoDB ObjectId as a string for a predefined reminder template, or null if using direct message)",
    "notes": "string (any other relevant scheduling details or constraints, or null if none - e.g., 'weekends only', 'every other day')"
  }}}}
}}}}


example schema for config , you should replace the requested information but adopt following structure while returning config according to user request

  {{
    _id: ObjectId('6845df7212352b9f85fa8335'),
    user_id: 'gojo0123456789',
    config: {{
      full_instruction_prompt: '# Default Reminder Agent Configuration\\n' +
        '\\n' +
        '# --- Core Function ---\\n' +
        '# This agent generates brief, bite-sized knowledge reminders.\\n' +
        '# It is NOT meant for deep teaching or conversational dialogue beyond setting preferences.\\n' +
        '\\n' +
        '# --- Reminder Topic ---\\n' +
        '# Current Topic: pytorch methods and functions\\n' +
        '\\n' +
        '# --- Reminder Style/Manner ---\\n' +
        '# Style: Quick, factual.\\n' +
        '# Tone: witty , uplifting, and engaging.\\n' +
        '# Length: Max 10 sentences.\\n' +
        '# Timing: 11AM daily\\n' +
        '\\n' +
        '# --- Constraints ---\\n' +
        '# 1. Always stay on the specified topic.\\n' +
        '# 2. Do not explain concepts in depth. Just provide a brief reminder of their existence or a key characteristic.\\n' +
        '# 3. Never engage in chat outside of configuration updates.\\n' +
        '# 4. If asked a question about the topic, the answer should be a reminder, not a lesson.\\n' +
        '\\n' +
        '# --- Example (for the AI to understand the format) ---\\n' +
        `# Example Reminder: "Reminder: 'ls' command lists directory contents in Linux."`
    }}
  }}

    IMPORTANT INSTRUCTIONS for schedule schema and config schema:
- If existing config is provided in context, update the new preferences in fields of existing ones , if no new preferences passed about particular field then simply keep old preferences as before for that particular  field
- If no existing config, create a new comprehensive config based on message of user but keep schema as instructed below
- Extract content topics, tone, style preferences for the config section
- Always include both "config" and "schedule" sections in the response ,keep them seperate  and dont mix them up
- Return ONLY the JSON object. Do NOT include any other text before or after the JSON.


User Input: {user_input}

JSON Output:"""


# --- RRule Parameter Generation Utility ---
class RRuleGenerator:
    """
    A utility class to convert structured schedule_value into dateutil.rrule parameters.
    Handles validation and raises ScheduleClarificationNeeded if details are insufficient.
    """

    DAY_MAP = {
        "monday": MO, "mon": MO,

        "tuesday": TU, "tue": TU,
        "wednesday": WE, "wed": WE,
        "thursday": TH, "thu": TH,
        "friday": FR, "fri": FR,
        "saturday": SA, "sat": SA,
        "sunday": SU, "sun": SU,
    }

    FREQ_MAP = {
        "daily": DAILY,
        "weekly": WEEKLY,
        "monthly": MONTHLY,
        "yearly": YEARLY, # Although not explicitly in prompt, good to support
        "hourly": HOURLY,
        "minutely": MINUTELY,
        "secondly": SECONDLY,
    }

    def __init__(self, schedule_type: str, schedule_value: Dict[str, Any], user_timezone_str: str = "Asia/Kolkata"):
        self.schedule_type = schedule_type
        self.schedule_value = schedule_value if schedule_value is not None else {}
        self.user_timezone_str = user_timezone_str
        try:
            self.user_tz = pytz.timezone(user_timezone_str)
        except pytz.UnknownTimeZoneError:
            logger.warning(f"Unknown timezone '{user_timezone_str}'. Defaulting to Asia/Kolkata.")
            self.user_tz = pytz.timezone("Asia/Kolkata")

    def _parse_time(self, time_str: Optional[str]) -> Tuple[Optional[int], Optional[int], Optional[int]]:
        """Parses a time string (e.g., "09:00 AM") into (hour, minute, second)."""
        if not time_str:
            return None, None, None
        try:
            # dateparser is good for this, but we want exact hours/minutes/seconds
            # Use datetime.strptime for strict parsing
            dt_object = datetime.strptime(time_str.upper().replace('.', ''), '%I:%M %p') # Handles "9:00 AM", "9.00 AM"
            return dt_object.hour, dt_object.minute, dt_object.second
        except ValueError:
            try: # Try 24-hour format
                dt_object = datetime.strptime(time_str, '%H:%M')
                return dt_object.hour, dt_object.minute, dt_object.second
            except ValueError:
                logger.warning(f"Could not parse time string: {time_str}")
                return None, None, None

    def generate_rrule_params(self) -> Dict[str, Any]:
        """
        Generates dateutil.rrule parameters from schedule_type and schedule_value.
        """
        logger.info("========= Generating RRule Parameters =========")
        logger.info(f"Schedule Type: {self.schedule_type}")
        logger.info(f"Schedule Value: {json.dumps(self.schedule_value, indent=2)}")
        logger.info(f"User Timezone: {self.user_timezone_str}")
        
        rrule_params: Dict[str, Any] = {}
        
        # Parse time if present
        time_str = self.schedule_value.get("time")
        if time_str:
            logger.info(f"🔄 Parsing time string: {time_str}")
            hour, minute, second = self._parse_time(time_str)
            if hour is None or minute is None:
                logger.warning(f"❌ Failed to parse time: {time_str}")
                raise ScheduleClarificationNeeded(
                    f"Invalid time format detected: {time_str}",
                    missing_field="time",
                    clarification_prompt_key="invalid_time_format"
                )
            rrule_params['byhour'] = [hour]
            rrule_params['byminute'] = [minute]
            rrule_params['bysecond'] = [second if second is not None else 0]
            logger.info(f"✅ Parsed time components - Hour: {hour}, Minute: {minute}, Second: {second}")

        # Handle different schedule types
        if self.schedule_type == ScheduleType.ONCE.value:
            logger.info("Processing one-time schedule...")
            date_str = self.schedule_value.get("date")
            if not date_str:
                raise ScheduleClarificationNeeded(
                    "Date is required for a one-time schedule.",
                    missing_field="date",
                    clarification_prompt_key="missing_date_for_once"
                )
            if hour is None or minute is None:
                 raise ScheduleClarificationNeeded(
                    "Time is required for a one-time schedule.",
                    missing_field="time",
                    clarification_prompt_key="missing_time_for_once"
                )            # For 'once' schedules, we don't generate rrule_params directly,
            # but rather a specific datetime for next_run_at.
            # We'll handle this special case in _calculate_next_run_at.
            return {} # No rrule params for 'once'

        elif self.schedule_type == ScheduleType.DAILY.value:
            logger.info("Processing daily schedule...")
            rrule_params['freq'] = DAILY
            if hour is None or minute is None:
                raise ScheduleClarificationNeeded(
                    "Time is required for a daily schedule.",
                    missing_field="time",
                    clarification_prompt_key="missing_time_for_daily"
                )

        elif self.schedule_type == ScheduleType.WEEKLY.value:
            logger.info("Processing weekly schedule...")
            rrule_params['freq'] = WEEKLY
            day_of_week_value = self.schedule_value.get("day_of_week") or self.schedule_value.get("days_of_week")
            if not day_of_week_value:
                raise ScheduleClarificationNeeded(
                    "Day of the week (e.g., Monday) is required for a weekly schedule.",
                    missing_field="day_of_week",
                    clarification_prompt_key="missing_day_for_weekly"
                )
            
            # Handle both single day (string) and multiple days (list)
            if isinstance(day_of_week_value, str):
                # Single day of week
                byweekday = self.DAY_MAP.get(day_of_week_value.lower())
                if byweekday is None:
                    raise ScheduleClarificationNeeded(
                        f"Invalid day of week: {day_of_week_value}. Please provide a valid day (e.g., Monday).",
                        missing_field="day_of_week",
                        clarification_prompt_key="invalid_day_format"
                    )
                rrule_params['byweekday'] = byweekday
            elif isinstance(day_of_week_value, list):
                # Multiple days of week (e.g., weekends)
                byweekdays = []
                for day_str in day_of_week_value:
                    if not isinstance(day_str, str):
                        raise ScheduleClarificationNeeded(
                            f"Invalid day format in list: {day_str}. Each day should be a string (e.g., 'Monday').",
                            missing_field="day_of_week",
                            clarification_prompt_key="invalid_day_format"
                        )
                    byweekday = self.DAY_MAP.get(day_str.lower())
                    if byweekday is None:
                        raise ScheduleClarificationNeeded(
                            f"Invalid day of week: {day_str}. Please provide valid days (e.g., Monday, Tuesday).",
                            missing_field="day_of_week",
                            clarification_prompt_key="invalid_day_format"
                        )
                    byweekdays.append(byweekday)
                rrule_params['byweekday'] = byweekdays
            else:
                raise ScheduleClarificationNeeded(
                    f"Invalid day_of_week format: {day_of_week_value}. Should be a string (e.g., 'Monday') or list (e.g., ['Saturday', 'Sunday']).",
                    missing_field="day_of_week",
                    clarification_prompt_key="invalid_day_format"
                )
            
            # For multi-day schedules without specified time, use a default time
            if hour is None or minute is None:
                if isinstance(day_of_week_value, list):
                    # For multi-day schedules (like weekends), default to 10:00 AM if no time specified
                    logger.info("Multi-day weekly schedule without time - defaulting to 10:00 AM")
                    hour, minute, second = 10, 0, 0
                else:                    raise ScheduleClarificationNeeded(
                        "Time is required for a weekly schedule.",
                        missing_field="time",
                        clarification_prompt_key="missing_time_for_weekly"
                    )

        elif self.schedule_type == ScheduleType.MONTHLY.value:
            logger.info("Processing monthly schedule...")
            rrule_params['freq'] = MONTHLY
            
            # Parse time if provided
            time_str = self.schedule_value.get("time")
            if time_str:
                hour, minute, second = self.parse_time_string(time_str)
            else:
                hour, minute, second = None, None, None
            
            day_of_month = self.schedule_value.get("day_of_month") # e.g., 15
            if day_of_month is not None:
                try:
                    day_of_month = int(day_of_month)
                    if not (1 <= day_of_month <= 31):
                        raise ValueError("Day of month must be between 1 and 31.")
                    rrule_params['bymonthday'] = [day_of_month]
                except (ValueError, TypeError):
                     raise ScheduleClarificationNeeded(
                        f"Invalid day of month: {day_of_month}. Please provide a number between 1 and 31.",
                        missing_field="day_of_month",
                        clarification_prompt_key="invalid_day_of_month_format"
                    )
            elif "day_of_week" in self.schedule_value and "week_of_month" in self.schedule_value: # e.g., third Monday
                day_of_week_value = self.schedule_value["day_of_week"]
                week_of_month = self.schedule_value["week_of_month"] # e.g., 1, 2, 3, 4, -1
                
                # Handle both string and list for day_of_week in monthly schedules
                if isinstance(day_of_week_value, str):
                    day_of_week_str = day_of_week_value
                elif isinstance(day_of_week_value, list) and len(day_of_week_value) > 0:
                    # For monthly schedules with multiple days, use the first one
                    day_of_week_str = day_of_week_value[0]
                else:
                    raise ScheduleClarificationNeeded(
                        "Invalid day_of_week format.",
                        missing_field="day_of_week",
                        clarification_prompt_key="invalid_day_format"
                    )
                
                byweekday = self.DAY_MAP.get(day_of_week_str.lower())
                if byweekday is None:
                    raise ScheduleClarificationNeeded(
                        f"Invalid day of week: {day_of_week_str}. Please provide a valid day (e.g., Monday).",
                        missing_field="day_of_week",
                        clarification_prompt_key="invalid_day_format"
                    )
                try:
                    week_of_month = int(week_of_month)
                    # dateutil uses tuple (weekday, weeknum) for nth occurrence (e.g., (MO, 3) for third Monday)
                    rrule_params['byweekday'] = [byweekday(week_of_month)]
                except (ValueError, TypeError):
                    raise ScheduleClarificationNeeded(
                        f"Invalid week of month: {week_of_month}. Please provide a number (e.g., 1 for first, -1 for last).",
                        missing_field="week_of_month",
                        clarification_prompt_key="invalid_week_of_month_format"
                    )
            else:
                raise ScheduleClarificationNeeded(
                    "For monthly schedules, specify 'day_of_month' (e.g., 15) or 'day_of_week' and 'week_of_month' (e.g., third Monday).",
                    missing_field="monthly_detail",
                    clarification_prompt_key="missing_monthly_detail"
                )
            if hour is None or minute is None:
                raise ScheduleClarificationNeeded(
                    "Time is required for a monthly schedule.",
                    missing_field="time",
                    clarification_prompt_key="missing_time_for_monthly"
                )

        elif self.schedule_type == ScheduleType.INTERVAL.value:
            logger.info("Processing interval schedule...")
            interval = self.schedule_value.get("interval")
            unit = self.schedule_value.get("unit")
            if interval is None or unit is None:
                raise ScheduleClarificationNeeded(
                    "For interval schedules, 'interval' (e.g., 3) and 'unit' (e.g., hours, days) are required.",
                    missing_field="interval_details",
                    clarification_prompt_key="missing_interval_details"
                )
            try:
                interval = int(interval)
                if interval <= 0:
                     raise ValueError("Interval must be a positive number.")
            except (ValueError, TypeError):
                 raise ScheduleClarificationNeeded(
                    f"Invalid interval: {interval}. Please provide a positive number.",
                    missing_field="interval",
                    clarification_prompt_key="invalid_interval_format"
                )

            freq = self.FREQ_MAP.get(unit.lower())
            if freq is None:
                raise ScheduleClarificationNeeded(
                    f"Invalid unit: {unit}. Supported units are hours, days, weekly, monthly, etc.",
                    missing_field="interval_unit",
                    clarification_prompt_key="invalid_interval_unit"
                )
            rrule_params['freq'] = freq
            rrule_params['interval'] = interval

        elif self.schedule_type == ScheduleType.NONE_OTHER.value:
            # If LLM classified as none_other, it's not a supported schedule type.
            raise ScheduleClarificationNeeded(
                "I couldn't classify your request into a supported schedule type (daily, weekly, monthly, once, interval). Please rephrase.",
                missing_field="schedule_type",
                clarification_prompt_key="unsupported_schedule_type"
            )
        else:
            # Should be caught by ScheduleType enum validation, but for safety
            raise ScheduleClarificationNeeded(
                f"Unrecognized schedule type: {self.schedule_type}.",
                missing_field="schedule_type",
                clarification_prompt_key="unrecognized_schedule_type_system_error"
            )

        logger.debug(f"Generated rrule_params for type {self.schedule_type}: {rrule_params}")
        return rrule_params

    def calculate_initial_next_run_at(self, start_time: datetime = None) -> datetime:
        """
        Calculates the initial next_run_at timestamp based on rrule_params and timezone.
        For 'once' schedules, directly parses the datetime.
        `start_time` should be timezone-aware (preferably UTC).
        """
        now_utc = datetime.now(timezone.utc)
        if start_time is None:
            # Use current time in user's timezone for initial context, then convert to UTC
            start_time_local = now_utc.astimezone(self.user_tz)
        else:
            # Ensure start_time is converted to user's timezone for rule application, then back to UTC
            start_time_local = start_time.astimezone(self.user_tz)

        if self.schedule_type == ScheduleType.ONCE.value:
            date_str = self.schedule_value.get("date")
            time_str = self.schedule_value.get("time")
            combined_datetime_str = f"{date_str} {time_str}" if date_str and time_str else None

            if not combined_datetime_str:
                raise ScheduleClarificationNeeded(
                    "Date and time are required to calculate next run for a one-time schedule.",
                    missing_field="date_time",
                    clarification_prompt_key="missing_date_time_for_once"
                )
            
            parsed_dt_local = dateparser.parse(combined_datetime_str, settings={'TIMEZONE': self.user_tz.zone, 'RETURN_AS_TIMEZONE_AWARE': True})

            if parsed_dt_local:
                # Ensure the parsed time is in the future for 'once' events
                parsed_dt_utc = parsed_dt_local.astimezone(timezone.utc)
                if parsed_dt_utc < now_utc:
                    # If the 'once' event is in the past, it's invalid.
                    raise ScheduleClarificationNeeded(
                        "The specified one-time reminder date/time is in the past.",
                        missing_field="past_date_time",
                        clarification_prompt_key="once_in_past"
                    )
                return parsed_dt_utc
            else:
                raise ScheduleClarificationNeeded(
                    f"Could not parse '{combined_datetime_str}' into a valid date/time for a one-time schedule.",
                    missing_field="date_time",
                    clarification_prompt_key="invalid_date_time_format_once"
                )
        else:
            # For recurring schedules, calculate based on rrule
            rrule_params = self.generate_rrule_params() # This call validates and may raise
            
            # Construct the rrule from the start_time_local in the user's timezone
            # and then find the next occurrence.
            # Convert rrule_params 'byhour', 'byminute', 'bysecond' to local time if necessary
            # (rrule expects these to match the start_time's timezone)

            # Important: rrule takes dtstart in the desired timezone,
            # and byhour/byminute/bysecond are relative to that timezone.
            # Our _parse_time already extracted these in 24-hour format.
            # So, apply them to the local start_time.

            # Create a localized start_time for rrule calculation
            rrule_dtstart = start_time_local.replace(
                hour=rrule_params.get('byhour', [start_time_local.hour])[0],
                minute=rrule_params.get('byminute', [start_time_local.minute])[0],
                second=rrule_params.get('bysecond', [start_time_local.second])[0],
                microsecond=0
            )

            # If the calculated rrule_dtstart is in the past for a recurring schedule,
            # we want the *next* occurrence.
            # rrule.after() handles this gracefully.
            try:
                # Remove byhour, byminute, bysecond from rrule_params as they are handled by dtstart.replace()
                # rrule takes them as separate kwargs or implicitly from dtstart.
                # However, for 'byhour', 'byminute', 'bysecond' to apply to *all* occurrences,
                # they should be in the rrule_params.
                # Let's re-think: rrule's dtstart sets the starting point.
                # byhour/byminute/bysecond restrict the *times* of generated occurrences.
                # So if we say daily, 9 AM, we want 9 AM each day *after* dtstart.

                # Best practice: always set dtstart to current time in the relevant timezone (user_tz here)
                # and let rrule generate the first occurrence *after* that.
                # 'byhour', 'byminute', 'bysecond' are correct for rrule_params.

                rule = rrule(dtstart=now_utc.astimezone(self.user_tz), **rrule_params)
                
                # Get the first occurrence strictly *after* now_utc
                next_occurrence_local = rule.after(now_utc.astimezone(self.user_tz), inc=False)
                
                if next_occurrence_local is None:
                    raise ScheduleClarificationNeeded(
                        "Could not find a valid future occurrence for the specified recurring schedule.",
                        missing_field="rrule_no_future_occurrence",
                        clarification_prompt_key="rrule_no_future_occurrence"
                    )

                return next_occurrence_local.astimezone(timezone.utc)

            except Exception as e:
                logger.error(f"Error generating rrule or calculating next run for {self.schedule_type}: {e}", exc_info=True)
                raise ScheduleClarificationNeeded(
                    f"Could not calculate the next run time for your schedule. Details: {e}",
                    missing_field="rrule_calculation_error",
                    clarification_prompt_key="rrule_calculation_error"
                )

    def serialize_rrule_params_for_db(self, rrule_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert rrule_params to a MongoDB-serializable format.
        Converts dateutil.rrule.weekday objects to integers.
        """
        serialized = rrule_params.copy()
        
        # Convert weekday objects to integers
        if 'byweekday' in serialized:
            weekday_value = serialized['byweekday']
            if hasattr(weekday_value, 'weekday'):
                # Single weekday object (e.g., MO, TU, etc.)
                serialized['byweekday'] = weekday_value.weekday
            elif isinstance(weekday_value, list):
                # List of weekday objects or tuples
                serialized_weekdays = []
                for wd in weekday_value:
                    if hasattr(wd, 'weekday'):
                        # Weekday object with possible nth occurrence
                        if hasattr(wd, 'n') and wd.n is not None:
                            # e.g., MO(2) for second Monday -> [0, 2]
                            serialized_weekdays.append([wd.weekday, wd.n])
                        else:
                            # Simple weekday -> 0
                            serialized_weekdays.append(wd.weekday)
                    else:
                        # Already serialized or integer
                        serialized_weekdays.append(wd)
                serialized['byweekday'] = serialized_weekdays
        
        return serialized

    @staticmethod
    def deserialize_rrule_params_from_db(serialized_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert MongoDB-stored rrule_params back to dateutil format.
        Converts integers back to dateutil.rrule.weekday objects.
        """
        from dateutil.rrule import MO, TU, WE, TH, FR, SA, SU
        
        WEEKDAY_MAP = [MO, TU, WE, TH, FR, SA, SU]
        
        deserialized = serialized_params.copy()
        
        # Convert integers back to weekday objects
        if 'byweekday' in deserialized:
            weekday_value = deserialized['byweekday']
            if isinstance(weekday_value, int):
                # Single integer -> weekday object
                deserialized['byweekday'] = WEEKDAY_MAP[weekday_value]
            elif isinstance(weekday_value, list):
                # List of integers or [int, nth] pairs
                deserialized_weekdays = []
                for wd in weekday_value:
                    if isinstance(wd, int):
                        # Simple integer -> weekday object
                        deserialized_weekdays.append(WEEKDAY_MAP[wd])
                    elif isinstance(wd, list) and len(wd) == 2:
                        # [weekday_int, nth] -> weekday(nth)
                        weekday_obj = WEEKDAY_MAP[wd[0]]
                        deserialized_weekdays.append(weekday_obj(wd[1]))
                    else:
                        # Already deserialized or unknown format
                        deserialized_weekdays.append(wd)
                deserialized['byweekday'] = deserialized_weekdays
        
        return deserialized

# --- LLM Clarification Question Generation Prompt ---
CLARIFICATION_PROMPT_TEMPLATE = """
The user wants to set a reminder, but some information required for the schedule is missing or unclear.
Based on the missing_detail_key, craft a concise, polite, and direct question to ask the user for this specific missing detail.
Do NOT include any preamble or conversational filler. Just the direct question.

Missing Detail Keys and Example Questions:
- "name": "What would you like to name this reminder?"
- "reminder_content_prompt_id": "Please provide the unique ID for the reminder's content prompt."
- "schedule_type": "Could you clarify the exact frequency? For example, is it daily, weekly, monthly, or a one-time reminder?"
- "time": "At what specific time should the reminder be set? (e.g., 9 AM, 14:30)"
- "invalid_time_format": "The time format is unclear. Could you provide the time in a standard format, like '9 AM' or '14:30'?"
- "date": "What exact date should the one-time reminder be set for? (e.g., 2025-06-30)"
- "date_time": "What is the exact date and time for this one-time reminder? (e.g., 2025-06-30 at 5 PM)"
- "missing_date_for_once": "What date should the one-time reminder be set for?"
- "missing_time_for_once": "What time should the one-time reminder be set for?"
- "once_in_past": "The one-time reminder you specified is in the past. Please provide a future date and time."
- "missing_time_for_daily": "At what specific time each day should the daily reminder be set?"
- "day_of_week": "Which day of the week (e.g., Monday, Tuesday) should the weekly reminder be set?"
- "missing_day_for_weekly": "Which day of the week should the weekly reminder be set? (e.g., Monday)"
- "missing_time_for_weekly": "At what specific time on that day should the weekly reminder be set?"
- "monthly_detail": "For monthly reminders, do you want it on a specific day of the month (e.g., the 15th) or on a specific day of the week in a month (e.g., the third Tuesday)?"
- "missing_monthly_detail": "To schedule a monthly reminder, please specify a day of the month (e.g., 'on the 15th') or a day of the week and its occurrence (e.g., 'on the third Monday')."
- "invalid_day_of_month_format": "The day of the month is invalid. Please provide a number between 1 and 31."
- "invalid_week_of_month_format": "The week of the month is invalid. Please provide a number (e.g., '1' for first, '-1' for last)."
- "interval_details": "For interval reminders, how often should it repeat? (e.g., 'every 3 hours', 'every 2 days')"
- "missing_interval_details": "Please specify the interval and unit for this reminder (e.g., 'every 3 hours', 'every 2 days')."
- "invalid_interval_format": "The interval amount is invalid. Please provide a positive number."
- "interval_unit": "What unit should the interval be? (e.g., hours, days, weeks, months)"
- "unsupported_schedule_type": "I couldn't identify a clear schedule type. Could you please specify if it's daily, weekly, monthly, a one-time event, or at a specific interval?"
- "rrule_calculation_error": "There was an issue calculating the precise schedule. Could you try rephrasing the frequency or details?"
- "rrule_no_future_occurrence": "Based on your description, there are no future occurrences for this schedule. Did you intend for it to start later?"
- "invalid_prompt_id": "The provided reminder content prompt ID seems invalid or missing. Please ensure it's a valid 24-character ID."
- "other": "Could you please provide more details to help me schedule this reminder?"

Missing Detail Key: {missing_detail_key}

Question:"""


# --- Core Scheduling Logic ---
async def parse_schedule_parameters_and_clarify(user_input: str, user_id: str) -> Dict[str, Any]:
    """
    Orchestrates the unified config+schedule extraction from user input.
    Checks for existing config, calls LLM with unified prompt, and returns both config and schedule data.
    """
    logger.info("========= Starting Unified Config+Schedule Parameter Parsing =========")
    logger.info(f"Processing user input: '{user_input}' for user: {user_id}")

    try:        # Step 1: Load and normalize existing user config
        logger.info("🔄 Checking for existing user config...")
        raw_existing = await get_user_config(user_id)
        norm_existing = normalize_user_config(raw_existing)
        # Step 2: Build context instruction for LLM prompt
        prompt_value = norm_existing['full_instruction_prompt']
        existing_prompt = prompt_value.strip()
        if existing_prompt:
            logger.info("✅ Found existing config - will merge with new preferences")
            context_instruction = f"""
EXISTING USER CONFIG CONTEXT:
The user already has these preferences configured:
- Current instruction prompt: \"{norm_existing['full_instruction_prompt']}\"
- Current timezone: \"{norm_existing['timezone']}\"
- Current message limit: {norm_existing['message_limit']}

Please MERGE the new preferences from the user input with the existing config. Keep existing preferences unless the user specifically wants to change them.
"""
        else:
            logger.info("ℹ️ No existing config found - will create new comprehensive config")
            context_instruction = """
NEW USER SETUP:
This user has no existing configuration. Please create a comprehensive new config based on their preferences in the input.
Extract topic preferences, tone, style, and any other customization details they mention.
"""

        # Phase 1: include existing schedule context
        logger.info("🔄 Checking for existing user schedule...")
        existing_schedules = await find_schedules(user_id=user_id, query_params={"status": ScheduleStatus.ACTIVE.value})
        if existing_schedules:
            existing_schedule = existing_schedules[0]
            context_instruction += f"""
EXISTING USER SCHEDULE CONTEXT:
- Name: \"{existing_schedule.name}\"
- Type: \"{existing_schedule.schedule_type}\"
- Value: {json.dumps(existing_schedule.schedule_value)}
- Timezone: \"{existing_schedule.timezone}\"

Please only update these fields if the user request changes them.
"""

        # Step 3: Construct unified LLM prompt
        llm_prompt = UNIFIED_EXTRACTION_PROMPT_TEMPLATE.format(
            context_instruction=context_instruction,
            user_input=user_input
        ).strip()
        
        logger.info("🔄 Generated unified LLM prompt:")
        logger.info("---BEGIN PROMPT---")
        logger.info(llm_prompt)
        logger.info("---END PROMPT---")
        
        # Step 4: Get LLM response (returns tuple: response, context)
        raw_llm_output, response_context = await get_gemini_response_async(llm_prompt)
        
        logger.info("✅ Received LLM response:")
        logger.info("---BEGIN LLM RESPONSE---")
        logger.info(raw_llm_output)
        logger.info("---END LLM RESPONSE---")
        logger.info(f"LLM processing context: {response_context.get('processing_status', 'unknown')}")

        if raw_llm_output is None or response_context.get("processing_status") != "completed":
            error_details = response_context.get('error_details', 'Unknown error')
            logger.error(f"❌ LLM processing failed: {error_details}")
            return {"status": "failure", "message": f"Failed to get a response from the AI for scheduling details. Error: {error_details}"}

        # Step 5: Extract and parse JSON
        json_start = raw_llm_output.find('{')
        json_end = raw_llm_output.rfind('}')
        if json_start == -1 or json_end == -1:
            logger.error("❌ No JSON object found in LLM output")
            return {"status": "failure", "message": "The AI provided an unparseable response for scheduling."}
            
        json_string = raw_llm_output[json_start : json_end + 1]
        logger.info("🔄 Attempting to parse JSON from LLM output:")
        logger.info(f"Extracted JSON string: {json_string}")
        
        parsed_response = json.loads(json_string)
        logger.info("✅ Successfully parsed JSON. Full response:")
        logger.info(json.dumps(parsed_response, indent=2))

        # Step 6: Validate the unified response structure
        if "config" not in parsed_response or "schedule" not in parsed_response:
            logger.error("❌ LLM response missing required 'config' or 'schedule' sections")
            return {"status": "failure", "message": "The AI response was missing required configuration or schedule information."}

        config_data = parsed_response["config"]
        schedule_data = parsed_response["schedule"]

        # Step 7: Validate config section
        logger.info("🔄 Validating config section...")
        config_required_keys = ["full_instruction_prompt", "message_limit", "timezone"]
        for key in config_required_keys:
            if key not in config_data or config_data[key] is None:
                logger.warning(f"Missing config field: {key}")
                return {"status": "clarification_needed", 
                        "question": await get_llm_clarification_question(f"config_{key}"),
                        "missing_field": f"config_{key}"}

        # Step 8: Validate schedule section
        logger.info("🔄 Validating schedule section...")
        schedule_required_keys = ["name", "schedule_type", "schedule_value", "timezone"]
        for key in schedule_required_keys:
            if key not in schedule_data or schedule_data[key] is None:
                logger.warning(f"Missing schedule field: {key}")
                return {"status": "clarification_needed", 
                        "question": await get_llm_clarification_question(f"schedule_{key}"),
                        "missing_field": f"schedule_{key}"}        # Validate ScheduleType enum
        classified_type_str = schedule_data.get("schedule_type", "").lower()
        if classified_type_str not in [e.value for e in ScheduleType]:
            logger.warning(f"LLM output contained invalid schedule_type: {classified_type_str}")
            return {"status": "clarification_needed",
                    "question": await get_llm_clarification_question("schedule_type"),
                    "missing_field": "schedule_type"}
        
        schedule_type = ScheduleType(classified_type_str)

        # Step 9: Generate RRule Parameters and Calculate Next Run
        user_timezone = schedule_data.get("timezone") or config_data.get("timezone") or "Asia/Kolkata"
        rrule_generator = RRuleGenerator(
            schedule_type=schedule_type.value,
            schedule_value=schedule_data["schedule_value"],
            user_timezone_str=user_timezone
        )

        try:
            rrule_params = rrule_generator.generate_rrule_params()
            initial_next_run_at = rrule_generator.calculate_initial_next_run_at()
        except ScheduleClarificationNeeded as e:
            logger.warning(f"Clarification needed for recurring schedule: {e.missing_field} - {e.message}")
            return {"status": "clarification_needed",
                    "question": await get_llm_clarification_question(e.clarification_prompt_key or e.missing_field),
                    "missing_field": e.missing_field}
        except Exception as e:
            logger.error(f"Unexpected error during rrule generation/calculation: {e}", exc_info=True)
            return {"status": "clarification_needed",
                    "question": await get_llm_clarification_question("rrule_calculation_error"),
                    "missing_field": "rrule_calculation_error"}        # Step 10: Prepare final schedule parameters
        # Serialize rrule_params for MongoDB storage
        serialized_rrule_params = rrule_generator.serialize_rrule_params_for_db(rrule_params)
        
        final_schedule_params = {
            "user_id": user_id,  # Add the missing user_id field
            "name": schedule_data["name"],
            "schedule_type": schedule_type.value,
            "schedule_value": schedule_data["schedule_value"],
            "rrule_params": serialized_rrule_params,
            "next_run_at": initial_next_run_at,
            "last_run_at": None,
            "reminder_content_prompt_id": schedule_data.get("reminder_content_prompt_id"),
            "status": ScheduleStatus.ACTIVE,
            "timezone": user_timezone,
            "notes": schedule_data.get("notes"),
        }

        # Step 11: Prepare final config data
        final_config_data = {
            "full_instruction_prompt": config_data["full_instruction_prompt"],
            "message_limit": config_data["message_limit"],
            "timezone": config_data["timezone"],
            "updated_at": datetime.now(timezone.utc)
        }

        logger.info(f"✅ Successfully parsed unified parameters. Next run at: {initial_next_run_at}")
        return {
            "status": "success", 
            "config_data": final_config_data,
            "schedule_params": final_schedule_params
        }

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM output as JSON: {e}. Raw Output: {raw_llm_output}", exc_info=True)
        return {"status": "failure", "message": "Failed to understand the schedule. The AI's response was not valid JSON."}
    except Exception as e:
        logger.error(f"Unexpected error during unified parsing for input '{user_input[:100]}...': {e}", exc_info=True)
        return {"status": "failure", "message": "An unexpected error occurred while trying to parse your schedule details."}


# --- Function to Generate LLM Clarification Question ---
async def get_llm_clarification_question(missing_detail_key: str) -> str:
    """
    Uses an LLM call to generate a natural language clarification question based on a key.
    """
    prompt = CLARIFICATION_PROMPT_TEMPLATE.format(missing_detail_key=missing_detail_key).strip()
    try:
        response, context = await get_gemini_response_async(prompt)
        if response and context.get("processing_status") == "completed":
            return response.strip()
        logger.warning(f"LLM returned empty response for clarification key: {missing_detail_key}. Falling back to generic.")
        return "Could you please provide more details to help me schedule this reminder?"
    except Exception as e:
        logger.error(f"Error generating LLM clarification question for '{missing_detail_key}': {e}", exc_info=True)
        return "I need more information to set this reminder. Can you please provide more details?"


# --- Function to Schedule a Reminder Task via Celery (Handles parsing outcome) ---
async def schedule_reminder_task(user_id: str, user_input: str) -> Dict[str, Any]:
    """
    Processes a scheduling request with integrated config+schedule creation.
    Checks for existing config, creates/updates both config and schedule in unified flow.
    """
    logger.info("========= Starting Unified Config+Schedule Request =========")
    logger.info(f"Received user input: '{user_input}'")
    logger.info(f"For user_id: {user_id}")

    try:
        # Step 1: Parse both config and schedule parameters from user input
        logger.info("🔄 Parsing unified config+schedule parameters...")
        parsing_result = await parse_schedule_parameters_and_clarify(user_input, user_id)
        logger.info(f"Parsing result status: {parsing_result['status']}")

        if parsing_result["status"] == "clarification_needed":
            logger.info(f"⚠️ Clarification needed for field: {parsing_result.get('missing_field')}")
            logger.info(f"Question to ask user: {parsing_result.get('question', '')}")
            return {
                "next": "schedule_clarification",
                "final_outcome": f"I need more information to set up your schedule. {parsing_result.get('question', '')}",
                "missing_field": parsing_result.get("missing_field")
            }
        elif parsing_result["status"] == "failure":
            logger.error(f"❌ Failed to parse parameters: {parsing_result.get('message')}")
            return {
                "next": "schedule_failure",
                "final_outcome": parsing_result["message"]
            }
        
        # If status is "success"
        config_data = parsing_result["config_data"]
        schedule_params = parsing_result["schedule_params"]
        
        logger.info("✅ Successfully parsed unified parameters:")
        logger.info(f"Config data: {config_data}")
        logger.info(f"Schedule params: {schedule_params}")        # Step 2: Check for existing config and determine if update is needed        logger.info("🔄 Checking for existing user config...")
        existing_config = await get_user_config(user_id)
        
        config_needs_update = True
        prompt = existing_config.get("full_instruction_prompt") or "" if existing_config else ""
        if existing_config and prompt:
            logger.info("✅ Found existing config for user")
            # Compare all fields to determine if update is needed
            if (existing_config["full_instruction_prompt"] == config_data["full_instruction_prompt"] and
                existing_config["timezone"] == config_data["timezone"] and
                existing_config["message_limit"] == config_data["message_limit"]):
                logger.info("ℹ️ Config unchanged - skipping config save")
                config_needs_update = False
        else:
            logger.info("ℹ️ No existing config found - will create new one")

        # Step 3: Save the updated/new config (only if changed)
        if config_needs_update:
            logger.info("🔄 Saving updated/new user config...")
            try:
                config_save_result = await save_user_config(user_id, config_data)
                if config_save_result:
                    logger.info("✅ Successfully saved user config")
                else:
                    logger.warning("⚠️ Config save returned False - but continuing with schedule creation")
            except Exception as e:
                logger.error(f"❌ Failed to save user config: {e}", exc_info=True)
                return {
                    "next": "schedule_failure",
                    "final_outcome": "Failed to save your preferences. Please try again."
                }        # Step 4: Create the schedule using existing function
        logger.info("🔄 Creating schedule in database...")
        try:
            # Check for existing active schedule for this user
            existing_schedules = await find_schedules(user_id=user_id, query_params={"status": ScheduleStatus.ACTIVE.value})
            if existing_schedules:
                # Update the first active schedule
                existing_schedule = existing_schedules[0]
                schedule_id = str(existing_schedule.id)
                logger.info(f"🔄 Found existing schedule ID: {schedule_id}. Updating it.")
                # Prepare update fields (exclude immutable fields)
                updates = schedule_params.copy()
                updates.pop('user_id', None)
                update_result = await update_schedule_by_id(schedule_id, updates)
                if update_result:
                    logger.info(f"✅ Successfully updated schedule with ID: {schedule_id}")
                else:
                    logger.warning(f"⚠️ Schedule ID: {schedule_id} not updated (no changes applied).")
            else:
                # No existing schedule - create a new one
                schedule_obj = Schedule(**schedule_params)
                schedule_creation_result = await create_schedule_definition(schedule_obj)
                if schedule_creation_result:
                    schedule_id = schedule_creation_result
                    logger.info(f"✅ Successfully created schedule with ID: {schedule_id}")
                else:
                    logger.error("❌ Schedule creation returned None/False")
                    return {
                        "next": "schedule_failure", 
                        "final_outcome": "Failed to create or update the schedule in the database."
                    }
             
            # Step 5: Enqueue the Celery task for the next run
            next_run_time = schedule_params["next_run_at"]
            logger.info(f"🔄 Scheduling Celery task for: {next_run_time}")
            try:
                # Use Celery's send_task with eta (estimated time of arrival)
                task_result = celery_app01.send_task(
                    "src.task.send_reminder_notification",
                    args=[str(schedule_id)],
                    eta=next_run_time
                )
                logger.info(f"✅ Celery task scheduled with ID: {task_result.id}")

                return {
                    "next": "schedule_success",
                    "final_outcome": f"✅ Perfect! I've set up your '{schedule_params['name']}' reminder and saved your preferences. The first reminder will be sent on {next_run_time.strftime('%Y-%m-%d at %H:%M %Z')}.",
                    "schedule_id": str(schedule_id),
                    "next_run_at": next_run_time.isoformat(),
                    "celery_task_id": task_result.id
                }
            except Exception as celery_error:
                logger.error(f"❌ Failed to schedule Celery task: {celery_error}", exc_info=True)
                return {
                    "next": "schedule_failure",
                    "final_outcome": "Schedule was created but failed to queue the reminder task."
                }
            
        except Exception as db_error:
             logger.error(f"❌ Database error during create/update schedule: {db_error}", exc_info=True)
             return {
                 "next": "schedule_failure",
                 "final_outcome": "Database error occurred while creating or updating the schedule."
             }

    except Exception as e:
        logger.error(f"❌ Unexpected error in schedule_reminder_task: {e}", exc_info=True)
        return {
            "next": "schedule_failure",
            "final_outcome": "An unexpected error occurred while processing your schedule request."
        }


# --- Functions for managing existing schedules ---

async def list_schedules_for_user(user_id: str) -> List[Schedule]:
    """
    Fetches and returns all active schedules for a given user.
    Raises DatabaseError on critical errors.
    """
    try:
        logger.info(f"Listing active schedules for user: {user_id}")
        # find_schedules now accepts user_id as an explicit argument
        schedules = await find_schedules(user_id=user_id, query_params={"status": ScheduleStatus.ACTIVE.value})
        logger.info(f"Found {len(schedules)} active schedules for user {user_id}.")
        return schedules
    except DatabaseError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error listing schedules for user {user_id}: {e}", exc_info=True)
        raise DatabaseError(f"Error listing schedules: {e}") from e

async def update_existing_schedule(schedule_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """
    Updates an existing schedule in the database.
    Performs validation on updates to ensure data integrity.
    This will likely trigger a Celery Beat reload in a full system.
    """
    logger.info(f"Attempting to update schedule ID: {schedule_id} with updates: {updates}")
    try:
        # Fetch existing schedule to apply partial updates and re-validate
        existing_schedule = await get_schedule_by_id(schedule_id)
        if not existing_schedule:
            logger.warning(f"Schedule with ID {schedule_id} not found for update.")
            return {"status": "failure", "message": f"Schedule with ID {schedule_id} not found."}

        # Apply updates to a temporary Schedule object for validation
        temp_schedule_dict = existing_schedule.model_dump()
        for key, value in updates.items():
            if key in temp_schedule_dict:
                temp_schedule_dict[key] = value
            else:
                logger.warning(f"Attempted to update non-existent field: {key}")

        # Re-validate the full schedule object with updates via Pydantic
        # This will catch type errors or invalid values for enums
        try:
            updated_schedule_model = Schedule(**temp_schedule_dict)
        except Exception as e:
            logger.error(f"Validation error applying updates to schedule {schedule_id}: {e}", exc_info=True)
            return {"status": "failure", "message": f"Invalid update data provided: {e}"}

        # If schedule_type or schedule_value changed, re-calculate rrule_params and next_run_at
        recalculate_rrule = False
        if "schedule_type" in updates or "schedule_value" in updates:
            recalculate_rrule = True

        if recalculate_rrule:
            logger.debug(f"Recalculating rrule_params and next_run_at for schedule {schedule_id} due to type/value change.")
            rrule_generator = RRuleGenerator(
                schedule_type=updated_schedule_model.schedule_type.value,
                schedule_value=updated_schedule_model.schedule_value,
                user_timezone_str=updated_schedule_model.timezone
            )
            try:
                updated_schedule_model.rrule_params = rrule_generator.generate_rrule_params()
                updated_schedule_model.next_run_at = rrule_generator.calculate_initial_next_run_at()
            except ScheduleClarificationNeeded as e:
                 logger.warning(f"Clarification needed during update rrule recalculation: {e.missing_field} - {e.message}")
                 # This is a complex case: update logic might need to signal clarification
                 # For now, treat as failure, LangGraph would need to initiate a new clarification flow.
                 question = await get_llm_clarification_question(e.clarification_prompt_key or e.missing_field)
                 return {"status": "clarification_needed",
                         "question": question,
                         "missing_field": e.missing_field}

        # Convert model back to dict for database update, excluding _id and created_at
        db_updates = updated_schedule_model.model_dump(by_alias=True, exclude_unset=True, exclude={'_id', 'created_at'})

        # Perform the actual database update
        success = await update_schedule_by_id(schedule_id, db_updates)

        if success:
            logger.info(f"✅ Schedule ID: {schedule_id} updated successfully in DB.")
            return {"status": "success", "message": f"Schedule '{updated_schedule_model.name}' updated successfully."}
        else:
            logger.warning(f"Failed to update schedule ID: {schedule_id} in DB.")
            return {"status": "failure", "message": "Failed to update schedule. It might not exist or no changes were made."}

    except DatabaseError as e:
        logger.error(f"Database error updating schedule {schedule_id}: {e}", exc_info=True)
        return {"status": "failure", "message": "A database error occurred while updating the schedule."}
    except Exception as e:
        logger.error(f"Unexpected error updating schedule {schedule_id}: {e}", exc_info=True)
        return {"status": "failure", "message": "An unexpected error occurred while updating the schedule."}


async def deactivate_and_delete_schedule(schedule_id: str, soft_delete: bool = True) -> Dict[str, Any]:
    """
    Deactivates or permanently deletes a schedule.
    Soft delete (setting status to 'inactive') is preferred.
    """
    logger.info(f"Attempting to {'deactivate' if soft_delete else 'delete'} schedule ID: {schedule_id}")
    try:
        success = False
        message_prefix = "Schedule"
        if soft_delete:
            success = await deactivate_schedule_by_id(schedule_id)
            message_prefix = "Schedule deactivated"
        else:
            success = await delete_schedule_by_id(schedule_id)
            message_prefix = "Schedule deleted permanently"

        if success:
            logger.info(f"✅ {message_prefix} ID: {schedule_id}.")
            return {"status": "success", "message": f"{message_prefix} successfully."}
        else:
            logger.warning(f"Failed to {'deactivate' if soft_delete else 'delete'} schedule ID: {schedule_id}.")
            return {"status": "failure", "message": f"Failed to {'deactivate' if soft_delete else 'delete'} schedule. It might not exist."}

    except DatabaseError as e:
        logger.error(f"Database error {'deactivating' if soft_delete else 'deleting'} schedule {schedule_id}: {e}", exc_info=True)
        return {"status": "failure", "message": f"A database error occurred while {'deactivating' if soft_delete else 'deleting'} the schedule."}
    except Exception as e:
        logger.error(f"Unexpected error {'deactivating' if soft_delete else 'deleting'} schedule {schedule_id}: {e}", exc_info=True)
        return {"status": "failure", "message": f"An unexpected error occurred while {'deactivating' if soft_delete else 'deleting'} the schedule."}


logger.info("✅ Robust LLM structured scheduling parameter parsing, validation, and outcome signaling logic implemented.")