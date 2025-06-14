from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional, Literal
from enum import Enum

class ProcessingStatus(str, Enum):
    """Status of message processing through the LLM pipeline"""
    PENDING = "pending"      # Initial state, not yet processed
    PROCESSING = "processing"  # Currently being processed by LLM
    COMPLETED = "completed"    # Successfully processed
    FAILED = "failed"         # Processing failed

class Message(BaseModel):
    """
    A single message in a conversation, with standardized fields for content, role, and metadata.
    """
    user_id: str             # Required field for message ownership
    content: str = Field(..., min_length=1, max_length=32768)  # Max ~32KB per message
    role: Literal["user", "assistant"]  # Restrict to valid roles
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    context: Optional[dict] = Field(default_factory=dict)  # Additional message context
    processing_status: ProcessingStatus = Field(default=ProcessingStatus.PENDING)
    processing_attempts: int = Field(default=0, ge=0)  # Ensure non-negative
    last_attempt: Optional[datetime] = None
    error_details: Optional[str] = None
    
    def to_text(self) -> str:
        """Convert message to a text format suitable for LLM context."""
        return f"{self.role.capitalize()}: {self.content}"
    
    def to_dict(self) -> dict:
        """Convert message to a dictionary format suitable for database storage."""
        return {
            "user_id": self.user_id,
            "content": self.content,
            "role": self.role,
            "timestamp": self.timestamp,
            "context": self.context or {},
            "processing_status": self.processing_status,
            "processing_attempts": self.processing_attempts,
            "last_attempt": self.last_attempt,
            "error_details": self.error_details
        }
    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        """Create a Message instance from a dictionary (e.g., from database)."""
        # Ensure user_id is present
        if "user_id" not in data:
            raise ValueError("user_id is required")
            
        # Handle status conversion
        if "processing_status" in data and isinstance(data["processing_status"], str):
            data["processing_status"] = ProcessingStatus(data["processing_status"])
            
        # Ensure datetime objects
        if "timestamp" in data and isinstance(data["timestamp"], str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"].rstrip("Z"))
        if "last_attempt" in data and isinstance(data["last_attempt"], str):
            data["last_attempt"] = datetime.fromisoformat(data["last_attempt"].rstrip("Z"))
        return cls(
            user_id=data["user_id"],
            content=data["content"],
            role=data["role"],
            timestamp=data["timestamp"],
            context=data.get("context", {}),
            processing_status=data.get("processing_status", ProcessingStatus.PENDING),
            processing_attempts=data.get("processing_attempts", 0),
            last_attempt=data.get("last_attempt"),
            error_details=data.get("error_details")
        )
