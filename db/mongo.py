# src/db/mongo.py
import pymongo
from pymongo import MongoClient, IndexModel, ASCENDING
from pymongo.errors import ConnectionFailure, OperationFailure, PyMongoError, DuplicateKeyError
from src.config.settings import MONGODB_CONNECTION_STRING , DB_NAME, COLLECTION_NAME # COLLECTION_NAME for users
# Import the revised models
from src.models.users import User
from src.models.schedule import Schedule
from typing import Optional, Tuple, List
import logging
from bson import ObjectId
# Import datetime and timezone for timezone-aware operations
from datetime import datetime, timezone


logger = logging.getLogger(__name__)

# Global client (managed by FastAPI/Uvicorn lifespan events)
_mongo_client: Optional[MongoClient] = None

# --- Custom Exception for Database Errors ---
# Define a custom exception to make error handling clearer
class DatabaseError(Exception):
    """Custom exception for database-related errors."""
    pass

def get_mongo_client() -> MongoClient:
    """
    Establishes and returns a MongoDB client connection.
    Raises DatabaseError on failure.
    """
    global _mongo_client
    if _mongo_client is not None:
        try:
            # Check if the existing connection is still alive with a quick command
            _mongo_client.admin.command('ping')
            return _mongo_client
        except ConnectionFailure:
            logger.warning("Existing MongoDB connection is stale. Reconnecting.")
            _mongo_client = None # Reset client if stale

    if not MONGODB_CONNECTION_STRING or MONGODB_CONNECTION_STRING == "YOUR_MONGODB_CONNECTION_STRING":
         # Configuration error - hard fail
         logger.critical("MongoDB connection string not configured!")
         raise DatabaseError("MongoDB connection string not configured.")

    try:
        logger.info("Attempting to establish new MongoDB connection...")
        # Use a timeout to prevent hanging indefinitely
        # serverSelectionTimeoutMS helps detect network issues faster
        client = MongoClient(MONGODB_CONNECTION_STRING, serverSelectionTimeoutMS=5000)
        # The ismaster command is cheap and does not require auth, verifies connection
        client.admin.command('ismaster')
        _mongo_client = client # Store client globally if successful
        logger.info("✅ New MongoDB connection established.")
        return _mongo_client
    except ConnectionFailure as e:
        logger.critical(f"MongoDB connection failed: {e}", exc_info=True)
        # Raise custom exception on connection failure
        _mongo_client = None # Ensure client is None if connection failed
        raise DatabaseError(f"MongoDB connection failed: {e}") from e
    except Exception as e:
        logger.critical(f"An unexpected error occurred during MongoDB connection: {e}", exc_info=True)
        _mongo_client = None
        raise DatabaseError(f"An unexpected error occurred during MongoDB connection: {e}") from e


def close_mongo_client():
    """Closes the global MongoDB client connection."""
    global _mongo_client
    if _mongo_client:
        logger.info("Closing MongoDB connection.")
        _mongo_client.close()
        _mongo_client = None

def get_mongo_db() -> pymongo.database.Database:
    """
    Returns the MongoDB database object and ensures indexes exist.
    Raises DatabaseError on failure.
    """
    try:
        client = get_mongo_client()
        # If get_mongo_client failed, it would have already raised an exception

        db = client[DB_NAME]

        # --- Ensure Indexes Exist ---
        # Check and create indexes if they don't exist.
        # A more robust system would use migration scripts to verify configuration.
        # For this phase, we ensure existence.

        # For User collection
        user_collection = db[COLLECTION_NAME] # COLLECTION_NAME is for users
        # Check existence by name
        if "user_id_1" not in user_collection.index_information():
             logger.info(f"Creating unique index on '{COLLECTION_NAME}.user_id'")
             # Create the index and verify acknowledgement
             # We don't check *if* it was created correctly beyond acknowledgement in this step
             try:
                 user_collection.create_index([("user_id", ASCENDING)], unique=True)
                 logger.info("✅ Index creation requested for user_id.")
             except OperationFailure as e:
                 logger.error(f"Failed to create index on {COLLECTION_NAME}.user_id: {e}", exc_info=True)
                 # Decide if index creation failure is critical enough to stop app startup
                 # For unique index on user_id, yes, probably critical.
                 raise DatabaseError(f"Failed to create index on {COLLECTION_NAME}.user_id: {e}") from e
             except Exception as e:
                 logger.error(f"Unexpected error during index creation on {COLLECTION_NAME}.user_id: {e}", exc_info=True)
                 raise DatabaseError(f"Unexpected error during index creation on {COLLECTION_NAME}.user_id: {e}") from e


        # For Schedule collection (New Collection)
        schedule_collection_name = "schedules" # Define a new collection name for schedules
        schedule_collection = db[schedule_collection_name]
        # Ensure index on user_id for fetching schedules for a user
        if "user_id_1" not in schedule_collection.index_information():
             logger.info(f"Creating index on '{schedule_collection_name}.user_id'")
             try:
                 schedule_collection.create_index([("user_id", ASCENDING)])
                 logger.info("✅ Index creation requested for schedules.user_id.")
             except Exception as e:
                 logger.error(f"Failed to create index on {schedule_collection_name}.user_id: {e}", exc_info=True)
                 # Non-unique index failure might be less critical, decide based on need
                 pass # Allow startup but log error

        # Ensure index on status and next_run_at for querying due schedules (Crucial for external scheduler)
        if "status_1_next_run_at_1" not in schedule_collection.index_information():
             logger.info(f"Creating index on '{schedule_collection_name}.status' and 'next_run_at'")
             try:
                 schedule_collection.create_index([("status", ASCENDING), ("next_run_at", ASCENDING)])
                 logger.info("✅ Index creation requested for schedules.status and next_run_at.")
             except Exception as e:
                 logger.error(f"Failed to create index on {schedule_collection_name}.status and next_run_at: {e}", exc_info=True)
                 pass # Allow startup but log error

        # --- End Ensure Indexes ---

        return db
    except DatabaseError:
        # If get_mongo_client failed, re-raise its exception
        raise
    except Exception as e:
        # Catch any other unexpected error during DB access or index check
        logger.critical(f"Unexpected error accessing database or checking indexes: {e}", exc_info=True)
        raise DatabaseError(f"Unexpected error accessing database or checking indexes: {e}") from e

# Helper to get User collection (using existing COLLECTION_NAME)
def get_user_collection() -> pymongo.collection.Collection:
    """
    Returns the user settings collection. Raises DatabaseError on failure.
    """
    try:
        db = get_mongo_db()
        # If get_mongo_db failed, it would have already raised
        collection = db[COLLECTION_NAME]
        return collection
    except DatabaseError:
        raise # Re-raise if getting DB failed
    except Exception as e:
        logger.critical(f"Unexpected error getting collection '{COLLECTION_NAME}': {e}", exc_info=True)
        raise DatabaseError(f"Unexpected error getting collection '{COLLECTION_NAME}': {e}") from e


# --- New Helper to get Schedule collection ---
def get_schedule_collection() -> pymongo.collection.Collection:
    """
    Returns the schedule entries collection. Raises DatabaseError on failure.
    """
    try:
        db = get_mongo_db()
        # If get_mongo_db failed, it would have already raised
        collection = db["schedules"] # Use the explicitly defined schedule collection name
        return collection
    except DatabaseError:
        raise # Re-raise if getting DB failed
    except Exception as e:
        logger.critical(f"Unexpected error getting collection 'schedules': {e}", exc_info=True)
        raise DatabaseError(f"Unexpected error getting collection 'schedules': {e}") from e


# --- Core User Data Functions (Refactored for Exception Handling) ---
def get_user_by_id(user_id: str) -> Optional[User]:
    """
    Fetches a user document by user_id and returns as a Pydantic model.
    Raises DatabaseError on critical DB errors.
    """
    try:
        collection = get_user_collection()
        # If get_user_collection failed, it would have already raised
        logger.debug(f"Fetching user document for user_id: {user_id}")
        user_doc = collection.find_one({"user_id": user_id})

        if user_doc:
            logger.debug(f"✅ Found user document for {user_id}.")
            # Pydantic parsing errors should ideally be handled by caller or validation layers
            return User(**user_doc)
        else:
            logger.debug(f"No user document found for {user_id}.")
            return None # User not found is not a DB error

    except DatabaseError:
        raise # Re-raise DB errors
    except PyMongoError as e:
         logger.error(f"PyMongo error fetching user document for {user_id}: {e}", exc_info=True)
         raise DatabaseError(f"DB error fetching user document for {user_id}: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error fetching user document for {user_id}: {e}", exc_info=True)
        raise DatabaseError(f"Unexpected error fetching user document for {user_id}: {e}") from e


def get_user_config(user_id: str) -> str | None:
    """
    Fetches the current config prompt for a user from MongoDB.
    Returns the config string ('') if document/field not found, or raises DatabaseError on critical errors.
    """
    try:
        collection = get_user_collection()
        # If get_user_collection failed, it would have already raised

        logger.debug(f"Fetching user config field for user_id: {user_id} with projection.")
        user_doc = collection.find_one(
            {"user_id": user_id},
            {"projection": {"config.full_instruction_prompt": 1, "_id": 1}}
        )

        if user_doc:
            logger.debug(f"✅ Found user document (projected) for {user_id}.")
            config = user_doc.get("config")
            if isinstance(config, dict):
                 return config.get("full_instruction_prompt", "") # '' if field missing
            else:
                 logger.warning(f"User document for {user_id} has missing or invalid 'config' field.")
                 return "" # Treat as empty config if field invalid/missing
        else:
            # User document not found - indicates a new user or issue
            logger.debug(f"User document not found for {user_id} during config fetch.")
            return "" # Return empty string for new users/missing docs, consistent with tweak_agent

    except DatabaseError:
        raise # Re-raise DB errors
    except PyMongoError as e:
         logger.error(f"PyMongo error fetching user config for {user_id}: {e}", exc_info=True)
         raise DatabaseError(f"DB error fetching user config for {user_id}: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error fetching user config for {user_id}: {e}", exc_info=True)
        raise DatabaseError(f"Unexpected error fetching user config for {user_id}: {e}") from e


def save_user_config(user_id: str, updated_instructions: str) -> bool:
    """
    Saves the updated config prompt for a user to MongoDB using upsert.
    Returns True on success, False on operational failure (like duplicate key), raises DatabaseError on critical errors.
    """
    try:
        collection = get_user_collection()
        # If get_user_collection failed, it would have already raised

        logger.debug(f"Saving config for user_id: {user_id} to collection: {COLLECTION_NAME}")
        update_result = collection.update_one(
            {"user_id": user_id},
            {"$set": {"config.full_instruction_prompt": updated_instructions, "updated_at": datetime.now(timezone.utc)}}, # Update timestamp on config save
            upsert=True
        )

        if update_result.acknowledged:
             if update_result.modified_count > 0 or update_result.upserted_id is not None:
                logger.debug(f"✅ Config modified or upserted for user {user_id}.")
                return True
             else:
                logger.warning(f"⚠️ Config save acknowledged for user {user_id}, but no change made (data identical?).")
                return True # Success as the desired state is achieved
        else:
             logger.error(f"MongoDB write not acknowledged for user {user_id}.")
             # Acknowledged is usually true unless write concern is low. If false, it's a DB issue.
             raise DatabaseError(f"MongoDB write not acknowledged for user {user_id}.")

    except DuplicateKeyError as e:
        logger.warning(f"Duplicate key error saving config for {user_id}: {e}", exc_info=True)
        # Duplicate key on user_id during upsert should not happen with unique index,
        # but handle specifically if needed for retry logic etc. For now, treat as non-critical failure of *this* operation.
        return False
    except DatabaseError:
        raise # Re-raise DB errors
    except PyMongoError as e:
         logger.error(f"PyMongo error saving config for {user_id}: {e}", exc_info=True)
         raise DatabaseError(f"DB error saving config for {user_id}: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error during save config for {user_id}: {e}", exc_info=True)
        raise DatabaseError(f"Unexpected error during save config for {user_id}: {e}") from e


# --- New Functions for Schedule Management (Refactored for Exception Handling) ---

def save_schedule_definition(schedule: Schedule) -> ObjectId:
    """
    Saves or updates a schedule definition in the database.
    Raises DatabaseError on critical errors. Returns ObjectId on success.
    """
    try:
        collection = get_schedule_collection()
        # If get_schedule_collection failed, it would have already raised

        schedule_doc = schedule.model_dump(by_alias=True, exclude_none=True)
        # Ensure timestamps are updated in UTC
        now_utc = datetime.now(timezone.utc)
        schedule_doc['updated_at'] = now_utc
        if 'created_at' not in schedule_doc or not isinstance(schedule_doc['created_at'], datetime):
             schedule_doc['created_at'] = now_utc # Ensure creation timestamp is set/updated if needed

        logger.debug(f"Saving schedule definition for user: {schedule.user_id}, rule: {schedule.recurrence_rule}")

        # Use update_one with upsert based on user_id and recurrence_rule
        filter_query = {"user_id": schedule.user_id, "recurrence_rule": schedule.recurrence_rule}
        update_query = {"$set": schedule_doc}

        result = collection.update_one(filter_query, update_query, upsert=True)

        if result.acknowledged:
            if result.upserted_id:
                logger.info(f"✅ Schedule definition created for user {schedule.user_id}. ID: {result.upserted_id}")
                return result.upserted_id # Return the new ObjectId
            elif result.modified_count > 0:
                logger.info(f"✅ Schedule definition updated for user {schedule.user_id}. Rule: {schedule.recurrence_rule}")
                # If updated, return the existing ID
                existing_doc = collection.find_one(filter_query, projection={"_id": 1})
                if existing_doc:
                     return existing_doc.get('_id')
                # Should not happen if modified_count > 0
                raise DatabaseError(f"Failed to retrieve ObjectId after updating schedule for user {schedule.user_id}.")
            else:
                logger.warning(f"⚠️ Schedule definition save acknowledged for user {schedule.user_id}, but no change made.")
                # If no change, return the existing ID
                existing_doc = collection.find_one(filter_query, projection={"_id": 1})
                if existing_doc:
                     return existing_doc.get('_id')
                # Should not happen if acknowledged
                raise DatabaseError(f"Failed to retrieve ObjectId after acknowledged no-change save for user {schedule.user_id}.")
        else:
            logger.error(f"MongoDB write not acknowledged for schedule for user {schedule.user_id}.")
            raise DatabaseError(f"MongoDB write not acknowledged for schedule for user {schedule.user_id}.")

    except DatabaseError:
        raise # Re-raise DB errors
    except PyMongoError as e:
         logger.error(f"PyMongo error saving schedule definition for user {schedule.user_id}: {e}", exc_info=True)
         raise DatabaseError(f"DB error saving schedule definition for user {schedule.user_id}: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error during save schedule definition for user {schedule.user_id}: {e}", exc_info=True)
        raise DatabaseError(f"Unexpected error during save schedule definition for user {schedule.user_id}: {e}") from e


def get_schedule_definitions(user_id: str, status: Optional[str] = None) -> List[Schedule]:
    """
    Fetches schedule definitions for a user, optionally filtered by status.
    Raises DatabaseError on critical errors.
    """
    try:
        collection = get_schedule_collection()
        # If get_schedule_collection failed, it would have already raised

        query = {"user_id": user_id}
        if status:
            query["status"] = status

        logger.debug(f"Fetching schedule definitions for user: {user_id}, status: {status}")
        # Fetch documents and parse them into Schedule models
        schedule_docs = list(collection.find(query))
        # Pydantic parsing errors should ideally be handled by caller or validation layers
        schedules = [Schedule(**doc) for doc in schedule_docs]
        logger.debug(f"✅ Found {len(schedules)} schedule definitions for user {user_id}.")
        return schedules

    except DatabaseError:
        raise # Re-raise DB errors
    except PyMongoError as e:
         logger.error(f"PyMongo error fetching schedule definitions for user {user_id}: {e}", exc_info=True)
         raise DatabaseError(f"DB error fetching schedule definitions for user {user_id}: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error fetching schedule definitions for user {user_id}: {e}", exc_info=True)
        raise DatabaseError(f"Unexpected error fetching schedule definitions for user {user_id}: {e}") from e


def find_due_schedules() -> List[Schedule]:
    """
    Finds active schedules whose next_run_at is in the past or is None.
    This is a query an external scheduler would use. Raises DatabaseError on critical errors.
    """
    try:
        collection = get_schedule_collection()
        # If get_schedule_collection failed, it would have already raised

        # Query for active schedules where next_run_at is less than or equal to now (UTC)
        # Or where next_run_at is null (meaning never ran or calculated)
        current_utc_time = datetime.now(timezone.utc)
        query = {
            "status": "active",
            "$or": [
                {"next_run_at": {"$lte": current_utc_time}},
                {"next_run_at": None}
            ]
        }
        # Sort by next_run_at to process earliest schedules first (helped by compound index)
        sort_criteria = [("next_run_at", ASCENDING)]

        logger.debug(f"Querying for due schedules (status=active, next_run_at <= {current_utc_time} or null)")
        schedule_docs = list(collection.find(query).sort(sort_criteria))
        # Pydantic parsing errors should ideally be handled by caller or validation layers
        schedules = [Schedule(**doc) for doc in schedule_docs]
        logger.debug(f"✅ Found {len(schedules)} due schedules.")
        return schedules

    except DatabaseError:
        raise # Re-raise DB errors
    except PyMongoError as e:
         logger.error(f"PyMongo error finding due schedules: {e}", exc_info=True)
         raise DatabaseError(f"DB error finding due schedules: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error finding due schedules: {e}", exc_info=True)
        raise DatabaseError(f"Unexpected error finding due schedules: {e}") from e

# You will need functions to update next_run_at after a task is scheduled or runs (in Step 2.7 refinement / Step 2.9)
# def update_schedule_next_run(schedule_id: ObjectId, next_run_time: datetime): ...
# def update_schedule_status(schedule_id: ObjectId, status: str): ...


logger.info("✅ MongoDB schedule management functions refined for robustness.")