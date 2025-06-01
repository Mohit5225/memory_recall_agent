# src/core/scheduler.py
from celery_config.Celery_app import celery_app01
from src.db.mongo import create_schedule_definition, get_schedule_by_id, find_schedules, update_schedule_by_id, delete_schedule_by_id, deactivate_schedule_by_id, DatabaseError
from src.models.schedule import Schedule, PyObjectId, ScheduleType, ScheduleStatus # Import all relevant enums/models
from src.llm.gemini import get_gemini_response_async # Assuming this is available and works
import logging
from datetime import datetime, timedelta, timezone
import json
import dateparser
from typing import Optional, Dict, Any, List, Tuple
from dateutil.rrule import rrule, rrulestr, YEARLY, MONTHLY, WEEKLY, DAILY, HOURLY, MINUTELY, SECONDLY, MO, TU, WE, TH, FR, SA, SU
import pytz # For timezone conversions

logger = logging.getLogger(__name__)

# --- Custom Exception for Clarification Needed ---
class ScheduleClarificationNeeded(Exception):
    """Custom exception raised when more information is needed to define a schedule."""
    def __init__(self, message: str, missing_field: str, clarification_prompt_key: str = None):
        super().__init__(message)
        self.missing_field = missing_field
        self.clarification_prompt_key = clarification_prompt_key or missing_field # Key for specific LLM prompt

# --- LLM Prompt for Structured Scheduling Parameter Extraction ---
SCHEDULING_EXTRACTION_PROMPT_TEMPLATE = """
You are a scheduling parameter extraction system for a reminder agent.
Your task is to analyze the user's request to schedule reminders and extract the following details.
Format the extracted information as a JSON object.

Expected JSON Schema:
{{
  "name": "string (a concise, human-readable name for the reminder, e.g., 'Daily AI Update', 'Tuesday Meeting Reminder')",
  "schedule_type": "string (one of: daily, weekly, monthly, once, interval, none_other - based on frequency or specific dates)",
  "schedule_value": "object (details for the schedule_type, e.g., {{"time": "10:00"}} for daily, {{"day_of_week": "Monday", "time": "09:00"}} for weekly, {{"date": "2025-12-31", "time": "14:00"}} for once, {{"interval": 2, "unit": "days"}} for interval. Empty object if not specified)",
  "timezone": "string (e.g., 'UTC', 'Asia/Kolkata', 'America/New_York' - infer from context or default to 'Asia/Kolkata' if unsure, use IANA format)",
  "reminder_content_prompt_id": "string (The MongoDB ObjectId as a string for the full instruction prompt that defines the reminder content)",
  "notes": "string (any other relevant scheduling details or constraints, or null if none - e.g., 'weekends only', 'every other day')"
}}

If a detail is not specified or is unclear, use 'null' for string/object fields, or infer sensible defaults.
Infer timezone from user input if possible, otherwise default to 'Asia/Kolkata'.
Ensure the schedule_type is one of the specified categories.
The 'schedule_value' object should contain the specific details for the chosen 'schedule_type'.
Return ONLY the JSON object. Do NOT include any other text before or after the JSON.

Examples:
User: "Schedule a daily AI update reminder at 9 AM IST and use the prompt ID abcdef123456789012345678"
JSON Output:
{{
  "name": "Daily AI Update Reminder",
  "schedule_type": "daily",
  "schedule_value": {{"time": "09:00 AM"}},
  "timezone": "Asia/Kolkata",
  "reminder_content_prompt_id": "abcdef123456789012345678",
  "notes": null
}}

User: "Remind me weekly every Tuesday at 3pm PST about the team sync using prompt ID fedcba987654321098765432"
JSON Output:
{{
  "name": "Team Sync Reminder",
  "schedule_type": "weekly",
  "schedule_value": {{"day_of_week": "Tuesday", "time": "3:00 PM"}},
  "timezone": "America/Los_Angeles",
  "reminder_content_prompt_id": "fedcba987654321098765432",
  "notes": null
}}

User: "Schedule a one-time reminder for my project deadline on 2025-06-30 at 5 PM using prompt ID 1234567890abcdef12345678"
JSON Output:
{{
  "name": "Project Deadline Reminder",
  "schedule_type": "once",
  "schedule_value": {{"date": "2025-06-30", "time": "5:00 PM"}},
  "timezone": "Asia/Kolkata",
  "reminder_content_prompt_id": "1234567890abcdef12345678",
  "notes": null
}}

User: "Remind me every 3 hours about stretching using prompt ID 11111111112222222222333333"
JSON Output:
{{
  "name": "Stretching Reminder",
  "schedule_type": "interval",
  "schedule_value": {{"interval": 3, "unit": "hours"}},
  "timezone": "Asia/Kolkata",
  "reminder_content_prompt_id": "11111111112222222222333333",
  "notes": null
}}

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
        Raises ScheduleClarificationNeeded if required information is missing.
        """
        rrule_params: Dict[str, Any] = {}
        hour, minute, second = None, None, None
        time_str = self.schedule_value.get("time")
        if time_str:
            hour, minute, second = self._parse_time(time_str)
            if hour is None or minute is None:
                raise ScheduleClarificationNeeded(
                    f"Invalid time format detected: {time_str}",
                    missing_field="time",
                    clarification_prompt_key="invalid_time_format"
                )
            rrule_params['byhour'] = [hour]
            rrule_params['byminute'] = [minute]
            rrule_params['bysecond'] = [second if second is not None else 0] # Default seconds to 0

        if self.schedule_type == ScheduleType.ONCE.value:
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
                )
            # For 'once' schedules, we don't generate rrule_params directly,
            # but rather a specific datetime for next_run_at.
            # We'll handle this special case in _calculate_next_run_at.
            return {} # No rrule params for 'once'

        elif self.schedule_type == ScheduleType.DAILY.value:
            rrule_params['freq'] = DAILY
            if hour is None or minute is None:
                raise ScheduleClarificationNeeded(
                    "Time is required for a daily schedule.",
                    missing_field="time",
                    clarification_prompt_key="missing_time_for_daily"
                )

        elif self.schedule_type == ScheduleType.WEEKLY.value:
            rrule_params['freq'] = WEEKLY
            day_of_week_str = self.schedule_value.get("day_of_week")
            if not day_of_week_str:
                raise ScheduleClarificationNeeded(
                    "Day of the week (e.g., Monday) is required for a weekly schedule.",
                    missing_field="day_of_week",
                    clarification_prompt_key="missing_day_for_weekly"
                )
            byweekday = self.DAY_MAP.get(day_of_week_str.lower())
            if byweekday is None:
                raise ScheduleClarificationNeeded(
                    f"Invalid day of week: {day_of_week_str}. Please provide a valid day (e.g., Monday).",
                    missing_field="day_of_week",
                    clarification_prompt_key="invalid_day_format"
                )
            rrule_params['byweekday'] = byweekday
            if hour is None or minute is None:
                raise ScheduleClarificationNeeded(
                    "Time is required for a weekly schedule.",
                    missing_field="time",
                    clarification_prompt_key="missing_time_for_weekly"
                )

        elif self.schedule_type == ScheduleType.MONTHLY.value:
            rrule_params['freq'] = MONTHLY
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
                day_of_week_str = self.schedule_value["day_of_week"]
                week_of_month = self.schedule_value["week_of_month"] # e.g., 1, 2, 3, 4, -1
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
async def parse_schedule_parameters_and_clarify(user_input: str) -> Dict[str, Any]:
    """
    Orchestrates the LLM extraction, deterministic RRule parameter generation,
    and handles clarification requests.

    Returns:
        A dictionary with either:
        - {"status": "success", "schedule_params": Dict[str, Any]}
        - {"status": "clarification_needed", "question": str, "missing_field": str}
        - {"status": "failure", "message": str}
    """
    logger.debug(f"Attempting LLM structured scheduling parameter parsing for: '{user_input[:100]}...'")
    raw_llm_output = None
    parsed_params_raw: Optional[Dict[str, Any]] = None

    try:
        llm_prompt = SCHEDULING_EXTRACTION_PROMPT_TEMPLATE.format(user_input=user_input).strip()
        raw_llm_output = await get_gemini_response_async(llm_prompt)

        if raw_llm_output is None:
            logger.error("LLM returned None for structured scheduling extraction.")
            return {"status": "failure", "message": "Failed to get a response from the AI for scheduling details."}

        logger.debug(f"Raw LLM output for scheduling: {raw_llm_output}")

        # Robust JSON extraction
        json_start = raw_llm_output.find('{')
        json_end = raw_llm_output.rfind('}')
        if json_start == -1 or json_end == -1:
            logger.error("Could not find JSON object in LLM output.")
            return {"status": "failure", "message": "The AI provided an unparseable response for scheduling. Please try rephrasing."}
        json_string = raw_llm_output[json_start : json_end + 1]
        
        parsed_params_raw = json.loads(json_string)
        logger.debug(f"Parsed JSON from LLM: {parsed_params_raw}")

        # --- Step 1: Basic Structural Validation of LLM Output ---
        expected_keys_and_types = {
            "name": str,
            "schedule_type": str,
            "schedule_value": dict,
            "timezone": (str, type(None)),
            "reminder_content_prompt_id": str,
            "notes": (str, type(None))
        }

        # Check for mandatory keys and their types (allowing None for optional)
        for key, expected_type in expected_keys_and_types.items():
            value = parsed_params_raw.get(key)
            if value is None and expected_type is not (str, type(None)): # if it's mandatory and None
                 logger.warning(f"Missing mandatory field from LLM: {key}")
                 return {"status": "clarification_needed", 
                         "question": get_llm_clarification_question(key),
                         "missing_field": key}
            if value is not None and not isinstance(value, expected_type):
                logger.warning(f"Invalid type for field '{key}': Expected {expected_type}, got {type(value)}")
                # For `schedule_value` if it's not a dict, it's a severe error
                if key == "schedule_value":
                    parsed_params_raw["schedule_value"] = {} # Default to empty dict
                else:
                    return {"status": "clarification_needed",
                            "question": get_llm_clarification_question(f"invalid_{key}_format"),
                            "missing_field": key}
        
        # Validate ScheduleType enum
        classified_type_str = parsed_params_raw.get("schedule_type", "").lower()
        if classified_type_str not in [e.value for e in ScheduleType]:
            logger.warning(f"LLM output contained invalid schedule_type: {classified_type_str}")
            return {"status": "clarification_needed",
                    "question": get_llm_clarification_question("schedule_type"),
                    "missing_field": "schedule_type"}
        
        schedule_type = ScheduleType(classified_type_str) # Convert to enum

        # Validate reminder_content_prompt_id is a valid ObjectId format
        prompt_id_str = parsed_params_raw.get("reminder_content_prompt_id")
        if not prompt_id_str or not ObjectId.is_valid(prompt_id_str):
            logger.warning(f"Invalid or missing reminder_content_prompt_id: {prompt_id_str}")
            return {"status": "clarification_needed",
                    "question": get_llm_clarification_question("invalid_prompt_id"),
                    "missing_field": "reminder_content_prompt_id"}
        
        # --- Step 2: Generate RRule Parameters and Calculate Next Run ---
        user_timezone = parsed_params_raw.get("timezone") or "Asia/Kolkata" # Default to user's timezone if not specified
        rrule_generator = RRuleGenerator(
            schedule_type=schedule_type.value,
            schedule_value=parsed_params_raw.get("schedule_value", {}),
            user_timezone_str=user_timezone
        )
        
        rrule_params = {}
        initial_next_run_at: Optional[datetime] = None

        if schedule_type == ScheduleType.ONCE:
            # For 'once', rrule_params will be empty, and next_run_at is directly parsed.
            try:
                initial_next_run_at = rrule_generator.calculate_initial_next_run_at()
            except ScheduleClarificationNeeded as e:
                logger.warning(f"Clarification needed for 'once' schedule: {e.missing_field} - {e.message}")
                return {"status": "clarification_needed",
                        "question": get_llm_clarification_question(e.clarification_prompt_key or e.missing_field),
                        "missing_field": e.missing_field}
        else:
            # For recurring schedules, generate rrule_params and then calculate initial_next_run_at
            try:
                rrule_params = rrule_generator.generate_rrule_params()
                initial_next_run_at = rrule_generator.calculate_initial_next_run_at()
            except ScheduleClarificationNeeded as e:
                logger.warning(f"Clarification needed for recurring schedule: {e.missing_field} - {e.message}")
                return {"status": "clarification_needed",
                        "question": get_llm_clarification_question(e.clarification_prompt_key or e.missing_field),
                        "missing_field": e.missing_field}
            except Exception as e:
                logger.error(f"Unexpected error during rrule generation/calculation: {e}", exc_info=True)
                return {"status": "clarification_needed",
                        "question": get_llm_clarification_question("rrule_calculation_error"),
                        "missing_field": "rrule_calculation_error"}

        # Prepare final parameters for Schedule model
        final_params = {
            "name": parsed_params_raw["name"],
            "schedule_type": schedule_type, # This is the enum value
            "schedule_value": parsed_params_raw["schedule_value"], # Keep original LLM output for audit/debug
            "rrule_params": rrule_params, # The parsed rrule parameters
            "next_run_at": initial_next_run_at,
            "last_run_at": None, # Initially null
            "reminder_content_prompt_id": PyObjectId(parsed_params_raw["reminder_content_prompt_id"]),
            "status": ScheduleStatus.ACTIVE, # Default to active upon creation
            "timezone": user_timezone, # Store the identified timezone
            "notes": parsed_params_raw.get("notes"),
        }

        logger.info(f"✅ Successfully parsed and validated schedule parameters. Next run at: {initial_next_run_at}")
        return {"status": "success", "schedule_params": final_params}

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM output as JSON: {e}. Raw Output: {raw_llm_output}", exc_info=True)
        return {"status": "failure", "message": "Failed to understand the schedule. The AI's response was not valid JSON."}
    except Exception as e:
        logger.error(f"Unexpected error during schedule parsing and validation for input '{user_input[:100]}...': {e}", exc_info=True)
        return {"status": "failure", "message": "An unexpected error occurred while trying to parse your schedule details."}


# --- Function to Generate LLM Clarification Question ---
async def get_llm_clarification_question(missing_detail_key: str) -> str:
    """
    Uses an LLM call to generate a natural language clarification question based on a key.
    """
    prompt = CLARIFICATION_PROMPT_TEMPLATE.format(missing_detail_key=missing_detail_key).strip()
    try:
        response = await get_gemini_response_async(prompt)
        if response:
            return response.strip()
        logger.warning(f"LLM returned empty response for clarification key: {missing_detail_key}. Falling back to generic.")
        return "Could you please provide more details to help me schedule this reminder?"
    except Exception as e:
        logger.error(f"Error generating LLM clarification question for '{missing_detail_key}': {e}", exc_info=True)
        return "I need more information to set this reminder. Can you please provide more details?"


# --- Function to Schedule a Reminder Task via Celery (Handles parsing outcome) ---
def schedule_reminder_task(user_id: str, user_input: str) -> Dict[str, Any]:
    """
    Orchestrates the entire scheduling process: parsing, validation, clarification, and DB persistence.
    This is the primary entry point for scheduling a new reminder.

    Returns a dictionary indicating outcome for LangGraph:
    - {"next": "schedule_success", "final_outcome": str, "schedule_id": str}
    - {"next": "awaiting_clarification", "question": str, "missing_field": str}
    - {"next": "schedule_failure", "final_outcome": str}
    """
    logger.info(f"Initiating schedule request for user: {user_id} with input: '{user_input[:100]}...'")

    parsing_result = parse_schedule_parameters_and_clarify(user_input)

    if parsing_result["status"] == "clarification_needed":
        return {
            "next": "awaiting_clarification",
            "question": parsing_result["question"],
            "missing_field": parsing_result["missing_field"]
        }
    elif parsing_result["status"] == "failure":
        return {
            "next": "schedule_failure",
            "final_outcome": parsing_result["message"]
        }
    
    # If status is "success"
    schedule_params = parsing_result["schedule_params"]

    try:
        # Create a Schedule Pydantic model instance
        schedule_definition = Schedule(
            user_id=user_id,
            name=schedule_params["name"],
            schedule_type=schedule_params["schedule_type"],
            schedule_value=schedule_params["schedule_value"],
            rrule_params=schedule_params["rrule_params"], # This is the key addition
            next_run_at=schedule_params["next_run_at"],
            last_run_at=schedule_params["last_run_at"],
            reminder_content_prompt_id=schedule_params["reminder_content_prompt_id"],
            status=schedule_params["status"],
            timezone=schedule_params["timezone"],
            notes=schedule_params["notes"],
        )

        # Use the new create_schedule_definition function from mongo.py
        schedule_id = create_schedule_definition(schedule_definition)

        if schedule_id:
            logger.info(f"✅ Schedule definition saved in DB. Schedule ID: {schedule_id}")
            # In a full Celery Beat integration, you'd now inform Celery Beat
            # to refresh its schedule. This often happens via watching the DB or
            # a custom signal/API endpoint. For now, it's just saved.
            return {
                "next": "schedule_success",
                "final_outcome": f"Schedule '{schedule_params['name']}' saved successfully. I will send reminders based on your request.",
                "schedule_id": str(schedule_id)
            }
        else:
            logger.error(f"Failed to save schedule definition for user {user_id} - create_schedule_definition returned None.")
            return {
                "next": "schedule_failure",
                "final_outcome": "Failed to save your schedule due to an internal database issue. Please try again."
            }

    except DatabaseError as e:
        logger.error(f"Database error during schedule definition process for user {user_id}: {e}", exc_info=True)
        return {"next": "schedule_db_error", "final_outcome": "A database error prevented saving your schedule."}
    except Exception as e:
        logger.error(f"Unexpected error during schedule definition process for user {user_id}: {e}", exc_info=True)
        return {"next": "schedule_exception", "final_outcome": "An internal system error occurred while processing your scheduling request."}


# --- Functions for managing existing schedules ---

def list_schedules_for_user(user_id: str) -> List[Schedule]:
    """
    Fetches and returns all active schedules for a given user.
    Raises DatabaseError on critical errors.
    """
    try:
        logger.info(f"Listing active schedules for user: {user_id}")
        # find_schedules now accepts user_id as an explicit argument
        schedules = find_schedules(user_id=user_id, query_params={"status": ScheduleStatus.ACTIVE.value})
        logger.info(f"Found {len(schedules)} active schedules for user {user_id}.")
        return schedules
    except DatabaseError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error listing schedules for user {user_id}: {e}", exc_info=True)
        raise DatabaseError(f"Error listing schedules: {e}") from e

def update_existing_schedule(schedule_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """
    Updates an existing schedule in the database.
    Performs validation on updates to ensure data integrity.
    This will likely trigger a Celery Beat reload in a full system.
    """
    logger.info(f"Attempting to update schedule ID: {schedule_id} with updates: {updates}")
    try:
        # Fetch existing schedule to apply partial updates and re-validate
        existing_schedule = get_schedule_by_id(schedule_id)
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
                 return {"status": "clarification_needed",
                         "question": get_llm_clarification_question(e.clarification_prompt_key or e.missing_field),
                         "missing_field": e.missing_field}


        # Convert model back to dict for database update, excluding _id and created_at
        db_updates = updated_schedule_model.model_dump(by_alias=True, exclude_unset=True, exclude={'_id', 'created_at'})

        # Perform the actual database update
        success = update_schedule_by_id(schedule_id, db_updates)

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


def deactivate_and_delete_schedule(schedule_id: str, soft_delete: bool = True) -> Dict[str, Any]:
    """
    Deactivates or permanently deletes a schedule.
    Soft delete (setting status to 'inactive') is preferred.
    """
    logger.info(f"Attempting to {'deactivate' if soft_delete else 'delete'} schedule ID: {schedule_id}")
    try:
        success = False
        message_prefix = "Schedule"
        if soft_delete:
            success = deactivate_schedule_by_id(schedule_id)
            message_prefix = "Schedule deactivated"
        else:
            success = delete_schedule_by_id(schedule_id)
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