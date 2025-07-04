import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from src.db.mongo import get_user_collection

logger = logging.getLogger(__name__)

async def find_user_by_user_id(user_id: str) -> Optional[Dict[str, Any]]:
    """Find user by user_id (which contains Google's sub)"""
    try:
        collection = await get_user_collection()
        user = await collection.find_one({"user_id": user_id})
        return user
    except Exception as e:
        logger.error(f"Error finding user by user_id {user_id}: {e}")
        return None

async def create_new_user(google_sub: str, email: str, name: str) -> Optional[Dict[str, Any]]:
    """Create a new user from Google OAuth data"""
    try:
        collection = await get_user_collection()
        
        user_data = {
            "user_id": google_sub,  # Primary identifier = Google's sub
            "display_name": name,   # Display name from Google
            "email": email,
            "roles": ["user"],
            "whatsapp_number": None,  # No phone by default
            "whatsapp_verified": False,  # Not verified by default
            "created_at": datetime.now(timezone.utc),
            "last_login": datetime.now(timezone.utc),
            "config": {
                "full_instruction_prompt": "",
                "message_limit": 10,
                "timezone": "UTC"
            }
        }
        
        result = await collection.insert_one(user_data)
        
        if result.inserted_id:
            user_data['_id'] = result.inserted_id
            logger.info(f"Created new user: {google_sub}")
            return user_data
        else:
            logger.error(f"Failed to create user: {google_sub}")
            return None
            
    except Exception as e:
        logger.error(f"Error creating user {google_sub}: {e}")
        return None

async def update_user_last_login(user_id: str) -> bool:
    """Update user's last login timestamp"""
    try:
        collection = await get_user_collection()
        
        result = await collection.update_one(
            {"user_id": user_id},
            {"$set": {"last_login": datetime.now(timezone.utc)}}
        )
        
        return result.modified_count > 0
        
    except Exception as e:
        logger.error(f"Error updating last login for {user_id}: {e}")
        return False

async def get_or_create_user(google_sub: str, email: str, name: str) -> Optional[Dict[str, Any]]:
    """Get existing user or create new one from Google OAuth data"""
    # Try to find existing user (user_id contains Google's sub)
    user = await find_user_by_user_id(google_sub)
    
    if user:
        # Update last login
        await update_user_last_login(google_sub)
        return user
    else:
        # Create new user
        return await create_new_user(google_sub, email, name)