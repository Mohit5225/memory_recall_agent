import pymongo
from src.config.settings import MONGODB_CONNECTION_STRING, DB_NAME, COLLECTION_NAME
import logging

logging.basicConfig(level=logging.INFO)

def get_mongo_client():
    """Establishes and returns a MongoDB client connection."""
    if not MONGODB_CONNECTION_STRING or MONGODB_CONNECTION_STRING == "YOUR_MONGODB_CONNECTION_STRING":
         logging.error("MongoDB connection string not configured.")
         return None
         
    client = None # Initialize client to None
    try:
        logging.info("Attempting to connect to MongoDB...")
        # Use a timeout to prevent hanging indefinitely
        client = pymongo.MongoClient(MONGODB_CONNECTION_STRING, serverSelectionTimeoutMS=5000)
        # The ismaster command is cheap and does not require auth.
        client.admin.command('ismaster')
        logging.info("✅ MongoDB connection successful.")
        return client
    except pymongo.errors.ConnectionFailure as e:
        logging.error(f"MongoDB connection failed: {e}")
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred during MongoDB connection: {e}")
        return None


def get_user_config(user_id: str) -> str | None:
    """Fetches the current config for a user from MongoDB."""
    client = get_mongo_client()
    if client is None:
        return None # Failed to get client

    try:
        db = client[DB_NAME]
        collection = db[COLLECTION_NAME]
        logging.info(f"Querying collection '{COLLECTION_NAME}' for user_id: {user_id}")
        user_doc = collection.find_one({"user_id": user_id})

        if user_doc:
            logging.info(f"✅ Found config for user {user_id}.")
            # Return the full instruction prompt if it exists
            return user_doc.get("full_instruction_prompt", "")
        else:
            logging.info(f"No existing config found for {user_id}.")
            # Return an empty string or a default string if user doc doesn't exist
            # The core logic layer (tweak_agent) will handle providing the full default if needed.
            return ""

    except Exception as e:
        logging.error(f"Error fetching user config for {user_id}: {e}")
        return None # Indicate failure
    finally:
        if client:
            client.close()


def save_user_config(user_id: str, updated_instructions: str) -> bool:
    """Saves the updated config for a user to MongoDB."""
    client = get_mongo_client()
    if client is None:
        return False # Failed to get client

    try:
        db = client[DB_NAME]
        collection = db[COLLECTION_NAME]
        logging.info(f"Saving config for user_id: {user_id} to collection: {COLLECTION_NAME}")

        # Use upsert=True to create the document if the user_id doesn't exist yet
        update_result = collection.update_one(
            {"user_id": user_id},
            {"$set": {"full_instruction_prompt": updated_instructions}},
            upsert=True,
        )

        if update_result.modified_count > 0:
            logging.info(f"✅ Config modified for user {user_id}. Modified count: {update_result.modified_count}")
            return True
        elif update_result.upserted_id is not None:
            logging.info(f"✅ Config upserted for user {user_id}. Upserted ID: {update_result.upserted_id}")
            return True
        else:
            # This might happen if the data you're trying to save is identical to existing data
            logging.warning(f"⚠️ No changes made for user {user_id} (document already has these values or no change needed).")
            return True # Consider this a success as the desired state is achieved

    except pymongo.errors.OperationFailure as e:
        logging.error(f"MongoDB Operation Failure during save for {user_id}: {e}")
        return False
    except Exception as e:
        logging.error(f"Unexpected error during save for {user_id}: {e}")
        return False
    finally:
        if client:
            client.close()