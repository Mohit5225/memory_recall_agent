# src/db/mongo.py
import pymongo
from pymongo import MongoClient, IndexModel, ASCENDING
from pymongo.errors import ConnectionFailure, OperationFailure
from config.settings import MONGODB_CONNECTION_STRING, DB_NAME, COLLECTION_NAME
from models.users import User # Import the revised User model
from typing import Optional, Tuple
import logging
from bson import ObjectId

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Global client (managed by FastAPI/Uvicorn lifespan events)
_mongo_client: Optional[MongoClient] = None

def get_mongo_client() -> Optional[MongoClient]:
    """Establishes and returns a MongoDB client connection."""
    global _mongo_client
    if _mongo_client is not None:
        try:
            # Check if the existing connection is still alive
            _mongo_client.admin.command('ping')
            return _mongo_client
        except ConnectionFailure:
            logger.warning("Existing MongoDB connection is stale. Reconnecting.")
            _mongo_client = None # Reset client if stale

    if not MONGODB_CONNECTION_STRING or MONGODB_CONNECTION_STRING == "YOUR_MONGODB_CONNECTION_STRING":
         logger.error("MongoDB connection string not configured.")
         return None

    try:
        logger.info("Attempting to establish new MongoDB connection...")
        # Use a timeout to prevent hanging indefinitely
        client = MongoClient(MONGODB_CONNECTION_STRING, serverSelectionTimeoutMS=5000)
        # The ismaster command is cheap and does not require auth.
        client.admin.command('ismaster')
        _mongo_client = client # Store client globally if successful
        logger.info("✅ New MongoDB connection established.")
        return _mongo_client
    except ConnectionFailure as e:
        logger.error(f"MongoDB connection failed: {e}")
        _mongo_client = None
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred during MongoDB connection: {e}")
        _mongo_client = None
        return None

# --- Add this function ---
def close_mongo_client():
    """Closes the global MongoDB client connection."""
    global _mongo_client
    if _mongo_client:
        logger.info("Closing MongoDB connection.")
        _mongo_client.close()
        _mongo_client = None
# --- End of added function ---


def get_mongo_db() -> Optional[pymongo.database.Database]:
    """Returns the MongoDB database object."""
    client = get_mongo_client()
    if client is None:
        return None
    try:
        db = client[DB_NAME]
        # Ensure index exists for efficient user lookup
        # This is critical for performance and ensures user_id is unique
        collection = db[COLLECTION_NAME]
        # Check if index exists before creating to avoid errors on restarts
        if "user_id_1" not in collection.index_information():
             logger.info(f"Creating unique index on '{COLLECTION_NAME}.user_id'")
             collection.create_index([("user_id", ASCENDING)], unique=True)
             logger.info("✅ Index created on user_id.")

        return db
    except Exception as e:
        logger.error(f"Error getting database or ensuring index: {e}")
        return None

def get_user_collection() -> Optional[pymongo.collection.Collection]:
    """Returns the user settings collection."""
    db = get_mongo_db()
    if db is None:
        return None
    try:
        collection = db[COLLECTION_NAME]
        return collection
    except Exception as e:
        logger.error(f"Error getting collection '{COLLECTION_NAME}': {e}")
        return None

# --- Core User Data Functions ---

def get_user_by_id(user_id: str) -> Optional[User]:
    """Fetches a user document by user_id and returns as a Pydantic model."""
    collection = get_user_collection()
    if collection is None:
        return None # Indicate failure to get collection

    try:
        logger.debug(f"Fetching user document for user_id: {user_id}")
        user_doc = collection.find_one({"user_id": user_id})

        if user_doc:
            logger.debug(f"✅ Found user document for {user_id}.")
            # Use the User model to parse the fetched document
            # Pydantic handles mapping _id to id and nesting config
            return User(**user_doc)
        else:
            logger.debug(f"No user document found for {user_id}.")
            return None # Indicate user not found

    except Exception as e:
        logger.error(f"Error fetching user document for {user_id}: {e}")
        return None # Indicate failure

# --- get_user_config (No change needed from previous revision) ---
def get_user_config(user_id: str) -> str | None:
    """
    Fetches the current config prompt for a user from MongoDB.
    Returns the config string on success ('') if not found, or None on critical error.
    """
    collection = get_user_collection()
    if collection is None:
        return None # Indicate critical failure to get collection

    try:
        logger.debug(f"Fetching user config field for user_id: {user_id} with projection.")
        # Use projection to fetch only the 'config.full_instruction_prompt' field and '_id'
        # Note: Projecting a nested field implicitly includes parent dicts
        user_doc = collection.find_one(
            {"user_id": user_id},
            {"projection": {"config.full_instruction_prompt": 1, "_id": 1}}
        )

        if user_doc:
            logger.debug(f"✅ Found user document (projected) for {user_id}.")
            # Safely access the nested config dictionary and the prompt field within it
            config = user_doc.get("config")
            if isinstance(config, dict):
                 # Use .get() for safety in case the nested field is missing in old docs
                 return config.get("full_instruction_prompt", "")
            else:
                 # Handle case where 'config' field is missing or not a dict unexpectedly
                 logger.warning(f"User document for {user_id} has missing or invalid 'config' field.")
                 return "" # Treat as empty config

        else:
            # User document not found - indicates a new user or issue
            logger.debug(f"User document not found for {user_id} during config fetch.")
            return "" # Return empty string for new users, consistent with tweak_agent expectation


    except Exception as e:
        logger.error(f"Error fetching user config for {user_id}: {e}")
        return None # Indicate critical failure

# --- save_user_config (No change needed from previous revision) ---
def save_user_config(user_id: str, updated_instructions: str) -> bool:
    """
    Saves the updated config prompt for a user to MongoDB.
    Uses update_one with upsert=True to create the user document if it doesn't exist.
    Returns True on success, False on critical error.
    """
    collection = get_user_collection()
    if collection is None:
        return False # Indicate critical failure to get collection

    try:
        logger.debug(f"Saving config for user_id: {user_id} to collection: {COLLECTION_NAME}")

        # Use update_one with upsert=True.
        # $set updates the specific nested field.
        # Upsert=True creates the document if user_id is not found,
        # and $set ensures the nested field and parent dicts are created/updated correctly.
        # This handles creation and update in one atomic operation.
        update_result = collection.update_one(
            {"user_id": user_id},
            {"$set": {"config.full_instruction_prompt": updated_instructions}},
            upsert=True # Create document if it doesn't exist
        )

        # Check for acknowledged write and either modified or upserted document
        if update_result.acknowledged:
             if update_result.modified_count > 0:
                logger.debug(f"✅ Config modified for user {user_id}. Modified count: {update_result.modified_count}")
                return True
             elif update_result.upserted_id is not None:
                logger.info(f"✅ Config upserted (user document created) for user {user_id}. Upserted ID: {update_result.upserted_id}")
                return True
             else:
                # Acknowledged write but no modification/upsert means data was identical
                logger.warning(f"⚠️ Config save acknowledged for user {user_id}, but no change made (data identical?).")
                return True # Success as the desired state is achieved
        else:
             logger.error(f"MongoDB write not acknowledged for user {user_id}.")
             return False

    except OperationFailure as e:
        logger.error(f"MongoDB Operation Failure during save for {user_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error during save for {user_id}: {e}")
        return False