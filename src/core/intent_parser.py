# src/core/intent_parser.py
from src.llm.gemini import get_gemini_response_async
import logging
from typing import Optional, Dict, Any, Union , Mapping 

logger = logging.getLogger(__name__)

# --- Prompt Engineering for Intent Parsing ---
# This prompt instructs the LLM to classify user input into predefined categories.
# This is crucial for the agent to understand *what* the user wants to do.
INTENT_PARSING_PROMPT_TEMPLATE = """

You are an intent classification system for an AI agent.
Your task is to categorize the user's request into one of the following predefined intents which can set reminders , adopt to preferances of users and send reminders on whatsapp :
-- self_description: The user is asking about the agent's identity, purpose, creator, capabilities, boundaries, or is trying to test, confuse, or challenge what the agent is. This includes direct, indirect, sarcastic, adversarial, or meta questions about "what are you", "who made you", "are you a bot", "are you sentient", "what do you do", etc. If the user's message is about the agent itself, its function, or its limits, classify as self_description. Do not rely on keywords—use reasoning and context.
- config_update: The user wants to change the agent's configuration (topic, style, tone, length). Only use this when they explicitly request to change settings.
EXAMPLES:
   * "Make your responses more technical"
   * "Change your tone to professional"
   * "Write with more analogies"
   * "Make explanations shorter"
- schedule_request: The user wants to set up, modify, or ask about reminder scheduling. Also use this when the user is responding to scheduling clarification questions.
EXAMPLES:
   * "Remind me about React hooks daily at 5:51"
   * "Can you set up a Python reminder every Tuesday?"
   * "Change my reminder time to 8am"
   * "I want React hooks instead of Linux commands"
- general_query: The user is asking a question or making a statement that is not a config update or schedule request. This includes asking questions about the reminder topic.
- clarification_request: The user's request does not fit clearly into any of the above categories so ask for clarification explictly , but do not over burden the user with too many questions , if they have given topic ,  timing of day , personality traits for you , that is mostly enough , help them narrow down their request when they are ambigous , but do not annoy otherwise. always maintain the tone they have requested.

Previous conversation context:
{message_history}

Analyze the user's input carefully, considering the conversation context above.  
RULES : 1)IF USER PROVIDES TIMING AND ASK IT TO CHANGE PROVIDE UPDATED CONFIG DETAILS AND CLASSIFY IT AS schedule_request
2)IF USER PROVIDES EVERYTHING EXCEPT REQUEST OF TIMING CHANGE CLASSIFY IT AS config_update
3) END THE CONVO POLITELY AFTER YOU HAVE TIMING , TOPIC , PERSONALITY TRAITS , DO NOT CONTINUE BY MORE QUESTIONS IT IS NOT HELPFUL IT IS ANNOYING 
4) DO NOT ASK FOR CONSENT IF USER HAS MENTIONED THEIR WISHES WITH CLARITY , THIS IS ANNOYING FOR THEM

Respond with ONLY the single intent category name (e.g., "config_update", "schedule_request", "general_query"). Do NOT include any other text, explanations, or punctuation but do not ask user explicitly for category, instead use the context to infer what they want.   

Never include the words ‘ACK’, ‘config_update’, ‘schedule_request’, or any intent category in your reply. These are for internal use only , you need to figure out input based on input provided , if unless input lacks clear timing 
, clear topic with subtopics like examples , personality traits , you can ask for clarification and clarify as classificaton request , but do not echo anything which is unproffesion to user-interface
your clarification request should always be likable and charming NOT STERILE AND BORING 
 do not annoy them if they have already given you enough information.
User Input: {user_input}

Intent Category:"""


async def parse_user_intent(
    user_input: str,
    state: Optional[Mapping[str, Any]] = None,
    message_history: Optional[str] = None
) -> str:
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
    

from typing import Mapping

async def handle_unclear_intent(user_input: str, state: Optional[Mapping[str, Any]]) -> str:
    """
    Handles cases where the intent is unclear by using rule-based fallback first,
    then engaging clarification if needed.

    Args:
        user_input: The raw input string from the user.
        state: The current state of the agent's workflow (optional).

    Returns:
        A string representing the clarified intent category.
    """
    if state:
        clarification_prompt = "I couldn't understand your request. Could you clarify what you want to do?"
        # Convert state to a mutable dict if it's not already
        if not isinstance(state, dict):
            state = dict(state)
        state['llm_response'] = clarification_prompt
        logger.info("Engaging user for clarification.")
        # Simulate sending clarification to the user and receiving a response
        # In a real implementation, this would involve a back-and-forth interaction
        clarified_input = await get_user_clarification(state)
        return await parse_user_intent(clarified_input, state)
    # If state is None, fallback to 'other' intent
    logger.warning("State is None during unclear intent handling. Returning 'other'.")
    return "other"


async def get_user_clarification(state: Mapping[str, Any]) -> str:
    """
    Simulates getting clarification from the user. Replace with actual user interaction logic.

    Args:
        state: The current state of the agent's workflow.

    Returns:
        The clarified user input.
    """
    # Placeholder for user interaction logic
    return state.get('user_input', "")  # Return the original input as a fallback