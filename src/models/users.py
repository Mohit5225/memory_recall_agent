# src/models/user.py
from pydantic import BaseModel, Field, BeforeValidator, ConfigDict
from typing import Optional, Annotated, List
from bson import ObjectId
from datetime import datetime, timezone

# --- Custom Pydantic Type for ObjectId Handling ---
def validate_objectid(v):
    """Validate and convert ObjectId for Pydantic"""
    if isinstance(v, ObjectId):
        return v
    if isinstance(v, str) and ObjectId.is_valid(v):
        return ObjectId(v)
    raise ValueError("Invalid ObjectId")

# Use Annotated for Pydantic v2 validation
PyObjectId = Annotated[ObjectId, BeforeValidator(validate_objectid)]

# --- Dedicated Model for Nested Configuration ---
# Provides better structure, type hinting, and validation for config data.
# As suggested by the review.
class UserConfig(BaseModel):
    """Configuration and state for a user."""
    full_instruction_prompt: str = ""
    message_limit: int = Field(default=10)  # Max messages to keep in history
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    timezone: str = Field(default="UTC")

    model_config = ConfigDict(arbitrary_types_allowed=True)

# --- Main User Model ---
# Represents the structure of a user document in MongoDB.
# Uses the custom PyObjectId and the nested UserConfig model.
class User(BaseModel):
    """User model with Google OAuth integration."""
    # Map MongoDB's _id to a Pydantic field named 'id'
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
      # Primary user identifier - uses Google's sub for consistency across the system
    user_id: str = Field(..., description="Google's unique user identifier (sub) - used as primary key")
    
    # Display name from Google (can have duplicates, used for UI)
    display_name: str = Field(..., description="Display name from Google profile")
    
    # User's email from Google
    email: str = Field(..., description="User's email from Google")
    
    # Auth and profile fields
    roles: List[str] = Field(default_factory=lambda: ["user"])
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_login: Optional[datetime] = None
    
    # Embed configuration using the dedicated UserConfig model
    config: UserConfig = Field(default_factory=UserConfig)


    # Future fields for auth and user profile (as suggested by review):
    # email: Optional[str] = None
    # password_hash: Optional[str] = None
    # created_at: datetime = Field(default_factory=datetime.utcnow) # Requires datetime import
    # updated_at: datetime = Field(default_factory=datetime.utcnow) # Requires datetime import
    # roles: List[str] = Field(default_factory=list) # For role-based access control, requires List import
    # last_login: Optional[datetime] = None # For activity logging, requires datetime import


    # Pydantic model configuration
    model_config = ConfigDict(
        # This allows Pydantic to populate fields using aliases (_id -> id)
        populate_by_name = True,
        # Allow ObjectId and other MongoDB types that Pydantic might not
        # natively validate without explicit rules. Essential for PyObjectId.
        arbitrary_types_allowed = True,
        # Support mapping from ORM objects or dictionaries using attribute/field names.
        # Useful when creating model from DB dicts.
        from_attributes = True,
        # Configure JSON encoding for ObjectId to string
        json_encoders = {ObjectId: str}, # Note: In Pydantic v2, json_encoders is within ConfigDict
        # Add an example for documentation/schema generation
        json_schema_extra = {
            "example": {
                "user_id": "test_user_123",
                "config": {
                    "full_instruction_prompt": "# My Custom Reminder Config\nTopic: Python\nStyle: Witty",
                    "message_limit": 10,
                    "timezone": "UTC"
                }
            }
        },
    )


# Add imports needed for future fields if you add them to the model definition
# from datetime import datetime
# from typing import List