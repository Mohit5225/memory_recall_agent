# src/agent/graph.py
from langgraph.graph import StateGraph, END
# Corrected relative import for AgentState
from .state import AgentState
# Import the core tweak agent logic
from core.tweak_agent import process_user_instruction

import logging
logger = logging.getLogger(__name__)

# --- Node Definitions ---

def entry_node(state: AgentState) -> AgentState:
    """Initial entry point of the graph. Logs entry."""
    logger.info(f"--- Entering graph for user: {state['user_id']} ---")
    return {} # No state update needed here, just proceed

# Node to Call the Core Tweak Agent Logic (Revised)
def call_tweak_agent(state: AgentState) -> AgentState:
    """
    LangGraph node to call the core process_user_instruction function.
    Handles True/False/None outcomes and exceptions. Returns outcome for transition.
    """
    logger.info(f"--- Executing Tweak Config Node for user: {state['user_id']} ---")

    user_id = state['user_id']
    user_input = state['user_input']

    outcome_key = "end_failure"  # Default outcome is failure
    final_outcome = "config_update_failed"  # Default final outcome

    try:
        # Call the core logic function
        success = process_user_instruction(user_id, user_input)

        # Determine outcomes based on the return value
        if success is True:
            logger.info("Tweak agent reported success.")
            outcome_key = "end_success"
            final_outcome = "config_updated_successfully"
        elif success is False:
            logger.error("Tweak agent reported operational failure.")
            outcome_key = "end_failure"
            final_outcome = "config_update_failed"
        elif success is None:
            logger.error("Tweak agent reported critical error.")
            outcome_key = "end_critical_failure"
            final_outcome = "critical_system_error"

    except Exception as e:
        logger.error(f"Unhandled exception in tweak agent node: {e}", exc_info=True)
        outcome_key = "end_exception"
        final_outcome = f"system_error: {str(e)}"

    logger.info(f"Tweak Config Node returning outcome: '{outcome_key}'")
    # Return both the next step and the final outcome
    return {
        "next": outcome_key,
        "final_outcome": final_outcome
    }

# --- Final Outcome Node ---
def report_outcome_node(state: AgentState) -> AgentState:
    """
    Final node that ensures the outcome is properly captured in the state.
    This node runs just before END to structure the final result.
    """
    logger.info(f"Finalizing outcome for user: {state['user_id']}")
    # The final_outcome should already be set by call_tweak_agent
    final_outcome = state.get('final_outcome', 'unknown_outcome')
    logger.info(f"Final outcome: {final_outcome}")
    return {"final_outcome": final_outcome}

# --- Graph Builder ---
def build_agent_graph():
    """
    Builds and compiles the LangGraph agent workflow graph.
    Includes entry, tweak_config, and report_outcome nodes.
    """
    # Define the graph with AgentState
    workflow = StateGraph(AgentState)

    # Add nodes to the graph
    workflow.add_node("entry", entry_node)
    workflow.add_node("tweak_config", call_tweak_agent)
    workflow.add_node("report_outcome", report_outcome_node)

    # Set entry point
    workflow.set_entry_point("entry")

    # Define edges
    workflow.add_edge("entry", "tweak_config")

    # Add conditional edges from tweak_config to report_outcome
    workflow.add_conditional_edges(
        "tweak_config",
        lambda state: state.get('next', 'end_failure'),
        {
            "end_success": "report_outcome",
            "end_failure": "report_outcome",
            "end_critical_failure": "report_outcome",
            "end_exception": "report_outcome"
        }
    )

    # Final edge from report_outcome to END
    workflow.add_edge("report_outcome", END)

    # Compile the graph
    graph = workflow.compile()
    logger.info("✅ LangGraph compiled successfully.")

    return graph

# Example usage (for testing this file if needed)
if __name__ == "__main__":
    print("--- LangGraph graph definition test ---")
    # This block won't run when imported by main.py
    # Building the graph itself should not require DB/LLM env vars,
    # but running graph.invoke would.
    try:
        graph = build_agent_graph()
        print("Graph built successfully.")
    except Exception as e:
        print(f"Error building graph: {e}")