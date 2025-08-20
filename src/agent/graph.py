 # src/agent/graph.py
from langgraph.graph import StateGraph, END

from src import config
from .state import AgentState
from src.core.tweak_agent import process_user_instruction
from src.core.intent_parser import parse_user_intent
from src.core.schedular import schedule_reminder_task, DatabaseError
from src.llm.gemini import get_gemini_response_async
from src.models.message import Message, ProcessingStatus # Ensure ProcessingStatus is imported
from motor.motor_asyncio import AsyncIOMotorClient # Import AsyncIOMotorClient
# Import get_mongo_client and DatabaseError from src.db.mongo
from src.db.mongo import get_mongo_client, DatabaseError 
from src.config.constants import DEFAULT_CONTEXT_WINDOW, GENERAL_QUERY_CONTEXT, ACKNOWLEDGE_CONTEXT
from src.config.settings import DB_NAME # Import DB_NAME
from typing import List, Optional, Dict, Any, Literal
import logging
from datetime import datetime # Ensure datetime is imported
import asyncio
from bson import ObjectId  # Import ObjectId for MongoDB document IDs
from hashlib import sha1  # Import sha1 for deterministic ID generation
from src.llm.openrouter import get_openrouter_chain_response_async
from src.config.settings import OPENROUTER_FALLBACK_MODELS, OPENROUTER_SELF_DESCRIPTION_MAX_RETRIES
from src.core.self_description import SELF_DESCRIPTION_TEMPLATE, STATIC_SELF_DESCRIPTION_FALLBACK
from src.agent import state

logger = logging.getLogger(__name__)

# Use constants from config instead of redefining them
CLARIFICATION_CONTEXT = 7

# --- Helper Functions ---

def _generate_deterministic_id(msg: dict) -> ObjectId:
    key = f"{msg['user_id']}|{msg.get('content','')}"
    return ObjectId(sha1(key.encode()).digest()[:12])

async def save_messages_atomically(user_id: str, messages: List[Message]) -> bool:
    client: Optional[AsyncIOMotorClient] = await get_mongo_client()
    if not client:
        logger.error("get_mongo_client() returned None.")
        return False

    coll = client[DB_NAME]["messages"]
    try:
        async with await client.start_session() as session:
            async with session.start_transaction():
                for msg in messages:
                    md = msg.model_dump()
                    md["user_id"] = user_id

                    # update last_attempt whenever we transition out of PENDING
                    if msg.processing_status in (
                        ProcessingStatus.PROCESSING,
                        ProcessingStatus.COMPLETED,
                        ProcessingStatus.FAILED
                    ):
                        md["last_attempt"] = datetime.utcnow()

                    # 1) generate a consistent _id so we can upsert
                    if not md.get("_id"):
                        md["_id"] = _generate_deterministic_id(md)

                    # 2) upsert by that _id
                    await coll.update_one(
                        {"_id": md["_id"]},
                        {"$set": md},
                        upsert=True,
                        session=session
                    )
        return True
    except Exception as exc:
        logger.error(f"Transaction failed: {exc}", exc_info=True)
        return False
def format_message_history(messages: List[Message], limit: Optional[int] = None) -> str:
    """Format message history for LLM context with proper windowing."""
    if not messages:
        return "No previous messages"
    
    if limit and len(messages) > limit:
        messages = messages[-limit:]
    
    # Format each message with role and content
    formatted_messages = []
    for msg in messages:
        role_prefix = "User" if msg.role == "user" else "Assistant"
        formatted_messages.append(f"{role_prefix}: {msg.content}")
        
    return "\n".join(formatted_messages)

def create_message(user_id: str, content: str, role: Literal["user", "assistant"], context: Optional[dict] = None, processing_status: ProcessingStatus = ProcessingStatus.PENDING) -> Message:
    """Create a new Message object with standardized format and metadata."""
    return Message(
        user_id=user_id,
        content=content,
        role=role,
        timestamp=datetime.utcnow(),  # Ensure proper ordering
        context=context or {},
        processing_status=processing_status
    )

# --- LLM Prompt Templates ---
GENERAL_QUERY_PROMPT = """You are a helpful AI assistant responding to a user query.
Context about the user and conversation:
User ID: {user_id}
Current configuration: {config}
Previous messages: {message_history}
Current query: {query}

Generate a helpful, contextual response addressing their query do not ask for timezone and country ever
Keep the response focused, and tone as requested , and relevant to their question.
If you need more information, ask a specific follow-up question."""

ACKNOWLEDGE_PROMPT = """Generate an acknowledgment response.
Context:
User ID: {user_id}
Their message: {query}
Previous messages: {message_history}
Current configuration: {config}

Generate a natural, contextual acknowledgment that:
1. Shows you understood their message in defined {style}Respond directly to the user's question
2. References relevant context from the conversation
3. strictly follow tone and speaking manner user have described in earlier or current request
4. keep response concise (1-2 sentences)
5.do not ask for timezone and country ever
6. Format using markdown with headings, bullet points, and code blocks as appropriate
"""

CLARIFICATION_PROMPT = """The user's intent is unclear and needs clarification.
Context:
User ID: {user_id}
Their message: {query}
Previous messages: {message_history}
Current configuration: {config}

Available intents: config_update, schedule_request, general_query

Generate a clarifying question that:
1. Acknowledges what you understood from their message
2. Asks specifically about what's unclear
3. If relevant, references their previous interactions
4. Gives examples of what you're looking for
5. do not ask for timezone and location ever !
6. strictly follow tone and speaking manner user have described in earlier or current request

"""
# --- Node Definitions ---

async def entry_node(state: AgentState) -> AgentState:
    """Initial entry point of the graph. Sets up message context and pruning."""
    logger.info(f"--- Starting interaction for user: {state['user_id']} ---")
    
    # Initialize processing status tracking
    state['processing_status'] = ProcessingStatus.PROCESSING
    state['processing_attempts'] = state.get('processing_attempts', 0) + 1
    state['started_at'] = datetime.utcnow()
    
    # Set fixed context window
    state['context_window'] = DEFAULT_CONTEXT_WINDOW
    
    # Ensure messages are properly windowed
    messages = state.get('messages', [])
    if len(messages) > DEFAULT_CONTEXT_WINDOW:
        state['messages'] = messages[-DEFAULT_CONTEXT_WINDOW:]  # Keep most recent N messages
    
    # Initialize empty lists if needed
    if not state.get('messages'):
        state['messages'] = []
    
    logger.info(f"Entry node initialized with {len(state.get('messages', []))} messages in context window")
    return state

async def call_intent_parser( state: AgentState) -> AgentState:
    """Parses intent with message history context."""
    logger.info(f"--- Executing Intent Parsing Node for user: {state['user_id']} ---")
    
    messages = state.get('messages', [])
    context_window = state.get('context_window', CLARIFICATION_CONTEXT)
    message_history = format_message_history(messages, context_window)
    user_input = messages[-1].content if messages else ""
    parsed_intent = await parse_user_intent(

        user_input=user_input,
        state=state,
        message_history=message_history
    )
    logger.info(f"Intent Parsing Node identified intent: '{parsed_intent}'")
    
    state['parsed_intent'] = parsed_intent or "other"
    return state

async def handle_general_query(state: AgentState) -> AgentState:
    """Handles general queries with standardized message handling."""
    logger.info(f"--- Handling General Query for user: {state['user_id']} ---")
    
    messages = state.get('messages', [])
    context_window = state.get('context_window', GENERAL_QUERY_CONTEXT)
    message_history = format_message_history(messages, context_window)
    user_id = state['user_id']
    user_query = state['user_input']
    config = state.get('current_config_prompt', '')
    
    try:
        prompt = GENERAL_QUERY_PROMPT.format(
            user_id=user_id,
            config=config,
            message_history=message_history,
            query=user_query,
            context_window=context_window
        )
        
        llm_response, context = await get_gemini_response_async(prompt)
        logger.info(f"LLM context: {context.get('processing_status', 'unknown')}")
        
        if not llm_response:
            logger.error("Failed to get LLM response for general query")
            fallback_response = "I'm sorry, I couldn't process your request. Please try again later."
            new_messages = [
                create_message(
                    user_id=user_id,
                    content=state['user_input'],
                    role="user",
                    context={"handler": "general_query", "sequence": len(messages)},
                    processing_status=ProcessingStatus.COMPLETED  # User input completed
                ),
                create_message(
                    user_id=user_id,
                    content=fallback_response,
                    role="assistant",
                    context={"error": "llm_failure", "handler": "general_query"},
                    processing_status=ProcessingStatus.FAILED
                )
            ]
            await save_messages_atomically(user_id, new_messages)
            
            # Update state status tracking
            state['processing_status'] = ProcessingStatus.FAILED
            state['error_details'] = "LLM response generation failed"
            state['completed_at'] = datetime.utcnow()
            
            return {
                **state,
                "llm_response": fallback_response,
                "final_outcome": "LLM response generation failed",
                "messages": messages[-context_window:] + new_messages
            }
        
        # Create message objects for successful transaction
        new_messages = [
            create_message(
                user_id=user_id,
                content=state['user_input'],
                role="user",
                context={"handler": "general_query", "sequence": len(messages)},
                processing_status=ProcessingStatus.COMPLETED  # User input completed
            ),
            create_message(
                user_id=user_id,
                content=llm_response,
                role="assistant",
                context={"handler": "general_query", "sequence": len(messages) + 1},
                processing_status=ProcessingStatus.COMPLETED  # Assistant response completed
            )
        ]
        
        # Save messages atomically
        if not await save_messages_atomically(user_id, new_messages):
            raise Exception("Failed to save messages atomically")
        
        # Update state with success status
        state['processing_status'] = ProcessingStatus.COMPLETED
        state['completed_at'] = datetime.utcnow()
        
        # Update state with windowed messages
        updated_messages = (messages + new_messages)[-context_window:]
        
        return {
            **state,
            "llm_response": llm_response,
            "messages": updated_messages
        }
        
    except Exception as e:
        logger.error(f"Error in general_query handler: {e}", exc_info=True)
        fallback_response = "I encountered an error processing your request. Please try again."
        new_messages = [
            create_message(
                user_id=user_id,
                content=state['user_input'], 
                role="user",
                processing_status=ProcessingStatus.COMPLETED  # User input completed
            ),
            create_message(
                user_id=user_id,
                content=fallback_response, 
                role="assistant", 
                context={"error": str(e), "handler": "general_query"},
                processing_status=ProcessingStatus.FAILED
            )
        ]
        # Try to save error messages atomically
        await save_messages_atomically(user_id, new_messages)
        
        # Update state status tracking
        state['processing_status'] = ProcessingStatus.FAILED
        state['error_details'] = str(e)
        state['completed_at'] = datetime.utcnow()
        
        return {
            **state,
            "llm_response": fallback_response,
            "final_outcome": f"Error in general query handler: {str(e)}",
            "messages": messages[-context_window:] + new_messages
        }

async def handle_acknowledge(state: AgentState) -> AgentState:
    """Handles acknowledgment intents with standardized message handling."""
    logger.info(f"--- Handling Acknowledge Intent for user: {state['user_id']} ---")
    
    messages = state.get('messages', [])
    context_window = state.get('context_window', ACKNOWLEDGE_CONTEXT)
    message_history = format_message_history(messages, context_window)
    user_id = state['user_id']
    user_query = state['user_input']
    config = state.get('current_config_prompt', '')
    try:
        prompt = ACKNOWLEDGE_PROMPT.format(
            user_id=user_id,
            query=state['user_input'],
            message_history=message_history,
            config=config
        )
        
        llm_response, context = await get_gemini_response_async(prompt)
        logger.info(f"LLM context: {context.get('processing_status', 'unknown')}")
        
        if not llm_response:
            logger.error("Failed to get LLM response for acknowledgment")
            fallback_response = "Thank you for your message. Is there anything else I can help with?"
            new_messages = [
                create_message(
                    user_id=user_id,
                    content=state['user_input'], 
                    role="user",
                    context={"handler": "general_query", "sequence": len(messages)},
                    processing_status=ProcessingStatus.COMPLETED
                ),
                create_message(
                    user_id=user_id,
                    content=fallback_response,
                    role="assistant",
                    context={"handler": "general_query", "fallback": True},
                    processing_status=ProcessingStatus.FAILED
                )
            ]
            if not await save_messages_atomically(user_id, new_messages):
                raise Exception("Failed to save messages atomically")
            
            # Update state status tracking
            state['processing_status'] = ProcessingStatus.FAILED
            state['error_details'] = "LLM response generation failed"
            state['completed_at'] = datetime.utcnow()
            updated_messages = (messages + new_messages)[-context_window:]
            
            return {
                **state,
                "llm_response": llm_response or "",
                "final_outcome": llm_response or "",
                "messages": updated_messages
            }
        
        # Create and save messages atomically with proper status
        new_messages = [
            create_message(
                user_id=user_id,
                content=state['user_input'], 
                role="user",
                 context={"handler": "general_query", "sequence": len(messages)},
                processing_status=ProcessingStatus.COMPLETED
            ),
            create_message(
                user_id=user_id,
                content=llm_response, 
                role="assistant",
                context={"handler": "general_query", "sequence": len(messages) + 1},
                processing_status=ProcessingStatus.COMPLETED
            )
        ]
        
        if not await save_messages_atomically(user_id, new_messages):
            raise Exception("Failed to save messages atomically")
        
        # Update state with success status
        state['processing_status'] = ProcessingStatus.COMPLETED
        state['completed_at'] = datetime.utcnow()
        
        return {
            **state,
            "llm_response": llm_response,
            "final_outcome": "Acknowledgment handled successfully",
            "messages": messages + new_messages
        }
        
    except Exception as e:
        logger.error(f"Error in handle_acknowledge: {e}", exc_info=True)
        fallback_response = "Thank you. Let me know if you need anything else."
        new_messages = [
            create_message(
                user_id=user_id,
                content=state['user_input'], 
                role="user",
                processing_status=ProcessingStatus.COMPLETED
            ),
            create_message(
                user_id=user_id,
                content=fallback_response,
                role="assistant",
                context={"error": str(e)},
                processing_status=ProcessingStatus.FAILED
            )
        ]
        # Try to save error messages atomically
        await save_messages_atomically(user_id, new_messages)
        
        # Update state status tracking
        state['processing_status'] = ProcessingStatus.FAILED
        state['error_details'] = str(e)
        state['completed_at'] = datetime.utcnow()
        
        return {
            **state,
            "llm_response": fallback_response,
            "final_outcome": f"Error in acknowledge handler: {str(e)}",
            "messages": messages + new_messages
        }

async def handle_self_description(state: AgentState) -> AgentState:
    """
    Handles self_description intent using OpenRouter multi-model fallback chain.
    Injects message history for context; falls back to static narrative if all fail.
    """
    user_id = state['user_id']
    user_query = state['user_input']
    # Gather recent messages if present
    messages: List[Message] = state.get("messages", [])  # type: ignore
    history_text = ""
    if messages:
        try:
            history_text = format_message_history(messages, limit=DEFAULT_CONTEXT_WINDOW)
        except Exception as e:
            logger.warning(f"[SELF_DESC] Failed to format history: {e}")

    system_prompt = SELF_DESCRIPTION_TEMPLATE
    user_prompt = f"User identity/purpose probe:\n{user_query}\nRespond per system identity discipline."

    llm_text, context = await get_openrouter_chain_response_async(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        message_history=history_text,
        model_sequence=OPENROUTER_FALLBACK_MODELS,
        max_retries_per_model=OPENROUTER_SELF_DESCRIPTION_MAX_RETRIES
    )

    if not llm_text:
        logger.error("[SELF_DESC] Falling back to static self-description payload.")
        # Personalize fallback slightly with user tail if possible
        tail = (user_query[:120] + "...") if len(user_query) > 120 else user_query
        fallback = STATIC_SELF_DESCRIPTION_FALLBACK + f"\n\n(Original probe context captured: \"{tail}\")"
        state['llm_response'] = fallback
        state['processing_status'] = ProcessingStatus.COMPLETED
        state['error_details'] = context.get("error_details") or ""
        state['llm_meta'] = context
        return state

    state['llm_response'] = llm_text
    state['processing_status'] = ProcessingStatus.COMPLETED
    state['llm_meta'] = context
    return state


async def handle_other_intent(state: AgentState) -> AgentState:
    """Handles unclear intents with standardized message handling."""
    logger.info(f"--- Handling Other Intent for user: {state['user_id']} ---")
    
    messages = state.get('messages', [])
    context_window = state.get('context_window', CLARIFICATION_CONTEXT)
    message_history = format_message_history(messages, context_window)
    user_id = state['user_id']
    config = state.get('current_config_prompt', '')
    try:
        prompt = CLARIFICATION_PROMPT.format(
            user_id=user_id,
            query=state['user_input'],
            message_history=message_history,
            config=config,
            
        )
        
        llm_response, context = await get_gemini_response_async(prompt)
        logger.info(f"LLM context: {context.get('processing_status', 'unknown')}")
        
        if not llm_response:
            logger.error("Failed to get LLM response for clarification")
            fallback_response = "I'm not sure I understand. Could you please rephrase your request, specifying if you want to schedule something, update settings, or ask a question?"
            new_messages = [
                create_message(
                    user_id=user_id,
                    content=state['user_input'], 
                    role="user",
                    processing_status=ProcessingStatus.COMPLETED
                ),
                create_message(
                    user_id=user_id,
                    content=fallback_response,
                    role="assistant",
                    context={"error": "llm_failure"},
                    processing_status=ProcessingStatus.FAILED
                )
            ]
            await save_messages_atomically(user_id, new_messages)
            
            # Update state status tracking
            state['processing_status'] = ProcessingStatus.FAILED
            state['error_details'] = "LLM response generation failed"
            state['completed_at'] = datetime.utcnow()
            
            return {
                **state,
                "llm_response": fallback_response,
                "final_outcome": "Used fallback clarification",
                "messages": messages + new_messages
            }
        
        # Create and save messages atomically with proper status
        new_messages = [
            create_message(
                user_id=user_id,
                content=state['user_input'], 
                role="user",
                processing_status=ProcessingStatus.COMPLETED
            ),
            create_message(
                user_id=user_id,
                content=llm_response, 
                role="assistant",
                processing_status=ProcessingStatus.COMPLETED
            )
        ]
        
        if not await save_messages_atomically(user_id, new_messages):
            raise Exception("Failed to save messages atomically")
        
        # Update state with success status
        state['processing_status'] = ProcessingStatus.COMPLETED
        state['completed_at'] = datetime.utcnow()
        
        return {
            **state,
            "llm_response": llm_response,
            "final_outcome": "Clarification requested",
            "messages": messages + new_messages
        }
        
    except Exception as e:
        logger.error(f"Error in handle_other_intent: {e}", exc_info=True)
        fallback_response = "I'm having trouble understanding. Could you please rephrase your request?"
        new_messages = [
            create_message(
                user_id=user_id,
                content=state['user_input'], 
                role="user",
                processing_status=ProcessingStatus.COMPLETED
            ),
            create_message(
                user_id=user_id,
                content=fallback_response,
                role="assistant",
                context={"error": str(e)},
                processing_status=ProcessingStatus.FAILED
            )
        ]
        # Try to save error messages atomically
        await save_messages_atomically(user_id, new_messages)
        
        # Update state status tracking
        state['processing_status'] = ProcessingStatus.FAILED
        state['error_details'] = str(e)
        state['completed_at'] = datetime.utcnow()
        
        return {
            **state,
            "llm_response": fallback_response,
            "final_outcome": f"Error in other intent handler: {str(e)}",
            "messages": messages + new_messages
        }

async def call_tweak_agent(state: AgentState) -> Dict[str, Any]:
    """
    LangGraph node to call the core process_user_instruction function.
    Handles outcomes and exceptions. Returns routing key for transitions.
    """
    logger.info(f"--- Executing Tweak Config Node for user: {state['user_id']} ---")
    user_id = state['user_id']
    user_input = state['user_input']

    outcome_key = "tweak_failure"
    final_outcome = "Configuration update failed."

    try:
        success = await process_user_instruction(user_id, user_input)
        if success is True:
            logger.info("Tweak agent reported success.")
            outcome_key = "tweak_success"
            final_outcome = "Configuration updated successfully."
        elif success is False:
            logger.error("Tweak agent reported operational failure.")
            outcome_key = "tweak_failure"
            final_outcome = "Failed to update configuration."
        elif success is None:
            logger.error("Tweak agent reported critical error.")
            outcome_key = "tweak_critical_failure"
            final_outcome = "An internal error occurred during configuration update."
    except Exception as e:
        logger.error(f"Unhandled exception in tweak agent node for user {user_id}: {e}", exc_info=True)
        outcome_key = "tweak_exception"
        final_outcome = f"An unexpected system error occurred during configuration update."

    logger.info(f"Tweak Config Node returning outcome: '{outcome_key}' and final outcome: '{final_outcome}'")
    return {
        "next": outcome_key,
        "llm_response": final_outcome,
        "final_outcome": outcome_key
         
    }

async def call_scheduling_logic(state: AgentState)-> Dict[str, Any] :
    """
    LangGraph node to call the core scheduling logic function.
    Handles validation, database errors, and routing logic with defensive programming.
    """
    logger.info(f"--- Executing Scheduling Logic Node for user: {state['user_id']} ---")
    messages = state.get('messages', [])
    context_window = state.get('context_window', GENERAL_QUERY_CONTEXT)
    message_history = format_message_history(messages, context_window)
    user_id = state['user_id']
    user_input = state['user_input']

    try:
        outcome_dict = await schedule_reminder_task(user_id, user_input)
        
        # Defensive validation: Ensure 'next' key exists and is valid
        if not outcome_dict or not isinstance(outcome_dict, dict):
            logger.error(f"Invalid outcome_dict returned from schedule_reminder_task: {outcome_dict}")
            return {
                "next": "schedule_exception",
                "final_outcome": "Internal scheduling error - invalid response format.",
                "llm_response": "An internal error occurred while processing your schedule request."
            }
        
        next_action = outcome_dict.get("next", "").strip()
        if not next_action:
            logger.error(f"Empty or missing 'next' key in scheduling outcome: {outcome_dict}")
            return {
                "next": "schedule_exception",
                "final_outcome": "Internal scheduling error - missing routing information.",
                "llm_response": "An internal error occurred while processing your schedule request."
            }
        
        # Validate that next_action is a known routing key
        valid_routes = {
            "schedule_success", "schedule_failure", "schedule_clarification", 
            "schedule_db_error", "schedule_exception"
        }
        if next_action not in valid_routes:
            logger.error(f"Invalid routing key from scheduling logic: '{next_action}'. Valid routes: {valid_routes}")
            return {
                "next": "schedule_exception",
                "final_outcome": f"Internal scheduling error - invalid routing key: {next_action}",
                "llm_response": "An internal error occurred while processing your schedule request."
            }
        
        logger.info(f"Scheduling logic returned valid outcome: {next_action}")
        # ─── INLINE LLM REWRITE ──────────────────────────────────────────────────────
        static_reply = outcome_dict.get("final_logic", "")
        prompt = GENERAL_QUERY_PROMPT.format(
            user_id=user_id,
            config=state.get("current_config_prompt", ""),
            message_history=message_history,
            query=static_reply
        )
        llm_text, _ = await get_gemini_response_async(prompt)
        return {
            "next": next_action,
             "llm_response": llm_text or static_reply,
             "final_outcome": next_action
   }
    except DatabaseError as e:
        logger.error(f"Database error caught in scheduling node for user {user_id}: {e}")
        return {
            "next": "schedule_db_error",
            "final_outcome": "A database error prevented saving your schedule. Please try again.",
            "llm_response": "A database error prevented saving your schedule. Please try again."
        }
    except Exception as e:
        logger.error(f"Unhandled exception in scheduling node for user {user_id}: {e}", exc_info=True)
        return {
            "next": "schedule_exception",
            "final_outcome": "An unexpected error occurred while processing your schedule request.",
            "llm_response": "An unexpected error occurred while processing your schedule request."
        }




async def report_outcome_node(state: AgentState) -> Dict[str, Any]:
    """
    Final node in the graph that ensures the final_outcome is correctly formatted.
    This node acts as a state consolidation point before termination.
    """
    logger.info(f"--- Executing Report Outcome Node for user: {state['user_id']} ---")
    
    final_outcome = state.get('final_outcome', "Operation completed.")
    llm_response = state.get('llm_response', final_outcome)
    
    logger.info(f"Final outcome: {final_outcome}")
    logger.info(f"LLM response: {llm_response}")
    
    return {
        "final_outcome": final_outcome,
        "llm_response": llm_response
    }

# --- Graph Builder ---
def build_agent_graph():
    """
    Builds and returns the compiled LangGraph workflow for the agent.
    Architectural reconstruction with proper separation of concerns.
    """
    # Create a new graph
    workflow = StateGraph(AgentState)

    # Add nodes to the graph
    workflow.add_node("entry", entry_node)
    workflow.add_node("parse_intent", call_intent_parser)
    workflow.add_node("tweak_config", call_tweak_agent)
    workflow.add_node("schedule", call_scheduling_logic)
    workflow.add_node("handle_clarification_request", handle_other_intent)  # Add this handler
    workflow.add_node("self_description", handle_self_description)   # ← new
    workflow.add_node("general_query", handle_general_query)
    workflow.add_node("acknowledge", handle_acknowledge)
    workflow.add_node("other", handle_other_intent)
    workflow.add_node("report_outcome", report_outcome_node)

    # Connect entry to intent parsing
    workflow.set_entry_point("entry")
    workflow.add_edge("entry", "parse_intent")

    # Branch based on parsed intent with defensive routing
    def route_intent(state):
        parsed_intent = state.get("parsed_intent", "other")
        logger.info(f"Routing intent: '{parsed_intent}'")
        
        # Defensive validation
        valid_intents = {"config_update", "schedule_request", "self_description", "general_query", "acknowledge", "other"}
        if parsed_intent not in valid_intents:
            logger.warning(f"Unknown intent '{parsed_intent}', defaulting to 'other'")
            return "other"
        return parsed_intent

    workflow.add_conditional_edges(
        "parse_intent",
        route_intent,
        {
            "config_update": "tweak_config",
            "schedule_request": "schedule",
             "clarification_request": "handle_clarification_request",
            "general_query": "general_query",
            "acknowledge": "acknowledge",
            "self_description": "self_description",
            "other": "other"
        }
    )

    # Connect simple handlers directly to report_outcome
    workflow.add_edge("general_query", "report_outcome")
    workflow.add_edge("acknowledge", "report_outcome")
    workflow.add_edge("handle_clarification_request", "report_outcome")
    workflow.add_edge("self_description", "report_outcome")  # ← new
    workflow.add_edge("other", "report_outcome")

    # Connect tweak_config outcomes with defensive routing
    def route_tweak_outcome(state):
        next_action = state.get("next", "tweak_exception")
        logger.info(f"Routing tweak outcome: '{next_action}'")
        
        valid_outcomes = {"tweak_success", "tweak_failure", "tweak_critical_failure", "tweak_exception"}
        if next_action not in valid_outcomes:
            logger.warning(f"Invalid tweak outcome '{next_action}', defaulting to 'tweak_exception'")
            return "tweak_exception"
        return next_action

    workflow.add_conditional_edges(
        "tweak_config",
        route_tweak_outcome,
        {
            "tweak_success": "report_outcome",
            "tweak_failure": "report_outcome",
            "tweak_critical_failure": "report_outcome",
            "tweak_exception": "report_outcome"
        }
    )

    # Connect schedule outcomes with defensive routing
    def route_schedule_outcome(state):
        next_action = state.get("next", "schedule_exception")
        logger.info(f"Routing schedule outcome: '{next_action}'")
        
        valid_outcomes = {
            "schedule_success", "schedule_failure", "schedule_clarification", 
            "schedule_db_error", "schedule_exception"
        }
        if next_action not in valid_outcomes:
            logger.warning(f"Invalid schedule outcome '{next_action}', defaulting to 'schedule_exception'")
            return "schedule_exception"
        return next_action

    workflow.add_conditional_edges(
        "schedule",
        route_schedule_outcome,
        {
            "schedule_success": "report_outcome",
            "schedule_failure": "report_outcome",
            "schedule_clarification": "report_outcome",
            "schedule_db_error": "report_outcome",
            "schedule_exception": "report_outcome"
        }
    )

    # Mark report_outcome as the end of all paths
    workflow.add_edge("report_outcome", END)

    # Compile the graph into a runnable workflow
    compiled_workflow = workflow.compile()
    logger.info("✅ LangGraph workflow compiled successfully with defensive routing.")
    return compiled_workflow

# --- Diagnostic and Testing Functions ---
def validate_graph_architecture():
    """
    Diagnostic function to validate the graph architecture for common failure modes.
    """
    logger.info("🔍 Validating LangGraph architecture...")
    
    # Test graph compilation
    try:
        graph = build_agent_graph()
        logger.info("✅ Graph compilation successful")
    except Exception as e:
        logger.error(f"❌ Graph compilation failed: {e}")
        return False
    
    # Validate node connectivity
    expected_nodes = {
        "entry", "parse_intent", "tweak_config", "schedule", 
        "general_query", "acknowledge", "other", "report_outcome"
    }
    
    logger.info(f"Expected nodes: {expected_nodes}")
    logger.info("✅ Architecture validation complete")
    return True

if __name__ == "__main__":
    print("--- LangGraph Reconstructed Architecture Test ---")
    validate_graph_architecture()
    logger.info("Recommend testing via `uvicorn main:app --reload`.")