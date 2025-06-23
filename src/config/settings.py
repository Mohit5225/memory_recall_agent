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

# --- OAuth Security Settings ---
OAUTH_REQUIRE_EMAIL_VERIFICATION = os.getenv("OAUTH_REQUIRE_EMAIL_VERIFICATION", "true").lower() == "true"
OAUTH_BLOCK_DISPOSABLE_EMAILS = os.getenv("OAUTH_BLOCK_DISPOSABLE_EMAILS", "true").lower() == "true"
OAUTH_ALLOWED_DOMAINS = [domain.strip() for domain in os.getenv("OAUTH_ALLOWED_DOMAINS", "").split(",") if domain.strip()]
OAUTH_MAX_LOGIN_ATTEMPTS = int(os.getenv("OAUTH_MAX_LOGIN_ATTEMPTS", "5"))
OAUTH_RATE_LIMIT_WINDOW = int(os.getenv("OAUTH_RATE_LIMIT_WINDOW", "300"))  # 5 minutes

# --- LLM Settings ---
# You could add model names, temperatures etc. here later
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "gemini-1.5-flash") # Default LLM model



# --- Redis Settings for Celery ---
REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT: int = int(os.getenv("REDIS_PORT", 6379))
# Optional: REDIS_PASSWORD: Optional[str] = os.getenv("REDIS_PASSWORD")
# Optional: REDIS_DB: int = int(os.getenv("REDIS_DB", 0))


# Celery Broker and Backend URL (using Redis)
# Construct URL based on settings
# If using password: f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
CELERY_BROKER_URL: str = os.getenv("REDIS_URL", f"redis://{REDIS_HOST}:{REDIS_PORT}/0") # Default to DB 0
CELERY_RESULT_BACKEND: str = os.getenv("REDIS_URL", f"redis://{REDIS_HOST}:{REDIS_PORT}/0") # Same as broker for simplicity


# --- Twilio Settings (Future) ---
# TWILIO_ACCOUNT_SID: Optional[str] = os.getenv("TWILIO_ACCOUNT_SID")
# TWILIO_AUTH_TOKEN: Optional[str] = os.getenv("TWILIO_AUTH_TOKEN")
# TWILIO_PHONE_NUMBER: Optional[str] = os.getenv("TWILIO_PHONE_NUMBER")
