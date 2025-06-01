# src/models/schedule.py
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Annotated, Dict, Any
from bson import ObjectId
from datetime import datetime, timezone # Import timezone for UTC operations
from .users import PyObjectId # Reuse the custom ObjectId type
from dateutil.rrule import rrule, rruleset, DAILY, WEEKLY, MONTHLY, YEARLY, MO, TU, WE, TH, FR, SA, SU

# --- Model for a Stored Schedule Entry ---
# This defines the structure of a document in MongoDB
class Schedule(BaseModel):
    # MongoDB's _id - now explicitly uses PyObjectId and handles the alias
    id: Optional[PyObjectId] = Field(alias="_id", default=None)

    # Link back to the user this schedule belongs to
    user_id: str = Field(...)

    # A user-friendly name for the schedule (e.g., "Daily AI Update Reminder")
    # This is new and crucial for user interaction and disambiguation
    name: Optional[str] = Field(default=None)

    # The type of schedule recurrence (e.g., "daily", "weekly", "one-time", "interval")
    # This remains similar but will be a parsed value from user input
    schedule_type: str = Field(...) # Renamed from recurrence_rule for clarity in DB context

    # The detailed schedule value, e.g., {"time": "09:00"} or {"day_of_week": "Monday", "time": "10:00"}
    # This is where the 'sophisticated' rule details live - primarily for display/auditing the LLM's raw parse
    schedule_value: Dict[str, Any] = Field(...)

    # --- NEW: The precise, machine-readable recurrence rule parameters for dateutil.rrule ---
    # This is derived from schedule_value in src/core/scheduler.py,
    # ensuring clean data for the Celery Beat scheduler.
    rrule_params: Optional[Dict[str, Any]] = Field(default=None)

    # Status of the schedule (e.g., "active", "paused", "completed", "cancelled")
    # This is critical for filtering and management
    status: str = Field(default="active")

    # The ObjectId reference to the full_instruction_prompt used for content generation
    # This links the schedule to the specific instructions for generating its reminder content
    reminder_content_prompt_id: PyObjectId = Field(...) # This should be a link to a user's config prompt ID

    # Store the ID assigned by Celery Beat for this persistent task
    # ESSENTIAL for updating or deleting the Celery task later
    celery_task_id: Optional[str] = Field(default=None)

    # Store the *next* time this schedule is due to trigger a task
    # This helps the external scheduler query efficiently
    # This will be calculated in src/core/scheduler.py upon creation, and updated by Celery Beat after each run.
    next_run_at: Optional[datetime] = Field(default=None)

    # --- NEW: Store the *last* time this schedule triggered a task ---
    # Critical for calculating the next run for recurring schedules using rrule.
    # Updated by Celery Beat after each successful task execution.
    last_run_at: Optional[datetime] = Field(default=None)

    # Timestamps - now using datetime.utcnow() for consistency with MongoDB's UTC storage
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_modified_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(
        populate_by_name = True,
        arbitrary_types_allowed = True, # For ObjectId, datetime, and rrule constants
        from_attributes = True,
        json_encoders = {
            ObjectId: str,
            datetime: lambda v: v.isoformat(),
            # Custom encoder for rrule constants if they appear in rrule_params
            # This ensures that rrule.DAILY (int 0) is correctly stored/retrieved if we store ints directly
            # For human-readable, we might convert them to strings like "DAILY" before storing.
            # For now, we'll assume direct int/str storage based on rrule's expected inputs.
        },
        json_schema_extra = {
            "example": {
                "user_id": "test_user_123",
                "name": "Daily Standup Reminder",
                "schedule_type": "daily",
                "schedule_value": {"time": "09:00"},
                "rrule_params": {
                    "freq": DAILY, # Stored as int 0
                    "byhour": [9],
                    "byminute": [0],
                    "bysecond": [0],
                    "dtstart": "2025-05-27T09:00:00Z"
                },
                "status": "active",
                "reminder_content_prompt_id": "60d5ec49f0f9b6c7a4d9e0e1", # Example ObjectId
                "celery_task_id": "celery-schedule-task-abcdef123",
                "next_run_at": "2025-05-27T09:00:00Z", # 'Z' for UTC
                "last_run_at": None, # Initially null
                "created_at": "2025-05-27T08:00:00Z",
                "last_modified_at": "2025-05-27T08:00:00Z",
            }
        },
    )