# src/models/user.py
from pydantic import BaseModel, Field, BeforeValidator, ConfigDict
from typing import Optional, Annotated, Dict, Any
from bson import ObjectId

# --- Custom Pydantic Type for ObjectId Handling ---
# Necessary for Pydantic v2 compatibility and correct serialization/deserialization
# of MongoDB's ObjectId.
# As suggested by the review.
def validate_objectid(v):
    if isinstance(v, ObjectId):
        return v
    if isinstance(v, str) and ObjectId.is_valid(v):
        return ObjectId(v)
    # Pydantic v2 expects a PydanticCustomError or ValueError
    raise ValueError("Invalid ObjectId")

# Use Annotated for Pydantic v2 validation
PyObjectId = Annotated[ObjectId, BeforeValidator(validate_objectid)]

# --- Dedicated Model for Nested Configuration ---
# Provides better structure, type hinting, and validation for config data.
# As suggested by the review.
class UserConfig(BaseModel):
    full_instruction_prompt: str = ""
    # Future config fields could go here:
    # style: str = "Quick, factual"
    # length: str = "Max 2-3 sentences"
    # etc.

# --- Main User Model ---
# Represents the structure of a user document in MongoDB.
# Uses the custom PyObjectId and the nested UserConfig model.
class User(BaseModel):
    # Map MongoDB's _id to a Pydantic field named 'id'
    # Use the custom PyObjectId type for correct handling
    id: Optional[PyObjectId] = Field(alias="_id", default=None)

    # Our application-level unique identifier
    # Review suggested renaming (username, email), but user_id is clear for now
    user_id: str = Field(...)

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
                }
            }
        },
    )


# Add imports needed for future fields if you add them to the model definition
# from datetime import datetime
# from typing import List