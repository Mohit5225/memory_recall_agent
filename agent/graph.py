# src/agent/graph.py
from langgraph.graph import StateGraph, END
from .state import AgentState
from  core.tweak_agent import process_user_instruction
# Import the new intent parsing logic
from core.intent_parser import parse_user_intent

import logging
logger = logging.getLogger(__name__)

# --- Node Definitions ---

def entry_node(state: AgentState) -> AgentState:
    """Initial entry point of the graph. Logs entry."""
    logger.info(f"--- Entering graph for user: {state['user_id']} ---")
    return {} # No state update needed here, just proceed


# --- Node to Call the Intent Parsing Logic ---
# This new node uses the LLM to classify the user's input.
def call_intent_parser(state: AgentState) -> AgentState:
    """
    LangGraph node to call the core parse_user_intent function.
    Reads user_input from state, calls parser, updates state with parsed_intent.
    """
    logger.info(f"--- Executing Intent Parsing Node for user: {state['user_id']} ---")
    user_input = state['user_input']

    # Call the core intent parsing logic
    parsed_intent = parse_user_intent(user_input)

    logger.info(f"Intent Parsing Node identified intent: '{parsed_intent}'")
    # Return the parsed intent within a dictionary to update the state
    return {"parsed_intent": parsed_intent}


# Node to Call the Core Tweak Agent Logic (Revised - No Change Needed Here Internally)
def call_tweak_agent(state: AgentState) -> AgentState:
    """
    LangGraph node to call the core process_user_instruction function.
    Handles True/False/None outcomes and exceptions. Returns outcome for transition.
    """
    logger.info(f"--- Executing Tweak Config Node for user: {state['user_id']} ---")

    user_id = state['user_id']
    user_input = state['user_input']

    outcome_key = "end_failure"
    final_outcome = "config_update_failed"

    try:
        success = process_user_instruction(user_id, user_input)

        if success is True:
            logger.info("Tweak agent reported success.")
            outcome_key = "end_success"
            final_outcome = "config_updated_successfully"
        elif success is False:
            logger.error("Tweak agent reported operational failure (returned False).")
            outcome_key = "end_failure"
            final_outcome = "config_update_failed"
        elif success is None:
             logger.error("Tweak agent reported critical error (returned None).")
             outcome_key = "end_critical_failure"
             final_outcome = "critical_system_error"

    except Exception as e:
        logger.error(f"Unhandled exception in tweak agent node for user {user_id}: {e}", exc_info=True)
        outcome_key = "end_exception"
        final_outcome = f"system_error: {str(e)}"

    logger.info(f"Tweak Config Node returning outcome: '{outcome_key}' and final outcome: '{final_outcome}'")
    # Return both the next step (for routing) and the final outcome (for reporting)
    return {
        "next": outcome_key, # This is used by the conditional edge FROM tweak_config (still routes to report_outcome)
        "final_outcome": final_outcome # This is read by report_outcome_node and main.py
    }


# Final Outcome Node (Revised - Now just reports the outcome already set)
def report_outcome_node(state: AgentState) -> AgentState:
    """
    Node to structure the final outcome before ending the graph.
    Reads the 'final_outcome' key from the state.
    """
    logger.info(f"--- Executing Report Outcome Node for user: {state['user_id']} ---")
    logger.debug(f"Report Outcome Node received state: {state}")

    # Read the final outcome key, which was already set by call_tweak_agent
    final_outcome = state.get("final_outcome", "processing_unknown")

    logger.info(f"Final outcome: '{final_outcome}'")
    # Return the final_outcome (it's already in state, this just ensures it persists if needed)
    # Returning the value itself is fine, or return {} if no further state change needed
    # For clarity, let's return an empty dict, assuming final_outcome is set earlier.
    # The state *already* has final_outcome from call_tweak_agent's return.
    return {}


# --- Graph Builder ---
def build_agent_graph():
    """
    Builds and compiles the LangGraph agent workflow graph.
    Includes entry, intent_parser, tweak_config, and report_outcome nodes.
    Defines conditional edges based on parsed_intent.
    """
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("entry", entry_node)
    workflow.add_node("parse_intent", call_intent_parser) # Add the new intent parsing node
    workflow.add_node("tweak_config", call_tweak_agent)
    workflow.add_node("report_outcome", report_outcome_node)

    # Define entry point
    workflow.set_entry_point("entry")

    # --- Define Edges ---

    # entry -> parse_intent (Unconditional)
    # After entering, the first step is always to parse the intent.
    workflow.add_edge("entry", "parse_intent")

    # Conditional edges from parse_intent
    # The graph routes based on the value of the 'parsed_intent' key in the state
    workflow.add_conditional_edges(
        "parse_intent", # Node whose state updates determine next step
        lambda state: state.get('parsed_intent', 'other'), # Read the 'parsed_intent' key from state. Default to 'other'.
        { # Mapping of parsed_intent value to the next node
            "config_update": "tweak_config", # If intent is config_update, go to tweak node
            # Add placeholders for other intents (will route to report_outcome for now)
            "schedule_request": "report_outcome", # Future: go to schedule node
            "general_query": "report_outcome",    # Future: go to generate/answer node
            "acknowledge": "report_outcome",     # Future: go to a simple ack node
            "other": "report_outcome",            # Unhandled intents go to report node
        }
    )

    # Conditional edges from tweak_config (based on 'next' key set by call_tweak_agent)
    # All outcomes from tweak_config now route to the report_outcome node
    workflow.add_conditional_edges(
        "tweak_config",
        lambda state: state.get('next', 'end_failure'), # Read the 'next' key from state
        { # Mapping of 'next' value to next node
            "end_success": "report_outcome",
            "end_failure": "report_outcome",
            "end_critical_failure": "report_outcome",
            "end_exception": "report_outcome"
        }
    )

    # Edge from report_outcome_node to END
    # After reporting the outcome, the graph ends.
    workflow.add_edge("report_outcome", END)


    # Compile the graph
    graph = workflow.compile()
    logger.info("✅ LangGraph compiled successfully with intent parsing.")

    return graph

# Example usage (for testing this file if needed)
if __name__ == "__main__":
    print("--- LangGraph graph definition test ---")
    # Ensure logging level is set to DEBUG here if running directly
    # logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
    logger.warning("Direct graph invocation requires careful setup of DB client and async context.")
    logger.info("Recommend testing via `uvicorn main:app --reload`.")