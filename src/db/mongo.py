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
from src.models.schedule import Schedule, ScheduleStatus
from src.models.message import Message, ProcessingStatus  # Added ProcessingStatus
from src.db.retry import with_retry
from src.config.constants import DEFAULT_CONTEXT_WINDOW  # Import constant for consistent windowing

logger = logging.getLogger(__name__)

# Validate that ScheduleStatus was imported correctly
if not hasattr(ScheduleStatus, 'ACTIVE'):
    raise ImportError("ScheduleStatus.ACTIVE not found - import issue detected")

# Global client (managed by FastAPI/Uvicorn lifespan events)
# Changed type hint to Motor's async client
_mongo_client: Optional[AsyncIOMotorClient] = None

# --- Custom Exception for Database Errors ---
class DatabaseError(Exception):
    """Custom exception for database-related errors."""
    pass

# --- Asynchronous Database Client Management ---
async def get_mongo_client() -> Optional[AsyncIOMotorClient]:
    global _mongo_client
    if _mongo_client is None:
        logger.info("MongoDB client is None, attempting to initialize...")
        try:
            if not MONGODB_CONNECTION_STRING:
                logger.error("MONGODB_CONNECTION_STRING is not set. Cannot initialize MongoDB client.")
                return None
            logger.info(f"Attempting to connect with MONGODB_CONNECTION_STRING (first 30 chars): {MONGODB_CONNECTION_STRING[:30]}...")
            _mongo_client = AsyncIOMotorClient(MONGODB_CONNECTION_STRING)
            logger.info("AsyncIOMotorClient instantiated. Pinging server to verify connection...")
            await _mongo_client.admin.command('ping')
            logger.info("MongoDB client initialized and connection verified (ping successful).")
        except ConnectionFailure as e:
            logger.error(f"MongoDB connection failed (ConnectionFailure) during initialization: {e}")
            _mongo_client = None 
            return None
        except PyMongoError as e: # Catch broader PyMongo errors like auth errors etc.
            logger.error(f"A PyMongoError occurred during MongoDB client initialization: {e.__class__.__name__}: {e}")
            _mongo_client = None
            return None
        except Exception as e: 
            logger.error(f"An unexpected error occurred during MongoDB client initialization: {e.__class__.__name__}: {e}")
            _mongo_client = None
            return None
    else:
        logger.info("MongoDB client already initialized, returning existing instance.")
    return _mongo_client

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


async def find_schedules_for_dispatch(now_utc: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """
    Finds active schedules that are due for dispatch.
    A schedule is due if its status is ACTIVE and next_run_at is less than or equal to the current UTC time.
    Args:
        now_utc: The current UTC datetime. If None, datetime.now(timezone.utc) is used.
    Returns:
        A list of schedule documents (as dicts) that are due.
    Raises:
        DatabaseError: If there's an issue accessing the database.
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    
    logger.info(f"Finding schedules for dispatch, due at or before: {now_utc.isoformat()}")
    
    try:
        schedules_collection = await get_schedule_collection()
        query = {
            "status": ScheduleStatus.ACTIVE.value, # Ensure we use the enum's value
            "next_run_at": {"$lte": now_utc}
        }
        
        # Log the query being made
        logger.debug(f"Dispatch query: {query}")

        cursor = schedules_collection.find(query)
        due_schedules = await cursor.to_list(length=None) # Get all matching documents
        
        logger.info(f"Found {len(due_schedules)} schedules due for dispatch.")
        # Convert ObjectId to str for easier serialization if needed later (e.g., by Celery)
        for schedule in due_schedules:
            if "_id" in schedule and isinstance(schedule["_id"], ObjectId):
                schedule["_id"] = str(schedule["_id"])
        
        return due_schedules
    except PyMongoError as e:
        logger.error(f"PyMongoError while finding schedules for dispatch: {e}", exc_info=True)
        raise DatabaseError(f"Database operation failed while finding schedules: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error while finding schedules for dispatch: {e}", exc_info=True)
        raise DatabaseError(f"An unexpected error occurred while finding schedules: {e}") from e

# --- Message Collection Management ---
async def get_messages_collection() -> AsyncIOMotorCollection:
    """Get a reference to the dedicated messages collection and ensure indexes exist."""
    client = await get_mongo_client()
    collection = client[DB_NAME]["messages"]
    
    # Check if indexes exist and create them if needed
    index_info = await collection.index_information()
    
    # Check and create compound index for efficient message retrieval
    if "user_messages_timestamp" not in index_info:
        await collection.create_index(
            [
                ("user_id", ASCENDING),
                ("timestamp", -1)
            ],
            name="user_messages_timestamp"
        )
        logger.info("✅ Created compound index on messages collection")
    
    # Check and create TTL index for automatic message pruning
    if "message_ttl" not in index_info:
        await collection.create_index(
            "timestamp",
            name="message_ttl",
            expireAfterSeconds=30 * 24 * 60 * 60  # 30 days
        )
        logger.info("✅ Created TTL index on messages collection")
    
    return collection

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
async def save_message(user_id: str, message_content: str, role: str, context: dict = None) -> bool:
    """
    Saves a new message using the dedicated messages collection with transaction support.
    Returns True on success, False on operational failure, raises DatabaseError on critical errors.
    """
    try:
        await get_mongo_client()  # Ensures _mongo_client is initialized
        collection = await get_messages_collection()
        
        # Create complete message object with user_id and processing status
        message_obj = Message(
            user_id=user_id,
            content=message_content,
            role=role,
            timestamp=datetime.utcnow(),
            context=context or {},
            processing_status=ProcessingStatus.PENDING
        )
        
        # Convert to dict
        message_dict = message_obj.model_dump()
        
        # Use a session for atomicity
        async with await _mongo_client.start_session() as session:
            async with session.start_transaction():
                result = await collection.insert_one(message_dict, session=session)
        return bool(result.inserted_id)
        
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
async def get_recent_messages(user_id: str, limit: int = DEFAULT_CONTEXT_WINDOW) -> List[Message]:
    """
    Get recent messages with optimized query and projection.
    Uses index on timestamp for efficient retrieval.
    """
    try:
        collection = await get_messages_collection()
        
        cursor = collection.find(
            {"user_id": user_id},
            projection={"_id": 0}  # MODIFIED: Removed "user_id": 0 to ensure it's included
        ).sort("timestamp", -1).limit(limit)
        
        # messages = [Message.from_dict(doc) async for doc in cursor] # Old line for context
        # Corrected line to ensure user_id is passed if it was missing due to projection
        messages_data = await cursor.to_list(length=limit)
        messages = []
        for doc in messages_data:
            # Ensure user_id from the query filter is used if somehow still missing in doc,
            # though the projection change should be the primary fix.
            # This is more of a safeguard or for contexts where doc might not have it.
            # However, for this specific error, the projection was the culprit.
            # The Message.from_dict will now receive user_id from the doc.
            if 'user_id' not in doc and user_id: # This check is now less critical with projection fix
                 doc['user_id'] = user_id # Should not be needed if projection is correct
            messages.append(Message.from_dict(doc))

        return list(reversed(messages))  # Return in chronological order
    except PyMongoError as e:
        logger.error(f"Error retrieving messages: {e}")
        raise DatabaseError(f"Failed to retrieve messages: {e}")

@with_retry()
async def prune_old_messages(user_id: str, keep_count: int = 100) -> bool:
    """
    Prune old messages while maintaining atomicity using a session.
    Uses a transaction to ensure consistency.

    Args:
        user_id: ID of the user whose messages should be pruned
        keep_count: Number of most recent messages to keep. Default is 100.
    
    Returns:
        bool: True if pruning was successful or no pruning was needed, False otherwise
    """
    try:
        db = await get_mongo_db()
        collection = await get_messages_collection()
        
        async with await _mongo_client.start_session() as session:
            async with session.start_transaction():
                # Get total count and verify if pruning is needed
                total_count = await collection.count_documents({"user_id": user_id}, session=session)
                if total_count <= keep_count:
                    return True  # Nothing to prune
                
                # Find the timestamp cutoff in a single aggregation
                pipeline = [
                    {"$match": {"user_id": user_id}},
                    {"$sort": {"timestamp": -1}},
                    {"$skip": keep_count - 1},  # -1 to get the last message we want to keep
                    {"$limit": 1},
                    {"$project": {"timestamp": 1}}
                ]
                
                cursor = collection.aggregate(pipeline, session=session)
                cutoff_doc = await cursor.to_list(1)
                
                if not cutoff_doc:
                    return True  # Something went wrong, but we'll return True to be safe
                  # Delete all messages older than the cutoff timestamp
                result = await collection.delete_many(
                    {
                        "user_id": user_id,
                        "timestamp": {"$lt": cutoff_doc[0]["timestamp"]}
                    },
                    session=session
                )
                
                # Transaction will automatically commit if we reach here
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
            # Migrate old documents to ensure compatibility
            migrated_doc = _migrate_old_schedule_document(schedule_doc)
            return Schedule(**migrated_doc)
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

        logger.debug(f"Fetching schedule definitions with query: {query}")        # Await the cursor and then convert to list
        schedule_docs = await collection.find(query).to_list(length=None) 
        schedules = [Schedule(**_migrate_old_schedule_document(doc)) for doc in schedule_docs]
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

@with_retry()
async def update_message_status(
    user_id: str, 
    message_id: str, 
    new_status: ProcessingStatus,
    error_details: str = None
) -> bool:
    """
    Updates the processing status of a message with transaction support.
    Returns True if successful, False if message not found, raises DatabaseError on critical errors.
    """
    try:
        collection = await get_messages_collection()
        
        async with await _mongo_client.start_session() as session:
            async with session.start_transaction():
                update_data = {
                    "$set": {
                        "processing_status": new_status,
                        "processing_attempts": {"$add": ["$processing_attempts", 1]},
                        "last_attempt": datetime.utcnow()
                    }
                }
                
                if error_details is not None:
                    update_data["$set"]["error_details"] = error_details

                result = await collection.update_one(
                    {
                        "user_id": user_id,
                        "_id": ObjectId(message_id)
                    },
                    update_data,
                    session=session
                )
                
                if not result.acknowledged:
                    logger.error("MongoDB write not acknowledged for message status update")
                    raise DatabaseError("MongoDB write not acknowledged")
                    
                return result.modified_count > 0

    except PyMongoError as e:
        logger.error(f"Error updating message status: {e}")
        raise DatabaseError(f"Failed to update message status: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in update_message_status: {e}")
        raise DatabaseError(f"Unexpected error in update_message_status: {e}")

def _migrate_old_schedule_document(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Migrate old schedule documents to the new format.
    Handles backward compatibility for documents missing schedule_type and schedule_value.
    """
    # Create a copy to avoid modifying the original
    migrated_doc = doc.copy()
    
    # If the document has the old 'recurrence_rule' field but no 'schedule_type'
    if 'recurrence_rule' in doc and 'schedule_type' not in doc:
        old_rule = doc['recurrence_rule']
        
        # Map old recurrence_rule values to new schedule_type
        if old_rule == 'once':
            migrated_doc['schedule_type'] = 'once'
            migrated_doc['schedule_value'] = {'type': 'once'}
        elif old_rule == 'daily':
            migrated_doc['schedule_type'] = 'daily'
            migrated_doc['schedule_value'] = {'time': '09:00'}  # Default time
        elif old_rule == 'weekly':
            migrated_doc['schedule_type'] = 'weekly'
            migrated_doc['schedule_value'] = {'day_of_week': 'monday', 'time': '09:00'}
        elif old_rule == 'monthly':
            migrated_doc['schedule_type'] = 'monthly'
            migrated_doc['schedule_value'] = {'day_of_month': 1, 'time': '09:00'}
        else:
            # Fallback for unknown old rules
            migrated_doc['schedule_type'] = 'once'
            migrated_doc['schedule_value'] = {'type': 'legacy', 'original_rule': old_rule}
    
    # Ensure schedule_type and schedule_value exist
    if 'schedule_type' not in migrated_doc:
        migrated_doc['schedule_type'] = 'once'
    if 'schedule_value' not in migrated_doc:
        migrated_doc['schedule_value'] = {'type': 'default'}
        
    # Add default name if missing
    if 'name' not in migrated_doc:
        migrated_doc['name'] = f"Legacy Schedule ({migrated_doc.get('schedule_type', 'unknown')})"
    
    return migrated_doc

logger.info("✅ MongoDB database functions refined for robustness.")