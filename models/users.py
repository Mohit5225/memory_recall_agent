# src/models/user.py
from pydantic import BaseModel, Field, BeforeValidator, ConfigDict
from typing import Optional, Annotated
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
    raise ValueError("Invalid ObjectId")

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
    # created_at: datetime = Field(default_factory=datetime.utcnow)    # Pydantic model configuration
    model_config = ConfigDict(
        # Core functionality
        arbitrary_types_allowed=True,  # Allow ObjectId and other MongoDB types
        from_attributes=True,  # Support mapping from ORM objects
        populate_by_name=True,  # Allow populating by field name as well as alias
        
        # JSON handling
        json_encoders={ObjectId: str},  # Convert ObjectId to string for JSON
        
        # Documentation and schema generation
        json_schema_extra={
            "example": {
                "user_id": "test_user_123",
                "config": {
                    "full_instruction_prompt": "# My Custom Reminder Config\nTopic: Python\nStyle: Witty",
                }
            }
        }
    )