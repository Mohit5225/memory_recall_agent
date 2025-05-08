import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Application Settings ---
# Read Google AI Studio API Key from .env
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Read MongoDB Connection String from .env
MONGODB_CONNECTION_STRING = os.getenv("MONGODB_CONNECTION_STRING")

# --- Database Settings ---
DB_NAME = os.getenv("DB_NAME", "your_llm_agent_db") # Default DB name if not in .env
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "user_settings") # Default Collection name

# --- LLM Settings ---
# You could add model names, temperatures etc. here later
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "gemini-1.5-flash") # Default LLM model