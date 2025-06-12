"""Message queue processor for handling failed LLM requests."""
import logging
from datetime import datetime, timedelta
from typing import List
from src.db.mongo import get_messages_collection
from src.models.message import Message
from src.llm.gemini import get_gemini_response_async
from motor.motor_asyncio import AsyncIOMotorCollection

logger = logging.getLogger(__name__)

MAX_RETRY_ATTEMPTS = 5
RETRY_DELAY_HOURS = 1

async def process_failed_messages():
    """Process messages that failed LLM processing and need to be retried."""
    try:
        collection: AsyncIOMotorCollection = await get_messages_collection()
        
        # Find failed messages that haven't exceeded max retries and haven't been tried recently
        retry_cutoff = datetime.utcnow() - timedelta(hours=RETRY_DELAY_HOURS)
        cursor = collection.find({
            "processing_status": "failed",
            "processing_attempts": {"$lt": MAX_RETRY_ATTEMPTS},
            "$or": [
                {"last_attempt": {"$lt": retry_cutoff}},
                {"last_attempt": None}
            ]
        })
        
        async for doc in cursor:
            message = Message.from_dict(doc)
            logger.info(f"Retrying failed message. Attempt {message.processing_attempts + 1}/{MAX_RETRY_ATTEMPTS}")
            
            # Retry LLM processing
            response_text, updated_context = await get_gemini_response_async(
                message.content,
                message_context=message.context
            )
            
            # Update message with new status
            message.context.update(updated_context)
            await collection.update_one(
                {"_id": doc["_id"]},
                {"$set": {
                    "context": message.context,
                    "processing_status": updated_context["processing_status"],
                    "processing_attempts": updated_context.get("processing_attempts", 1),
                    "last_attempt": updated_context.get("last_attempt"),
                    "error_message": updated_context.get("error_message")
                }}
            )
            
            if updated_context["processing_status"] == "completed":
                logger.info(f"Successfully reprocessed message after {message.processing_attempts} attempts")
            else:
                logger.warning(f"Message reprocessing failed. Will retry later if attempts remain")
                
    except Exception as e:
        logger.error(f"Error in message queue processor: {e}", exc_info=True)