# src/config/constants.py
"""
Application constants used across modules.
This prevents circular imports by providing a central location for shared constants.
"""

# Default context windows for different handlers
DEFAULT_CONTEXT_WINDOW = 7  # Standardize context window across handlers
GENERAL_QUERY_CONTEXT = 7
ACKNOWLEDGE_CONTEXT = 7
SCHEDULE_LIMIT_PER_USER = 1  # Maximum number of schedules allowed per user (default 1)
    