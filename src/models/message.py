from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional, Literal

class Message(BaseModel):
    """
    A single message in a conversation, with standardized fields for content, role, and metadata.
    """
    content: str
    role: Literal["user", "assistant"]  # Restrict to valid roles
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    context: Optional[dict] = Field(default_factory=dict)  # Additional message context
    
    def to_text(self) -> str:
        """Convert message to a text format suitable for LLM context."""
        return f"{self.role.capitalize()}: {self.content}"
    
    def to_dict(self) -> dict:
        """Convert message to a dictionary format suitable for database storage."""
        return {
            "content": self.content,
            "role": self.role,
            "timestamp": self.timestamp,
            "context": self.context or {}
        }
      @classmethod
    def from_dict(cls, data: dict) -> "Message":
        """Create a Message instance from a dictionary (e.g., from database)."""
        return cls(
            content=data["content"],
            role=data["role"],
            timestamp=data["timestamp"],
            context=data.get("context", {})
        )
        return cls(**data)
