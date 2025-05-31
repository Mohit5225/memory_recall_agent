# src/db/mongo.py
import pymongo
from pymongo import MongoClient, IndexModel, ASCENDING
from pymongo.errors import ConnectionFailure, OperationFailure, PyMongoError, DuplicateKeyError
from src.config.settings import MONGODB_CONNECTION_STRING , DB_NAME, COLLECTION_NAME # COLLECTION_NAME for users
# Import the revised models
from src.models.users import User
from src.models.schedule import Schedule
from typing import Optional, Tuple, List, Dict, Any
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

# Current save_schedule_definition is more like an upsert based on user_id and recurrence_rule.
# For 2.7.1, we need functions to *find* by various criteria (not just status), *update* by _id, and *delete* by _id.
# Let's adjust save_schedule_definition to be a clear "create" if _id is not present, or "update" if _id is present.

# First, rename `save_schedule_definition` to something clearer like `upsert_schedule_definition`
# or better, create distinct `create_schedule_definition` and `update_schedule_definition_by_id`
# For this step, let's make `save_schedule_definition` (your existing one) more robust and general-purpose for *initial* saving,
# and then add the new specific `get_schedule_by_id`, `find_schedules`, `update_schedule_by_id`, and `delete_schedule_by_id`.

def create_schedule_definition(schedule_data: Schedule) -> ObjectId: # Changed from Dict to Schedule for type safety
    """
    Creates a new schedule definition in the database.
    Raises DatabaseError on critical errors. Returns ObjectId on success.
    """
    try:
        collection = get_schedule_collection()

        # Convert Pydantic model to a dictionary suitable for MongoDB insertion
        # This handles ObjectId and datetime conversion correctly
        # Using .model_dump(by_alias=True) ensures '_id' alias is used for MongoDB
        insert_data = schedule_data.model_dump(by_alias=True, exclude_none=True)

        # Set/update timestamps if not already set by Pydantic's default_factory
        now_utc = datetime.now(timezone.utc)
        if 'created_at' not in insert_data:
            insert_data['created_at'] = now_utc
        insert_data['last_modified_at'] = now_utc

        logger.debug(f"Creating new schedule definition for user: {schedule_data.user_id}, name: {schedule_data.name}")

        result = collection.insert_one(insert_data)

        if result.acknowledged:
            logger.info(f"✅ Schedule definition created. ID: {result.inserted_id}")
            return result.inserted_id
        else:
            logger.error(f"MongoDB write not acknowledged for new schedule.")
            raise DatabaseError(f"MongoDB write not acknowledged for new schedule.")

    except DatabaseError:
        raise # Re-raise DB errors
    except PyMongoError as e:
        logger.error(f"PyMongo error creating schedule definition: {e}", exc_info=True)
        raise DatabaseError(f"DB error creating schedule definition: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error during creation of schedule definition: {e}", exc_info=True)
        raise DatabaseError(f"Unexpected error during creation of schedule definition: {e}") from e

def get_schedule_by_id(schedule_id: str) -> Optional[Schedule]:
    """
    Fetches a single schedule document by its unique MongoDB _id and returns as a Pydantic model.
    Raises DatabaseError on critical DB errors.
    """
    try:
        collection = get_schedule_collection()
        logger.debug(f"Fetching schedule document for _id: {schedule_id}")
        schedule_doc = collection.find_one({"_id": ObjectId(schedule_id)})

        if schedule_doc:
            logger.debug(f"✅ Found schedule document for _id: {schedule_id}.")
            return Schedule(**schedule_doc)
        else:
            logger.debug(f"No schedule document found for _id: {schedule_id}.")
            return None # Schedule not found is not a DB error

    except DatabaseError:
        raise # Re-raise DB errors
    except PyMongoError as e:
        logger.error(f"PyMongo error fetching schedule document by id {schedule_id}: {e}", exc_info=True)
        raise DatabaseError(f"DB error fetching schedule document by id {schedule_id}: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error fetching schedule document by id {schedule_id}: {e}", exc_info=True)
        raise DatabaseError(f"Unexpected error fetching schedule document by id {schedule_id}: {e}") from e

def find_schedules(user_id: Optional[str] = None, query_params: Optional[Dict[str, Any]] = None) -> List[Schedule]:
    """
    Fetches schedule definitions, optionally filtered by user_id or other query parameters,
    and returns as Pydantic models.
    Raises DatabaseError on critical errors.
    """
    try:
        collection = get_schedule_collection()
        query: Dict[str, Any] = {"status": "active"} # Default to active schedules
        if user_id:
            query["user_id"] = user_id
        if query_params:
            query.update(query_params)

        logger.debug(f"Fetching schedule definitions with query: {query}")
        schedule_docs = list(collection.find(query))
        schedules = [Schedule(**doc) for doc in schedule_docs]
        logger.debug(f"✅ Found {len(schedules)} schedule definitions with query.")
        return schedules

    except DatabaseError:
        raise # Re-raise DB errors
    except PyMongoError as e:
        logger.error(f"PyMongo error fetching schedule definitions with query {query}: {e}", exc_info=True)
        raise DatabaseError(f"DB error fetching schedule definitions with query {query}: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error fetching schedule definitions with query {query}: {e}", exc_info=True)
        raise DatabaseError(f"Unexpected error fetching schedule definitions with query {query}: {e}") from e

def get_all_active_schedules() -> List[Schedule]:
    """
    Fetches all active schedule definitions, primarily for the Celery Beat scheduler.
    This replaces the implicit filter within find_schedules for this specific purpose.
    Raises DatabaseError on critical errors.
    """
    return find_schedules(user_id=None, query_params={"status": "active"})


def update_schedule_by_id(schedule_id: str, updates: Dict[str, Any]) -> bool:
    """
    Updates fields of an existing schedule document by its _id.
    Raises DatabaseError on critical errors. Returns True on success, False if document not found.
    """
    try:
        collection = get_schedule_collection()
        updates["last_modified_at"] = datetime.now(timezone.utc) # Always update timestamp
        logger.debug(f"Updating schedule _id: {schedule_id} with updates: {updates}")

        result = collection.update_one({"_id": ObjectId(schedule_id)}, {"$set": updates})

        if result.acknowledged:
            if result.modified_count > 0:
                logger.info(f"✅ Schedule _id: {schedule_id} updated.")
                return True
            else:
                logger.warning(f"⚠️ Schedule _id: {schedule_id} not found or no change made.")
                return False # Not found or no effective change
        else:
            logger.error(f"MongoDB write not acknowledged for schedule _id: {schedule_id}.")
            raise DatabaseError(f"MongoDB write not acknowledged for schedule _id: {schedule_id}.")

    except DatabaseError:
        raise # Re-raise DB errors
    except PyMongoError as e:
        logger.error(f"PyMongo error updating schedule by id {schedule_id}: {e}", exc_info=True)
        raise DatabaseError(f"DB error updating schedule by id {schedule_id}: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error updating schedule by id {schedule_id}: {e}", exc_info=True)
        raise DatabaseError(f"Unexpected error updating schedule by id {schedule_id}: {e}") from e

def delete_schedule_by_id(schedule_id: str) -> bool:
    """
    Deletes a schedule document by its _id.
    Raises DatabaseError on critical errors. Returns True on success, False if document not found.
    """
    try:
        collection = get_schedule_collection()
        logger.debug(f"Deleting schedule _id: {schedule_id}")
        result = collection.delete_one({"_id": ObjectId(schedule_id)})

        if result.acknowledged:
            if result.deleted_count > 0:
                logger.info(f"✅ Schedule _id: {schedule_id} deleted.")
                return True
            else:
                logger.warning(f"⚠️ Schedule _id: {schedule_id} not found for deletion.")
                return False # Document not found
        else:
            logger.error(f"MongoDB write not acknowledged for schedule _id: {schedule_id} deletion.")
            raise DatabaseError(f"MongoDB write not acknowledged for schedule _id: {schedule_id} deletion.")

    except DatabaseError:
        raise # Re-raise DB errors
    except PyMongoError as e:
        logger.error(f"PyMongo error deleting schedule by id {schedule_id}: {e}", exc_info=True)
        raise DatabaseError(f"DB error deleting schedule by id {schedule_id}: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error deleting schedule by id {schedule_id}: {e}", exc_info=True)
        raise DatabaseError(f"Unexpected error deleting schedule by id {schedule_id}: {e}") from e

def deactivate_schedule_by_id(schedule_id: str) -> bool:
    """
    Sets the 'status' field of a schedule to 'inactive' by its _id, effectively deactivating it.
    Raises DatabaseError on critical errors. Returns True on success, False if document not found.
    """
    try:
        collection = get_schedule_collection()
        logger.debug(f"Deactivating schedule _id: {schedule_id}")
        # Change 'active' field to 'status' field as per Schedule model
        updates = {"status": "inactive", "last_modified_at": datetime.now(timezone.utc)}
        result = collection.update_one({"_id": ObjectId(schedule_id)}, {"$set": updates})

        if result.acknowledged:
            if result.modified_count > 0:
                logger.info(f"✅ Schedule _id: {schedule_id} deactivated.")
                return True
            else:
                logger.warning(f"⚠️ Schedule _id: {schedule_id} not found or already inactive for deactivation.")
                return False # Not found or no effective change
        else:
            logger.error(f"MongoDB write not acknowledged for schedule _id: {schedule_id} deactivation.")
            raise DatabaseError(f"MongoDB write not acknowledged for schedule _id: {schedule_id} deactivation.")

    except DatabaseError:
        raise # Re-raise DB errors
    except PyMongoError as e:
        logger.error(f"PyMongo error deactivating schedule by id {schedule_id}: {e}", exc_info=True)
        raise DatabaseError(f"DB error deactivating schedule by id {schedule_id}: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error deactivating schedule by id {schedule_id}: {e}", exc_info=True)
        raise DatabaseError(f"Unexpected error deactivating schedule by id {schedule_id}: {e}") from e


logger.info("✅ MongoDB schedule management functions refined for robustness.")