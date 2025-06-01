# src/core/intent_parser.py
from  src.llm.gemini import get_gemini_response_async
import logging

logger = logging.getLogger(__name__)

# --- Prompt Engineering for Intent Parsing ---
# This prompt instructs the LLM to classify user input into predefined categories.
# This is crucial for the agent to understand *what* the user wants to do.
INTENT_PARSING_PROMPT_TEMPLATE = """
You are an intent classification system for an AI agent.
Your task is to categorize the user's request into one of the following predefined intents:

- config_update: The user wants to change the agent's configuration (topic, style, tone, length).
- schedule_request: The user wants to set up, modify, or ask about reminder scheduling.
- general_query: The user is asking a question or making a statement that is not a config update or schedule request. This includes asking questions about the reminder topic.
- acknowledge: The user is simply acknowledging something or saying thanks (e.g., "ok", "got it", "thanks").
- other: The user's request does not fit clearly into any of the above categories.

Analyze the user's input carefully. Respond with ONLY the single intent category name (e.g., "config_update", "schedule_request", "general_query"). Do NOT include any other text, explanations, or punctuation.

User Input: {user_input}

Intent Category:"""


async def parse_user_intent(user_input: str) -> str:
    """
    Uses the LLM to classify the user's input into a predefined intent category.

    Args:
        user_input: The raw input string from the user.

    Returns:
        A string representing the classified intent category. Defaults to 'other' on error.
    """
    logger.info(f"Attempting to parse intent for input: '{user_input[:50]}...'")

    llm_prompt = INTENT_PARSING_PROMPT_TEMPLATE.format(user_input=user_input).strip()

    try:
        # Call the LLM via the gemini module
        intent_raw = await get_gemini_response_async(llm_prompt)

        if intent_raw is None:
            logger.error("LLM returned None for intent parsing.")
            return "other" # Default to 'other' on LLM failure

        # Basic cleaning of LLM output to get just the intent string
        intent = intent_raw.strip().lower()

        # Validate the intent against expected categories (basic check)
        valid_intents = ["config_update", "schedule_request", "general_query", "acknowledge", "other"]
        if intent not in valid_intents:
             logger.warning(f"LLM returned unexpecte    d intent: '{intent}'. Defaulting to 'other'.")
             return "other"

        logger.info(f"✅ Parsed intent: '{intent}'")
        return intent

    except Exception as e:
        logger.error(f"Error during intent parsing for input '{user_input[:50]}...': {e}", exc_info=True)
        return "other" # Default to 'other' on unexpected x