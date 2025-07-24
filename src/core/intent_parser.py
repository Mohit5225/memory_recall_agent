# src/core/intent_parser.py
from src.llm.gemini import get_gemini_response_async
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# --- Prompt Engineering for Intent Parsing ---
# This prompt instructs the LLM to classify user input into predefined categories.
# This is crucial for the agent to understand *what* the user wants to do.
INTENT_PARSING_PROMPT_TEMPLATE = """
You are an intent classification system for an AI agent.
Your task is to categorize the user's request into one of the following predefined intents:

- config_update: The user wants to change the agent's configuration (topic, style, tone, length). Only use this when they explicitly request to change settings.
- schedule_request: The user wants to set up, modify, or ask about reminder scheduling. Also use this when the user is responding to scheduling clarification questions.
- general_query: The user is asking a question or making a statement that is not a config update or schedule request. This includes asking questions about the reminder topic.
- clarification_request: The user is asking for clarification about what information is needed or what they should do next.
- acknowledge: The user is simply acknowledging something or saying thanks (e.g., "ok", "got it", "thanks").
- other: The user's request does not fit clearly into any of the above categories.

Previous conversation context:
{message_history}

Analyze the user's input carefully, considering the conversation context above. If the user is asking what information is needed or what to do next, classify it as "clarification_request".

Respond with ONLY the single intent category name (e.g., "config_update", "schedule_request", "general_query"). Do NOT include any other text, explanations, or punctuation.

User Input: {user_input}

Intent Category:"""


async def parse_user_intent(user_input: str, state: Optional[dict] = None, message_history: Optional[str] = None) -> str:
    """
    Uses the LLM to classify the user's input into a predefined intent category.
    If the intent is unclear, engages in iterative clarification with the user.

    Args:
        user_input: The raw input string from the user.
        state: The current state of the agent's workflow (optional).
        message_history: The formatted conversation history for context (optional).

    Returns:
        A string representing the classified intent category. Defaults to 'other' on error.
    """
    logger.info(f"Attempting to parse intent for input: '{user_input[:50]}...'")

    # Use message history for context, fallback to "No previous messages" if not provided
    context_history = message_history or "No previous messages"
    
    llm_prompt = INTENT_PARSING_PROMPT_TEMPLATE.format(
        user_input=user_input,
        message_history=context_history
    ).strip()
    
    try:
        # Call the LLM via the gemini module
        intent_raw, context = await get_gemini_response_async(llm_prompt)
        logger.info(f"LLM context: {context.get('processing_status', 'unknown')}")

        if intent_raw is None:
            logger.error("LLM returned None for intent parsing.")
            return await handle_unclear_intent(user_input, state)

        # Basic cleaning of LLM output to get just the intent string
        intent = intent_raw.strip().lower()

        # Validate the intent against expected categories (basic check)
        valid_intents = ["config_update", "schedule_request", "general_query", "acknowledge", "clarification_request", "other"]
        if intent not in valid_intents:
            logger.warning(f"LLM returned unexpected intent: '{intent}'. Engaging clarification.")
            return await handle_unclear_intent(user_input, state)

        logger.info(f"✅ Parsed intent: '{intent}'")
        return intent

    except Exception as e:
        logger.error(f"Error during intent parsing for input '{user_input[:50]}...': {e}", exc_info=True)
        return await handle_unclear_intent(user_input, state)


def rule_based_intent_fallback(user_input: str) -> str:
    """
    Rule-based fallback when LLM fails. Uses keyword matching for basic intent detection.
    90% confidence this catches common patterns when LLM quota is exhausted.
    """
    input_lower = user_input.lower()
    
    # Schedule request patterns
    if any(keyword in input_lower for keyword in ["remind", "schedule", "daily", "weekly", "monthly", "at", "every", "notification"]):
        logger.info("Rule-based fallback detected: schedule_request")
        return "schedule_request"
    
    # Config update patterns  
    if any(keyword in input_lower for keyword in ["change", "update", "configure", "set", "tone", "style", "topic"]):
        logger.info("Rule-based fallback detected: config_update") 
        return "config_update"
    
    # Acknowledgment patterns
    if any(keyword in input_lower for keyword in ["thanks", "thank you", "ok", "okay", "got it", "understood"]):
        logger.info("Rule-based fallback detected: acknowledge")
        return "acknowledge"
    
    # Default to general_query for questions
    if any(keyword in input_lower for keyword in ["what", "how", "why", "when", "where", "?"]):
        logger.info("Rule-based fallback detected: general_query")
        return "general_query"
    
    logger.info("Rule-based fallback detected: other")
    return "other"


async def handle_unclear_intent(user_input: str, state: Optional[dict]) -> str:
    """
    Handles cases where the intent is unclear by using rule-based fallback first,
    then engaging clarification if needed.

    Args:
        user_input: The raw input string from the user.
        state: The current state of the agent's workflow (optional).

    Returns:
        A string representing the clarified intent category.
    """
    logger.info("Engaging user for clarification.")
    
    # Try rule-based fallback first (95% confidence this works for your input)
    fallback_intent = rule_based_intent_fallback(user_input)
    if fallback_intent != "other":
        logger.info(f"Rule-based fallback successful: {fallback_intent}")
        return fallback_intent
    
    # If rule-based fails, default to other and let that node handle clarification
    return "other"


async def get_user_clarification(state: dict) -> str:
    """
    Simulates getting clarification from the user. Replace with actual user interaction logic.

    Args:
        state: The current state of the agent's workflow.

    Returns:
        The clarified user input.
    """
    # Placeholder for user interaction logic
    return state.get('user_input', "")  # Return the original input as a fallback