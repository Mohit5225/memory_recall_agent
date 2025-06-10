import logging
from typing import Optional, Tuple, List, Dict, Any
from datetime import datetime, timezone
from bson import ObjectId

# --- New Motor Imports ---
import motor.motor_asyncio
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
from pymongo import IndexModel, ASCENDING
# Re-import PyMongoError types for comprehensive error handling, as Motor extends them
from pymongo.errors import ConnectionFailure, OperationFailure, PyMongoError, DuplicateKeyError

from src.config.settings import MONGODB_CONNECTION_STRING, DB_NAME, COLLECTION_NAME
from src.models.users import User
from src.models.schedule import Schedule
from src.models.message import Message  # New import for Message model
from src.db.retry import with_retry

logger = logging.getLogger(__name__)

# Global client (managed by FastAPI/Uvicorn lifespan events)
# Changed type hint to Motor's async client
_mongo_client: Optional[AsyncIOMotorClient] = None

# --- Custom Exception for Database Errors ---
class DatabaseError(Exception):
    """Custom exception for database-related errors."""
    pass

# --- Asynchronous Database Client Management ---
async def get_mongo_client() -> AsyncIOMotorClient:
    """
    Establishes and returns an asynchronous MongoDB client connection.
    Raises DatabaseError on failure.
    """
    global _mongo_client
    if _mongo_client is not None:
        try:
            # Check if the existing connection is still alive with a quick async command
            # The 'ping' command is now awaited
            await _mongo_client.admin.command('ping')
            return _mongo_client
        except ConnectionFailure:
            logger.warning("Existing MongoDB connection is stale or lost. Reconnecting.")
            _mongo_client = None # Reset client if stale

    if not MONGODB_CONNECTION_STRING or MONGODB_CONNECTION_STRING == "YOUR_MONGODB_CONNECTION_STRING":
        logger.critical("MongoDB connection string not configured!")
        raise DatabaseError("MongoDB connection string not configured.")

    try:
        logger.info("Attempting to establish new asynchronous MongoDB connection...")
        # Instantiate Motor's async client
        # serverSelectionTimeoutMS helps detect network issues faster
        client = AsyncIOMotorClient(MONGODB_CONNECTION_STRING, serverSelectionTimeoutMS=5000)
        
        # The ismaster command is cheap and does not require auth, verifies connection
        # This command is now awaited
        await client.admin.command('ismaster') 
        _mongo_client = client # Store client globally if successful
        logger.info("✅ New asynchronous MongoDB connection established.")
        return _mongo_client
    except ConnectionFailure as e:
        logger.critical(f"MongoDB connection failed: {e}", exc_info=True)
        _mongo_client = None
        raise DatabaseError(f"MongoDB connection failed: {e}") from e
    except Exception as e:
        logger.critical(f"An unexpected error occurred during MongoDB connection: {e}", exc_info=True)
        _mongo_client = None
        raise DatabaseError(f"An unexpected error occurred during MongoDB connection: {e}") from e


async def close_mongo_client():
    """Closes the global MongoDB client connection asynchronously."""
    global _mongo_client
    if _mongo_client:
        logger.info("Closing MongoDB connection.")
        # MotorClient.close() is synchronous, but safe to call in async context.
        # No `await` is needed or available for `_mongo_client.close()`.
        _mongo_client.close()
        _mongo_client = None

async def get_mongo_db() -> motor.motor_asyncio.AsyncIOMotorDatabase:
    """
    Returns the asynchronous MongoDB database object and ensures indexes exist.
    Raises DatabaseError on failure.
    """
    try:
        # Await the asynchronous client getter
        client = await get_mongo_client() 

        db = client[DB_NAME]

        # --- Ensure Indexes Exist (Asynchronously) ---
        # For User collection
        user_collection = db[COLLECTION_NAME] 
        
        if "user_id_1" not in (await user_collection.index_information()): 
            logger.info(f"Creating unique index on '{COLLECTION_NAME}.user_id'")
            try:
                await user_collection.create_index([("user_id", ASCENDING)], unique=True)
                logger.info("✅ Index creation requested for user_id.")
            except OperationFailure as e:
                logger.error(f"Failed to create index on {COLLECTION_NAME}.user_id: {e}", exc_info=True)
                raise DatabaseError(f"Failed to create index on {COLLECTION_NAME}.user_id: {e}") from e
            except Exception as e:
                logger.error(f"Unexpected error during index creation on {COLLECTION_NAME}.user_id: {e}", exc_info=True)
                raise DatabaseError(f"Unexpected error during index creation on {COLLECTION_NAME}.user_id: {e}") from e

        # For Schedule collection (New Collection)
        schedule_collection_name = "schedules"
        schedule_collection = db[schedule_collection_name]
        
        if "user_id_1" not in (await schedule_collection.index_information()):
            logger.info(f"Creating index on '{schedule_collection_name}.user_id'")
            try:
                await schedule_collection.create_index([("user_id", ASCENDING)])
                logger.info("✅ Index creation requested for schedules.user_id.")
            except Exception as e:
                logger.error(f"Failed to create index on {schedule_collection_name}.user_id: {e}", exc_info=True)
                pass 

        if "status_1_next_run_at_1" not in (await schedule_collection.index_information()):
            logger.info(f"Creating index on '{schedule_collection_name}.status' and 'next_run_at'")
            try:
                await schedule_collection.create_index([("status", ASCENDING), ("next_run_at", ASCENDING)])
                logger.info("✅ Index creation requested for schedules.status and next_run_at.")
            except Exception as e:
                logger.error(f"Failed to create index on {schedule_collection_name}.status and next_run_at: {e}", exc_info=True)
                pass 

        # --- End Ensure Indexes ---

        return db
    except DatabaseError:
        raise
    except Exception as e:
        logger.critical(f"Unexpected error accessing database or checking indexes: {e}", exc_info=True)
        raise DatabaseError(f"Unexpected error accessing database or checking indexes: {e}") from e

# Helper to get User collection
async def get_user_collection() -> motor.motor_asyncio.AsyncIOMotorCollection:
    """
    Returns the asynchronous user settings collection. Raises DatabaseError on failure.
    """
    try:
        # Await the asynchronous DB getter
        db = await get_mongo_db() 
        collection = db[COLLECTION_NAME]
        return collection
    except DatabaseError:
        raise
    except Exception as e:
        logger.critical(f"Unexpected error getting collection '{COLLECTION_NAME}': {e}", exc_info=True)
        raise DatabaseError(f"Unexpected error getting collection '{COLLECTION_NAME}': {e}") from e


# --- New Helper to get Schedule collection ---
async def get_schedule_collection() -> motor.motor_asyncio.AsyncIOMotorCollection:
    """
    Returns the asynchronous schedule entries collection. Raises DatabaseError on failure.
    """
    try:
        # Await the asynchronous DB getter
        db = await get_mongo_db() 
        collection = db["schedules"] 
        return collection
    except DatabaseError:
        raise
    except Exception as e:
        logger.critical(f"Unexpected error getting collection 'schedules': {e}", exc_info=True)
        raise DatabaseError(f"Unexpected error getting collection 'schedules': {e}") from e


# --- Message Collection Management ---
async def get_messages_collection() -> motor.motor_asyncio.AsyncIOMotorCollection:
    """Returns the dedicated messages collection for better scaling."""
    try:
        db = await get_mongo_db()
        return db["messages"]  # Dedicated collection for messages
    except Exception as e:
        logger.error(f"Error getting messages collection: {e}")
        raise DatabaseError(f"Error getting messages collection: {e}")

async def ensure_message_indexes():
    """Creates optimized indexes for message operations."""
    try:
        collection = await get_messages_collection()
        
        # Compound index for efficient message retrieval
        await collection.create_index(
            [
                ("user_id", ASCENDING),
                ("timestamp", -1)
            ],
            name="user_messages_timestamp"
        )
        
        # TTL index for automatic message pruning after 30 days
        await collection.create_index(
            "timestamp",
            name="message_ttl",
            expireAfterSeconds=30 * 24 * 60 * 60  # 30 days
        )
        
        logger.info("✅ Message indexes created successfully")
    except Exception as e:
        logger.error(f"Error creating message indexes: {e}")
        raise DatabaseError(f"Failed to create message indexes: {e}")

@with_retry()
async def save_message(user_id: str, message: Message) -> bool:
    """
    Saves a message with atomic operation for concurrent safety.
    Uses ordered insert to ensure message sequence integrity.
    """
    try:
        collection = await get_messages_collection()
        
        # Prepare message document
        message_doc = {
            "user_id": user_id,
            **message.to_dict()
        }
        
        # Use atomic insert for concurrency safety
        result = await collection.insert_one(message_doc)
        
        return bool(result.inserted_id)
    except PyMongoError as e:
        logger.error(f"Error saving message: {e}")
        raise DatabaseError(f"Failed to save message: {e}")

@with_retry()
async def get_recent_messages(user_id: str, limit: int = 7) -> List[Message]:
    """
    Get recent messages with optimized query and projection.
    Uses index on timestamp for efficient retrieval.
    """
    try:
        collection = await get_messages_collection()
        
        cursor = collection.find(
            {"user_id": user_id},
            projection={"_id": 0, "user_id": 0}
        ).sort("timestamp", -1).limit(limit)
        
        messages = [Message.from_dict(doc) async for doc in cursor]
        return list(reversed(messages))  # Return in chronological order
    except PyMongoError as e:
        logger.error(f"Error retrieving messages: {e}")
        raise DatabaseError(f"Failed to retrieve messages: {e}")

@with_retry()
async def prune_old_messages(user_id: str, max_messages: int = 100) -> bool:
    """
    Prune old messages while maintaining atomicity.
    Uses bulk operation for efficiency.
    """
    try:
        collection = await get_messages_collection()
        
        # Get timestamp of the nth newest message
        cursor = collection.find(
            {"user_id": user_id},
            projection={"timestamp": 1}
        ).sort("timestamp", -1).skip(max_messages).limit(1)
        
        nth_message = await cursor.to_list(1)
        
        if not nth_message:
            return True  # Nothing to prune
            
        # Delete all messages older than the nth message
        result = await collection.delete_many({
            "user_id": user_id,
            "timestamp": {"$lt": nth_message[0]["timestamp"]}
        })
        
        return bool(result.deleted_count)
    except PyMongoError as e:
        logger.error(f"Error pruning messages: {e}")
        raise DatabaseError(f"Failed to prune messages: {e}")

# --- Core User Data Functions (Refactored for Exception Handling) ---
async def get_user_by_id(user_id: str) -> Optional[User]:
    """
    Fetches a user document by user_id and returns as a Pydantic model.
    Raises DatabaseError on critical DB errors.
    """
    try:
        collection = await get_user_collection() # Await the collection getter
        logger.debug(f"Fetching user document for user_id: {user_id}")
        user_doc = await collection.find_one({"user_id": user_id}) # Await find_one

        if user_doc:
            logger.debug(f"✅ Found user document for {user_id}.")
            return User(**user_doc)
        else:
            logger.debug(f"No user document found for {user_id}.")
            return None

    except DatabaseError:
        raise
    except PyMongoError as e:
        logger.error(f"PyMongo error fetching user document for {user_id}: {e}", exc_info=True)
        raise DatabaseError(f"DB error fetching user document for {user_id}: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error fetching user document for {user_id}: {e}", exc_info=True)
        raise DatabaseError(f"Unexpected error fetching user document for {user_id}: {e}") from e


@with_retry()
async def get_user_config(user_id: str) -> str | None:
    """
    Fetches the current config prompt for a user from MongoDB.
    Returns the config string ('') if document/field not found, or raises DatabaseError on critical errors.
    """
    try:
        collection = await get_user_collection() # Await the collection getter
        logger.debug(f"Fetching user config field for user_id: {user_id} with projection.")
        user_doc = await collection.find_one( # Await find_one
            {"user_id": user_id},
            {"projection": {"config.full_instruction_prompt": 1, "_id": 1}}
        )

        if user_doc:
            logger.debug(f"✅ Found user document (projected) for {user_id}.")
            config = user_doc.get("config")
            if isinstance(config, dict):
                return config.get("full_instruction_prompt", "")
            else:
                logger.warning(f"User document for {user_id} has missing or invalid 'config' field.")
                return ""
        else:
            logger.debug(f"User document not found for {user_id} during config fetch.")
            return ""

    except DatabaseError:
        raise
    except PyMongoError as e:
        logger.error(f"PyMongo error fetching user config for {user_id}: {e}", exc_info=True)
        raise DatabaseError(f"DB error fetching user config for {user_id}: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error fetching user config for {user_id}: {e}", exc_info=True)
        raise DatabaseError(f"Unexpected error fetching user config for {user_id}: {e}") from e


@with_retry()
async def save_user_config(user_id: str, updated_instructions: str) -> bool:
    """
    Saves the updated config prompt for a user to MongoDB using upsert.
    Returns True on success, False on operational failure (like duplicate key), raises DatabaseError on critical errors.
    """
    try:
        collection = await get_user_collection() # Await the collection getter
        logger.debug(f"Saving config for user_id: {user_id} to collection: {COLLECTION_NAME}")
        update_result = await collection.update_one( # Await update_one
            {"user_id": user_id},
            {"$set": {"config.full_instruction_prompt": updated_instructions, "updated_at": datetime.now(timezone.utc)}},
            upsert=True
        )

        if update_result.acknowledged:
            if update_result.modified_count > 0 or update_result.upserted_id is not None:
                logger.debug(f"✅ Config modified or upserted for user {user_id}.")
                return True
            else:
                logger.warning(f"⚠️ Config save acknowledged for user {user_id}, but no change made (data identical?).")
                return True
        else:
            logger.error(f"MongoDB write not acknowledged for user {user_id}.")
            raise DatabaseError(f"MongoDB write not acknowledged for user {user_id}.")

    except DuplicateKeyError as e:
        logger.warning(f"Duplicate key error saving config for {user_id}: {e}", exc_info=True)
        return False
    except DatabaseError:
        raise
    except PyMongoError as e:
        logger.error(f"PyMongo error saving config for {user_id}: {e}", exc_info=True)
        raise DatabaseError(f"DB error saving config for {user_id}: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error during save config for {user_id}: {e}", exc_info=True)
        raise DatabaseError(f"Unexpected error during save config for {user_id}: {e}") from e


# --- New Functions for Schedule Management (Refactored for Exception Handling) ---

@with_retry()
async def create_schedule_definition(schedule_data: Schedule) -> ObjectId:
    """
    Creates a new schedule definition in the database.
    Raises DatabaseError on critical errors. Returns ObjectId on success.
    """
    try:
        collection = await get_schedule_collection() # Await the collection getter

        insert_data = schedule_data.model_dump(by_alias=True, exclude_none=True)

        now_utc = datetime.now(timezone.utc)
        if 'created_at' not in insert_data:
            insert_data['created_at'] = now_utc
        insert_data['last_modified_at'] = now_utc

        logger.debug(f"Creating new schedule definition for user: {schedule_data.user_id}, name: {schedule_data.name}")

        result = await collection.insert_one(insert_data) # Await insert_one

        if result.acknowledged:
            logger.info(f"✅ Schedule definition created. ID: {result.inserted_id}")
            return result.inserted_id
        else:
            logger.error(f"MongoDB write not acknowledged for new schedule.")
            raise DatabaseError(f"MongoDB write not acknowledged for new schedule.")

    except DatabaseError:
        raise
    except PyMongoError as e:
        logger.error(f"PyMongo error creating schedule definition: {e}", exc_info=True)
        raise DatabaseError(f"DB error creating schedule definition: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error during creation of schedule definition: {e}", exc_info=True)
        raise DatabaseError(f"Unexpected error during creation of schedule definition: {e}") from e

@with_retry()
async def get_schedule_by_id(schedule_id: str) -> Optional[Schedule]:
    """
    Fetches a single schedule document by its unique MongoDB _id and returns as a Pydantic model.
    Raises DatabaseError on critical DB errors.
    """
    try:
        collection = await get_schedule_collection() # Await the collection getter
        logger.debug(f"Fetching schedule document for _id: {schedule_id}")
        schedule_doc = await collection.find_one({"_id": ObjectId(schedule_id)}) # Await find_one

        if schedule_doc:
            logger.debug(f"✅ Found schedule document for _id: {schedule_id}.")
            return Schedule(**schedule_doc)
        else:
            logger.debug(f"No schedule document found for _id: {schedule_id}.")
            return None

    except DatabaseError:
        raise
    except PyMongoError as e:
        logger.error(f"PyMongo error fetching schedule document by id {schedule_id}: {e}", exc_info=True)
        raise DatabaseError(f"DB error fetching schedule document by id {schedule_id}: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error fetching schedule document by id {schedule_id}: {e}", exc_info=True)
        raise DatabaseError(f"Unexpected error fetching schedule document by id {schedule_id}: {e}") from e

async def find_schedules(user_id: Optional[str] = None, query_params: Optional[Dict[str, Any]] = None) -> List[Schedule]:
    """
    Fetches schedule definitions, optionally filtered by user_id or other query parameters,
    and returns as Pydantic models.
    Raises DatabaseError on critical errors.
    """
    try:
        collection = await get_schedule_collection() # Await the collection getter
        query: Dict[str, Any] = {"status": "active"} # Default to active schedules
        if user_id:
            query["user_id"] = user_id
        if query_params:
            query.update(query_params)

        logger.debug(f"Fetching schedule definitions with query: {query}")
        # Await the cursor and then convert to list
        schedule_docs = await collection.find(query).to_list(length=None) 
        schedules = [Schedule(**doc) for doc in schedule_docs]
        logger.debug(f"✅ Found {len(schedules)} schedule definitions with query.")
        return schedules

    except DatabaseError:
        raise
    except PyMongoError as e:
        logger.error(f"PyMongo error fetching schedule definitions with query {query}: {e}", exc_info=True)
        raise DatabaseError(f"DB error fetching schedule definitions with query {query}: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error fetching schedule definitions with query {query}: {e}", exc_info=True)
        raise DatabaseError(f"Unexpected error fetching schedule definitions with query {query}: {e}") from e

async def get_all_active_schedules() -> List[Schedule]:
    """
    Fetches all active schedule definitions, primarily for the Celery Beat scheduler.
    This replaces the implicit filter within find_schedules for this specific purpose.
    Raises DatabaseError on critical errors.
    """
    return await find_schedules(user_id=None, query_params={"status": "active"}) # Await the call to find_schedules


@with_retry()
async def update_schedule_by_id(schedule_id: str, updates: Dict[str, Any]) -> bool:
    """
    Updates fields of an existing schedule document by its _id.
    Raises DatabaseError on critical errors. Returns True on success, False if document not found.
    """
    try:
        collection = await get_schedule_collection() # Await the collection getter
        updates["last_modified_at"] = datetime.now(timezone.utc)
        logger.debug(f"Updating schedule _id: {schedule_id} with updates: {updates}")

        result = await collection.update_one({"_id": ObjectId(schedule_id)}, {"$set": updates}) # Await update_one

        if result.acknowledged:
            if result.modified_count > 0:
                logger.info(f"✅ Schedule _id: {schedule_id} updated.")
                return True
            else:
                logger.warning(f"⚠️ Schedule _id: {schedule_id} not found or no change made.")
                return False
        else:
            logger.error(f"MongoDB write not acknowledged for schedule _id: {schedule_id}.")
            raise DatabaseError(f"MongoDB write not acknowledged for schedule _id: {schedule_id}.")

    except DatabaseError:
        raise
    except PyMongoError as e:
        logger.error(f"PyMongo error updating schedule by id {schedule_id}: {e}", exc_info=True)
        raise DatabaseError(f"DB error updating schedule by id {schedule_id}: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error updating schedule by id {schedule_id}: {e}", exc_info=True)
        raise DatabaseError(f"Unexpected error updating schedule by id {schedule_id}: {e}") from e

@with_retry()
async def delete_schedule_by_id(schedule_id: str) -> bool:
    """
    Deletes a schedule document by its _id.
    Raises DatabaseError on critical errors. Returns True on success, False if document not found.
    """
    try:
        collection = await get_schedule_collection() # Await the collection getter
        logger.debug(f"Deleting schedule _id: {schedule_id}")
        result = await collection.delete_one({"_id": ObjectId(schedule_id)}) # Await delete_one

        if result.acknowledged:
            if result.deleted_count > 0:
                logger.info(f"✅ Schedule _id: {schedule_id} deleted.")
                return True
            else:
                logger.warning(f"⚠️ Schedule _id: {schedule_id} not found for deletion.")
                return False
        else:
            logger.error(f"MongoDB write not acknowledged for schedule _id: {schedule_id} deletion.")
            raise DatabaseError(f"MongoDB write not acknowledged for schedule _id: {schedule_id} deletion.")

    except DatabaseError:
        raise
    except PyMongoError as e:
        logger.error(f"PyMongo error deleting schedule by id {schedule_id}: {e}", exc_info=True)
        raise DatabaseError(f"DB error deleting schedule by id {schedule_id}: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error deleting schedule by id {schedule_id}: {e}", exc_info=True)
        raise DatabaseError(f"Unexpected error deleting schedule by id {schedule_id}: {e}") from e

@with_retry()
async def deactivate_schedule_by_id(schedule_id: str) -> bool:
    """
    Sets the 'status' field of a schedule to 'inactive' by its _id, effectively deactivating it.
    Raises DatabaseError on critical errors. Returns True on success, False if document not found.
    """
    try:
        collection = await get_schedule_collection() # Await the collection getter
        logger.debug(f"Deactivating schedule _id: {schedule_id}")
        updates = {"status": "inactive", "last_modified_at": datetime.now(timezone.utc)}
        result = await collection.update_one({"_id": ObjectId(schedule_id)}, {"$set": updates}) # Await update_one

        if result.acknowledged:
            if result.modified_count > 0:
                logger.info(f"✅ Schedule _id: {schedule_id} deactivated.")
                return True
            else:
                logger.warning(f"⚠️ Schedule _id: {schedule_id} not found or already inactive for deactivation.")
                return False
        else:
            logger.error(f"MongoDB write not acknowledged for schedule _id: {schedule_id} deactivation.")
            raise DatabaseError(f"MongoDB write not acknowledged for schedule _id: {schedule_id} deactivation.")

    except DatabaseError:
        raise
    except PyMongoError as e:
        logger.error(f"PyMongo error deactivating schedule by id {schedule_id}: {e}", exc_info=True)
        raise DatabaseError(f"DB error deactivating schedule by id {schedule_id}: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error deactivating schedule by id {schedule_id}: {e}", exc_info=True)
        raise DatabaseError(f"Unexpected error deactivating schedule by id {schedule_id}: {e}") from e

# --- New Functions for Message History Management ---

@with_retry()
async def save_message(user_id: str, message_content: str, role: str, context: dict = None) -> bool:
    """
    Saves a new message using the dedicated messages collection.
    Returns True on success, False on operational failure, raises DatabaseError on critical errors.
    """
    try:
        collection = await get_messages_collection()
        logger.debug(f"Saving message for user_id: {user_id}")
        
        # Create new message document
        new_message = {
            "user_id": user_id,
            "content": message_content,
            "role": role,
            "timestamp": datetime.now(timezone.utc),
            "context": context or {}
        }
        
        # Insert the new message
        result = await collection.insert_one(new_message)
        
        if result.acknowledged:
            logger.debug(f"✅ Message saved for user {user_id}")
            return True
        else:
            logger.error(f"MongoDB write not acknowledged for user {user_id}")
            raise DatabaseError(f"MongoDB write not acknowledged for user {user_id}")

    except DuplicateKeyError as e:
        logger.warning(f"Duplicate key error saving message for {user_id}: {e}", exc_info=True)
        return False
    except DatabaseError:
        raise
    except PyMongoError as e:
        logger.error(f"PyMongo error saving message for {user_id}: {e}", exc_info=True)
        raise DatabaseError(f"DB error saving message for {user_id}: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error saving message for {user_id}: {e}", exc_info=True)
        raise DatabaseError(f"Unexpected error saving message for {user_id}: {e}") from e

@with_retry()
async def get_recent_messages(user_id: str, limit: Optional[int] = None) -> List[Message]:
    """
    Retrieves recent messages for a user, respecting their message limit setting.
    
    Args:
        user_id: The ID of the user
        limit: Optional override for number of messages to return
        
    Returns:
        List[Message]: List of recent messages with proper context
    """
    try:
        collection = await get_user_collection()
        
        # Get user document with messages and limit
        user = await collection.find_one(
            {"user_id": user_id},
            {"config.messages": 1, "config.message_limit": 1}
        )
        
        if not user or "config" not in user:
            return []
            
        messages_data = user["config"].get("messages", [])
        user_limit = user["config"].get("message_limit", 10)
        effective_limit = min(limit if limit is not None else user_limit, user_limit)
        
        # Get the most recent messages within the limit
        recent_messages = messages_data[-effective_limit:] if messages_data else []
        
        # Convert to Message objects, ensuring context exists
        return [Message(
            content=msg["content"],
            role=msg["role"],
            timestamp=msg["timestamp"],
            context=msg.get("context", {})  # Ensure context exists
        ) for msg in recent_messages]
        
    except Exception as e:
        logger.error(f"Error fetching messages for user {user_id}: {e}", exc_info=True)
        raise DatabaseError(f"Error fetching messages: {str(e)}") from e

# --- Message Migration Function ---
async def migrate_messages_to_include_context(user_id: str = None) -> Tuple[int, int]:
    """
    Migrates existing messages to include context field.
    Returns tuple of (processed_count, updated_count).
    
    Args:
        user_id: Optional user_id to migrate specific user's messages. If None, migrates all users.
    """
    try:
        collection = await get_user_collection()
        query = {"user_id": user_id} if user_id else {}
        
        # Find users with messages that need context
        pipeline = [
            {"$match": query},
            {"$unwind": "$config.messages"},
            {"$match": {"config.messages.context": {"$exists": False}}},
            {"$group": {"_id": "$_id"}}
        ]
        
        users_to_update = await collection.aggregate(pipeline).to_list(length=None)
        processed = 0
        updated = 0
        
        for user_doc in users_to_update:
            # Add context field to messages that don't have it
            result = await collection.update_many(
                {"_id": user_doc["_id"], "config.messages.context": {"$exists": False}},
                {"$set": {"config.messages.$[msg].context": {}}},
                array_filters=[{"msg.context": {"$exists": False}}]
            )
            processed += 1
            updated += result.modified_count
            
        return processed, updated
            
    except Exception as e:
        logger.error(f"Error during message migration: {e}", exc_info=True)
        raise DatabaseError(f"Error during message migration: {str(e)}") from e

# --- Message Pruning Function ---
async def prune_old_messages(user_id: str = None) -> int:
    """
    Prunes messages exceeding the user's message limit.
    Returns number of messages pruned.
    
    Args:
        user_id: Optional user_id to prune specific user's messages. If None, prunes all users.
    """
    try:
        collection = await get_user_collection()
        query = {"user_id": user_id} if user_id else {}
        
        total_pruned = 0
        async for user in collection.find(query):
            messages = user.get("config", {}).get("messages", [])
            message_limit = user.get("config", {}).get("message_limit", 10)
            
            if len(messages) > message_limit:
                # Calculate how many messages to remove
                to_remove = len(messages) - message_limit
                
                # Remove oldest messages
                result = await collection.update_one(
                    {"_id": user["_id"]},
                    {"$push": {"config.messages": {
                        "$each": [],
                        "$slice": -message_limit  # Keep only the latest messages
                    }}}
                )
                
                if result.modified_count:
                    total_pruned += to_remove
                    
        return total_pruned
            
    except Exception as e:
        logger.error(f"Error during message pruning: {e}", exc_info=True)
        raise DatabaseError(f"Error during message pruning: {str(e)}") from e

logger.info("✅ MongoDB schedule management functions refined for robustness.")