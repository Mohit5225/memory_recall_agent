import os
from dotenv import load_dotenv
from typing import Optional

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



# --- Redis Settings for Celery ---
REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT: int = int(os.getenv("REDIS_PORT", 6379))
REDIS_PASSWORD: Optional[str] = os.getenv("REDIS_PASSWORD")
REDIS_DB: int = int(os.getenv("REDIS_DB", 0))

REDIS_DB_OTP = 1

# Celery Broker and Backend URL (using Redis)
# Construct URL based on settings
# If using password: f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
CELERY_BROKER_URL: str = os.getenv("REDIS_URL", f"redis://{REDIS_HOST}:{REDIS_PORT}/0") # Default to DB 0
CELERY_RESULT_BACKEND: str = os.getenv("REDIS_URL", f"redis://{REDIS_HOST}:{REDIS_PORT}/0") # Same as broker for simplicity


TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")  
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")   
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")  
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")

# --- OAuth Security Settings ---
OAUTH_REQUIRE_EMAIL_VERIFICATION = os.getenv("OAUTH_REQUIRE_EMAIL_VERIFICATION", "true").lower() == "true"
OAUTH_BLOCK_DISPOSABLE_EMAILS = os.getenv("OAUTH_BLOCK_DISPOSABLE_EMAILS", "true").lower() == "true"
OAUTH_ALLOWED_DOMAINS = [domain.strip() for domain in os.getenv("OAUTH_ALLOWED_DOMAINS", "").split(",") if domain.strip()]
OAUTH_MAX_LOGIN_ATTEMPTS = int(os.getenv("OAUTH_MAX_LOGIN_ATTEMPTS", "5"))
OAUTH_RATE_LIMIT_WINDOW = int(os.getenv("OAUTH_RATE_LIMIT_WINDOW", "300"))  # 5 minutes

OTP_REDIS_URL = os.getenv("OTP_REDIS_URL")  # e.g. "https://integral-mantis-55410.upstash.io"
OTP_REDIS_TOKEN = os.getenv("OTP_REDIS_TOKEN")  # e.g. "AdhyAAIjcDE0ZTk5YjVkMGJjYzE0ZDU2OGJkMTcyMDQyMjY3NWVmM3AxMA"
 
OPENROUTER_SECRET_KEY = os.getenv("OPENROUTER_SECRET_KEY")

OPENROUTER_FALLBACK_MODELS = [
    "openai/gpt-oss-20b:free",
    "meta-llama/llama-3.1-70b-instruct:free",
    "nvidia/llama-3.1-nemotron-70b-instruct:free",
    "google/gemini-flash-1.5-8b:free",

    # "qwen/qwen3-235b-a22b:free",
    # "moonshotai/kimi-dev-72b:free",  
    #  "qwen/qwen-2.5-coder-32b-instruct:free",
    # "deepseek/deepseek-r1-0528:free",
]



model_sequence = ["qwen/qwen3-235b-a22b:free", "deepseek/deepseek-r1-0528:free", "qwen/qwen-2.5-coder-32b-instruct:free"]

OPENROUTER_SELF_DESCRIPTION_MAX_RETRIES = int(os.getenv("OPENROUTER_SELF_DESCRIPTION_MAX_RETRIES", "3"))