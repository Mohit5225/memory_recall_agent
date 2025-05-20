# src/core/scheduler.py


from celery_config.Celery_app import celery_app01  # Import the Celery app from our main task module
# Define actual task later: from src.task import generate_reminder_batch_task

# Import DB functions and Schedule model, and custom DatabaseError
from  src.db.mongo import save_schedule_definition, get_schedule_definitions, find_due_schedules, DatabaseError
from src.models.schedule import Schedule

import logging
# Import datetime and timezone for timezone-aware operations
from datetime import datetime, timezone
from typing import Optional, Dict, Any
# Import LLM interaction for structured extraction
from src.llm.gemini import get_gemini_response
# Import json for parsing LLM output
import json
# Import dateparser for robust datetime validation/parsing after LLM
import dateparser


logger = logging.getLogger(__name__)

# --- LLM Prompt for Structured Scheduling Parameter Extraction ---
# This prompt instructs the LLM to extract scheduling details and return them as JSON.
# Defines the structure of the expected JSON output and provides examples for clarity.
SCHEDULING_EXTRACTION_PROMPT_TEMPLATE = """
You are a scheduling parameter extraction system for a reminder agent.
Your task is to analyze the user's request to schedule reminders and extract the following details.
Format the extracted information as a JSON object.

Expected JSON Schema:
{{
  "recurrence_rule": "string (one of: daily, weekly, monthly, once, none_other - based on frequency)",
  "schedule_time": "string (e.g., '10:00 AM', 'noon', '3pm', or null if not specified)",
  "schedule_day": "string (e.g., 'Monday', 'Tuesday', 'Friday', or null if not specified - for weekly rules)",
  "schedule_date": "string (e.g., '2025-12-31', 'tomorrow', 'next week', or null if not specified - for start date or 'once' date)",
  "timezone": "string (e.g., 'UTC', 'EST', 'PST', or null if not specified - infer from context or default to UTC if unsure)",
  "end_date": "string (e.g., '2026-01-01', or null if not specified - when the schedule should stop)",
  "notes": "string (any other relevant scheduling details or constraints, or null if none - e.g., 'weekends only', 'every other day')"
}}

If a detail is not specified or is unclear, use 'null'.
Infer timezone from user input if possible, otherwise default to 'UTC'.
Ensure the recurrence_rule is one of the specified categories.
Return ONLY the JSON object. Do NOT include any other text before or after the JSON.

Examples:
User: "Schedule daily reminders for me at 9 AM"
JSON Output:
{{
  "recurrence_rule": "daily",
  "schedule_time": "9:00 AM",
  "schedule_day": null,
  "schedule_date": null,
  "timezone": "UTC",
  "end_date": null,
  "notes": null
}}

User: "Remind me weekly every Tuesday at 3pm"
JSON Output:
{{
  "recurrence_rule": "weekly",
  "schedule_time": "3:00 PM",
  "schedule_day": "Tuesday",
  "schedule_date": null,
  "timezone": "UTC",
  "end_date": null,
  "notes": null
}}

User: "Schedule a reminder just once next Monday at 10:30 AM"
JSON Output:
{{
  "recurrence_rule": "once",
  "schedule_time": "10:30 AM",
  "schedule_day": "Monday",
  "schedule_date": "next Monday",
  "timezone": "UTC",
  "end_date": null,
  "notes": null
}}

User: "Schedule reminders monthly starting Jan 1st 2026"
JSON Output:
{{
  "recurrence_rule": "monthly",
  "schedule_time": null,
  "schedule_day": null,
  "schedule_date": "Jan 1st 2026",
  "timezone": "UTC",
  "end_date": null,
  "notes": null
}}

User: "what is a recursive function?"
JSON Output:
{{
  "recurrence_rule": "none_other",
  "schedule_time": null,
  "schedule_day": null,
  "schedule_date": null,
  "timezone": null,
  "end_date": null,
  "notes": null
}}

User Input: {user_input}

JSON Output:"""


# --- Advanced Scheduling Parameter Parsing (LLM Structured Extraction with Robust Validation) ---
def parse_schedule_parameters(user_input: str) -> Optional[Dict[str, Any]]:
    """
    Uses a targeted LLM call to extract scheduling parameters as JSON.
    Includes comprehensive validation of the LLM's output and date/time strings.

    Args:
        user_input: The raw input string from the user.

    Returns:
        A dictionary containing validated and processed parameters, including
        'recurrence_rule', 'first_run_at' (as datetime or None), and 'parsed_parameters_raw'.
        Returns None if LLM call fails, JSON parsing fails, validation fails,
        or insufficient details are found for a schedule.
    """
    logger.debug(f"Attempting LLM structured scheduling parameter parsing for: '{user_input[:50]}...'")

    llm_prompt = SCHEDULING_EXTRACTION_PROMPT_TEMPLATE.format(user_input=user_input).strip()
    raw_llm_output = None # Initialize raw output for logging in case of JSON error

    try:
        # --- Step 1: Call LLM for Structured Extraction ---
        # Add retry logic here in a production system
        raw_llm_output = get_gemini_response(llm_prompt)

        if raw_llm_output is None:
            logger.error("LLM returned None for structured scheduling extraction.")
            return None # Indicate parsing failure

        logger.debug(f"Raw LLM output for scheduling: {raw_llm_output}")

        # --- Step 2: Parse LLM Output as JSON ---
        # Robustly attempt to parse the JSON output. LLMs can be inconsistent.
        # Use a more robust JSON extraction than simple find('{').
        # Can use regex or look for common JSON patterns if needed.
        # For now, keep simple find and assume the LLM tries to follow instructions.
        json_start = raw_llm_output.find('{')
        json_end = raw_llm_output.rfind('}')

        if json_start == -1 or json_end == -1:
            logger.error("Could not find JSON object in LLM output.")
            return None # Indicate parsing failure (malformed JSON)

        json_string = raw_llm_output[json_start : json_end + 1]
        logger.debug(f"Extracted potential JSON string: {json_string}")

        parsed_params_raw: Dict[str, Any] = json.loads(json_string)
        logger.debug(f"Parsed JSON from LLM: {parsed_params_raw}")

        # --- Step 3: Validate Parsed Parameters Structure ---
        # Check if required keys are present and values are of expected basic types (strings or nulls).
        # This catches LLM hallucinating wrong structure.
        expected_keys_and_types = {
            "recurrence_rule": (str, type(None)),
            "schedule_time": (str, type(None)),
            "schedule_day": (str, type(None)),
            "schedule_date": (str, type(None)),
            "timezone": (str, type(None)),
            "end_date": (str, type(None)),
            "notes": (str, type(None))
        }

        if not all(key in parsed_params_raw and isinstance(parsed_params_raw[key], expected_keys_and_types[key]) for key in expected_keys_and_types):
             logger.error(f"LLM output JSON missing keys or invalid types. Expected: {expected_keys_and_types}. Received: {parsed_params_raw}")
             return None # Indicate validation failure (invalid structure)


        # --- Step 4: Validate and Standardize Recurrence Rule ---
        valid_rules = ["daily", "weekly", "monthly", "once", "none_other"]
        classified_rule = parsed_params_raw.get("recurrence_rule", "none_other") # Default if key missing or value is None
        if not isinstance(classified_rule, str) or classified_rule.lower() not in valid_rules:
            logger.warning(f"LLM output contained invalid or non-string recurrence_rule: {classified_rule}. Treating as 'none_other'.")
            classified_rule = "none_other" # Treat invalid classification as none_other
        else:
            classified_rule = classified_rule.lower() # Standardize to lowercase


        # --- Step 5: Process Date/Time Strings into datetime objects using dateparser ---
        # Use dateparser to robustly parse the date/time strings provided by the LLM.
        # This adds robustness even if the LLM's string format varies or is vague.
        final_params: Dict[str, Any] = {}
        final_params["recurrence_rule"] = classified_rule # Use the validated/standardized rule

        # Combine date and time strings from LLM if both exist
        datetime_string_parts = []
        if parsed_params_raw.get("schedule_date"):
             datetime_string_parts.append(str(parsed_params_raw.get("schedule_date")))
        if parsed_params_raw.get("schedule_time"):
             datetime_string_parts.append(str(parsed_params_raw.get("schedule_time")))
        # Also include day if specified, as dateparser can use it (e.g., "Tuesday at 10 AM")
        if parsed_params_raw.get("schedule_day") and not parsed_params_raw.get("schedule_date"):
             datetime_string_parts.append("on " + str(parsed_params_raw.get("schedule_day")))


        combined_datetime_string = " ".join(datetime_string_parts).strip()
        parsed_first_run_at = None
        now_utc = datetime.now(timezone.utc)

        if combined_datetime_string:
             # Attempt to parse the combined string using dateparser
             # Use the timezone provided by LLM, defaulting to UTC if null/invalid/unparsable
             llm_timezone_str = parsed_params_raw.get("timezone") or 'UTC'
             try:
                 # Use dateparser settings for timezone and awareness
                 settings = {'TIMEZONE': llm_timezone_str, 'RETURN_AS_TIMEZONE_AWARE': True}
                 temp_dt = dateparser.parse(combined_datetime_string, settings=settings)

                 if temp_dt:
                     # Ensure it's timezone-aware UTC for storage
                     parsed_dt_utc = temp_dt.astimezone(timezone.utc)

                     # Only consider explicit future times as potential first_run_at
                     # If the parsed time is in the past or now, we might ignore it as an explicit start,
                     # especially for recurring rules where the scheduler calculates the next from 'now'.
                     # However, for 'once', past time is a failure.
                     if parsed_dt_utc > now_utc:
                         parsed_first_run_at = parsed_dt_utc
                         logger.debug(f"✅ Parsed first run time string '{combined_datetime_string}' as {parsed_first_run_at} (UTC).")
                     else:
                         logger.debug(f"Parsed time string '{combined_datetime_string}' resulted in past/now time {parsed_dt_utc}. Not using as explicit first_run_at.")

                 else:
                     logger.warning(f"Could not parse combined datetime string '{combined_datetime_string}' using dateparser.")

             except Exception as e:
                  logger.error(f"Error parsing combined datetime string '{combined_datetime_string}' using dateparser: {e}", exc_info=True)
                  parsed_first_run_at = None # Ensure None on error


        final_params["first_run_at"] = parsed_first_run_at

        # --- Step 6: Final Validation for Sufficiency ---
        # Now check if the parsed/validated data is sufficient for a schedule request.
        # This is the crucial check to avoid saving nonsensical schedules.

        is_sufficient = False
        final_validation_reason = "Insufficient details" # Default reason

        if final_params.get("recurrence_rule") == "once":
            # For a 'once' schedule, we absolutely MUST have a valid future first_run_at time.
            if final_params.get("first_run_at") is not None:
                is_sufficient = True
                final_validation_reason = "Once schedule with valid time"
            else:
                final_validation_reason = "Once rule classified, but no valid future time found."

        elif final_params.get("recurrence_rule") in ["daily", "weekly", "monthly"]:
            # For recurring schedules, having a recognized rule is sufficient.
            # The external scheduler can calculate the next run based on the rule starting from now
            # if an explicit first_run_at wasn't provided or was in the past.
             is_sufficient = True
             final_validation_reason = f"Recurring rule '{final_params.get('recurrence_rule')}' classified."

        else: # Includes "none_other" and any other cases not mapped to supported rules
            final_validation_reason = f"Input classified as '{final_params.get('recurrence_rule')}' which is not a supported schedule type or 'none_other'."


        if not is_sufficient:
            logger.warning(f"Final validation failed: {final_validation_reason}. Input: '{user_input[:50]}...'")
            return None # Indicate parsing/validation failure

        # Store raw parsed parameters from LLM output for debugging/auditing
        final_params["parsed_parameters_raw"] = parsed_params_raw


        logger.debug(f"✅ Final validated and parsed schedule parameters: {final_params}. Reason: {final_validation_reason}")
        return final_params

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM output as JSON: {e}. Raw Output: {raw_llm_output}", exc_info=True)
        return None # Indicate parsing failure
    except Exception as e:
        logger.error(f"Unexpected error during LLM parsing/validation for input '{user_input[:50]}...': {e}", exc_info=True)
        return None # Indicate parsing failure


# --- Function to Schedule a Reminder Task via Celery (Handles parsing outcome) ---
def schedule_reminder_task(user_id: str, user_input: str) -> Dict[str, Any]:
    """
    Parses schedule info using LLM structured extraction, saves definition to DB.
    Returns a dictionary indicating outcome for LangGraph.
    Raises DatabaseError if DB operation fails critically.
    """
    logger.info(f"Attempting to process schedule request for user: {user_id} with input: '{user_input[:50]}...'")

    # Default outcomes
    outcome_key = "schedule_failure"
    final_outcome = "Scheduling failed." # Default user-friendly message

    try:
        # --- Step 1: Parse Parameters (LLM Structured Extraction with Validation) ---
        # This function now returns None if parsing/validation fails due to insufficient details
        parsed_params = parse_schedule_parameters(user_input)

        if parsed_params is None:
            logger.warning(f"Schedule parsing failed or insufficient details provided for input: '{user_input}'")
            # Set specific outcome for parsing failure
            outcome_key = "schedule_parsing_failed"
            final_outcome = "Sorry, I couldn't understand the scheduling details. Please provide a clear time or frequency (like 'daily', 'weekly', 'tomorrow at 10 AM')." # User-friendly message
            # No DB operation needed if parsing failed
            return {"next": outcome_key, "final_outcome": final_outcome}

        # Extract validated parameters (if parsing succeeded)
        recurrence_rule = parsed_params.get("recurrence_rule")
        first_run_at = parsed_params.get("first_run_at")
        parsed_parameters_raw = parsed_params.get("parsed_parameters_raw")

        # --- Step 2: Create/Update Schedule Definition in DB (Only if parsing succeeded) ---
        # Ensure we have a valid rule to save (should be guaranteed by parse_schedule_parameters returning non-None)
        if not recurrence_rule or recurrence_rule == "none_other":
             # This case should be caught by parse_schedule_parameters returning None, but double-check for robustness
             logger.error(f"Internal error: parsed_params is not None, but rule is invalid: {recurrence_rule}")
             outcome_key = "schedule_failure"
             final_outcome = "An internal error occurred during scheduling."
             return {"next": outcome_key, "final_outcome": final_outcome}


        schedule_definition = Schedule(
            user_id=user_id,
            recurrence_rule=recurrence_rule, # Use the LLM-classified rule
            status="active",
            # Set next_run_at if a specific future time was parsed and validated.
            # If None, the external scheduler will calculate the first run based on the rule from now.
            next_run_at=first_run_at,
            # Store raw parsed parameters for auditing LLM output
            parsed_parameters_raw=parsed_parameters_raw,
        )

        # Save the schedule definition to MongoDB. This function raises DatabaseError on failure.
        schedule_id = save_schedule_definition(schedule_definition)

        # If save_schedule_definition returns an ObjectId, it was successful
        if schedule_id:
            logger.info(f"✅ Schedule definition saved/updated in DB. Schedule ID: {schedule_id}")
            outcome_key = "schedule_success"
            final_outcome = "Schedule saved successfully. I will send reminders based on your request." # User-friendly success message
            # The external scheduler will now find this definition and trigger tasks.
            return {"next": outcome_key, "final_outcome": final_outcome}
        else:
             # save_schedule_definition should raise on failure, but as a fallback for non-critical PyMongoErrors
             logger.error(f"Failed to save schedule definition for user {user_id}.")
             outcome_key = "schedule_failure"
             final_outcome = "Failed to save your schedule. Please try again." # Specific failure message
             return {"next": outcome_key, "final_outcome": final_outcome}


    except DatabaseError as e:
        # Catch specific DatabaseErrors raised by save_schedule_definition
        logger.error(f"Database error during schedule definition process for user {user_id}: {e}", exc_info=True)
        # Set specific outcome for database failure
        return {"next": "schedule_db_error", "final_outcome": f"A database error prevented saving your schedule."}
    except Exception as e:
        # Catch any other unexpected exceptions during the process before/during DB call
        logger.error(f"Unexpected error during schedule definition process for user {user_id}: {e}", exc_info=True)
        # This is an unexpected failure *after* parsing attempt, but before DB commit logic fully resolves
        outcome_key = "schedule_exception"
        final_outcome = f"An internal system error occurred while processing your scheduling request."
        # Return outcome key for the graph to handle gracefully.
        return {"next": outcome_key, "final_outcome": final_outcome}


# --- Functions needed for the external scheduler (No changes) ---
# def find_due_schedules(): ... # Defined in src/db/mongo.py
# def calculate_next_run_time(schedule: Schedule) -> datetime: ... # Needs implementation later
# def trigger_scheduled_task(schedule: Schedule): ... # Needs implementation later


logger.info("✅ Robust LLM structured scheduling parameter parsing, validation, and outcome signaling logic implemented.")