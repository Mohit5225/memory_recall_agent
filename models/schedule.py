# src/models/schedule.py
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Annotated, Dict, Any
from bson import ObjectId
from datetime import datetime
from .users import PyObjectId # Reuse the custom ObjectId type

# --- Model for a Stored Schedule Entry ---
# This defines the structure of a document in a new 'schedules' collection in MongoDB.
class Schedule(BaseModel):
    # MongoDB's _id
    id: Optional[PyObjectId] = Field(alias="_id", default=None)

    # Link back to the user this schedule belongs to
    user_id: str = Field(...)

    # The type of schedule recurrence (e.g., "daily", "weekly", "monthly", "once")
    # Or store a more complex parsed rule structure if needed
    recurrence_rule: str = Field(...)

    # Status of the schedule (e.g., "active", "paused", "completed", "cancelled")
    status: str = Field(default="active")

    # Store the *next* time this schedule is due to trigger a task
    # This helps the external scheduler query efficiently
    next_run_at: Optional[datetime] = Field(default=None)

    # Store the user's prompt ID or other config reference used for this schedule batch (Future)
    # config_id: Optional[PyObjectId] = None

    # Store the ID of the active batch generated for this schedule (Future)
    # active_batch_id: Optional[PyObjectId] = None # Links to a future 'reminder_batches' collection

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now) # Use datetime.now for timezone-aware
    updated_at: datetime = Field(default_factory=datetime.now) # Use datetime.now


    model_config = ConfigDict(
        populate_by_name = True,
        arbitrary_types_allowed = True, # For ObjectId and datetime
        from_attributes = True,
        json_encoders = {ObjectId: str, datetime: lambda v: v.isoformat()}, # Encode ObjectId and datetime
        json_schema_extra = {
            "example": {
                "user_id": "test_user_123",
                "recurrence_rule": "daily",
                "status": "active",
                "next_run_at": "2025-05-16T10:00:00+00:00",
                "created_at": "2025-05-15T10:00:00+00:00",
                "updated_at": "2025-05-15T10:00:00+00:00",
            }
        },
    )