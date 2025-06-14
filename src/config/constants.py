# src/config/constants.py
"""
Application constants used across modules.
This prevents circular imports by providing a central location for shared constants.
"""

# Default context windows for different handlers
DEFAULT_CONTEXT_WINDOW = 7  # Standardize context window across handlers
GENERAL_QUERY_CONTEXT = 7
ACKNOWLEDGE_CONTEXT = 7

# --- LLM Error Handling and Monitoring Constants ---
# Retry logic constants
RETRYABLE_ERROR_TYPES = {"rate_limit", "quota_exceeded", "network_error", "timeout"}
CRITICAL_ERROR_TYPES = {"api_key_invalid", "authentication_failed"}
MAX_CONTEXT_RETRY_ATTEMPTS = 2  # Additional retries based on context for specific error types

# Monitoring and metrics
LLM_SUCCESS_RATE_THRESHOLD = 0.85  # Alert if success rate drops below 85%
LLM_METRICS_LOG_INTERVAL = 100  # Log metrics every N calls

# User-friendly error messages
USER_FRIENDLY_ERROR_MESSAGES = {
    "api_key_invalid": "The AI service is temporarily unavailable due to a configuration issue. Please try again later.",
    "quota_exceeded": "The AI service has reached its daily limit. Please try again later or contact support.",
    "rate_limit": "The AI service is busy right now. Please wait a moment and try again.",
    "max_retries": "The AI service is experiencing issues. Please try again in a few minutes.",
    "network_error": "There was a connection issue with the AI service. Please check your internet connection and try again.",
    "timeout": "The AI service took too long to respond. Please try again.",
    "unknown": "The AI service encountered an unexpected issue. Please try again or contact support if the problem persists."
}
