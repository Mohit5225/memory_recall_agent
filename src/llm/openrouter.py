import httpx
import logging
import json
from typing import Optional, Tuple, Dict, Any
import httpx, logging, json, asyncio
from typing import Optional, Tuple, Dict, Any, List
from src.config.settings import (
OPENROUTER_SECRET_KEY,
OPENROUTER_FALLBACK_MODELS,
OPENROUTER_SELF_DESCRIPTION_MAX_RETRIES
, model_sequence )

ERROR_TYPE_MAP = {
    400: "bad_request",
    401: "auth_error",
    403: "forbidden",
    404: "not_found",
    408: "timeout",
    409: "conflict",
    422: "validation_error",
    429: "rate_limited",
    500: "server_error",
    502: "bad_gateway",
    503: "service_unavailable",
    504: "gateway_timeout"
}
def _classify_http_error(status_code: int) -> str:
    return ERROR_TYPE_MAP.get(status_code, "http_error")

# Set up logging
logger = logging.getLogger(__name__)

# --- Constants ---
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

async def get_openrouter_chain_response_async(
    system_prompt: str,
    user_prompt: str,
    message_history: Optional[str],
    model_sequence: Optional[List[str]] = None,
    max_retries_per_model: Optional[int] = None,
    timeout_seconds: float = 60.0
) -> Tuple[Optional[str], Dict[str, Any]]:
    """
    Multi-model, per-model retry chain with structured logging + attempt ledger.
    Returns first successful response or None + rich context if all fail.
    """
    if not OPENROUTER_SECRET_KEY:
        msg = "OPENROUTER_SECRET_KEY missing"
        logging.error(msg)
        return None, {
            "llm_provider": "openrouter",
            "processing_status": "failed",
            "error_details": msg,
            "attempts": []
        }

    models = model_sequence or OPENROUTER_FALLBACK_MODELS
    retries = max_retries_per_model or OPENROUTER_SELF_DESCRIPTION_MAX_RETRIES

    attempts: List[Dict[str, Any]] = []
    headers = {
        "Authorization": f"Bearer {OPENROUTER_SECRET_KEY}",
        "Content-Type": "application/json"
    }

    # Construct contextual messages (system + optional history summary + user)
    history_block = ""
    if message_history:
        # Trim excessively long history to control token usage
        trimmed = message_history[-4000:]
        history_block = f"Conversation Snapshot (compressed):\n{trimmed}\n--- End Snapshot ---"

    base_messages = [
        {"role": "system", "content": system_prompt.strip()},
        *( [{"role": "system", "content": history_block}] if history_block else [] ),
        {"role": "user", "content": user_prompt.strip()}
    ]

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        for model in models:
            for attempt in range(1, retries + 1):
                payload = {
                    "model": model,
                    "messages": base_messages,
                    # "extra_body": {
                    #     "reasoning": False,
                    #     "thinking": False
                    # }

                }
                attempt_record: Dict[str, Any] = {
                    "model": model,
                    "attempt_number": attempt,
                    "status": "started"
                }
                logging.info(f"[SELF_DESC][MODEL={model}][ATTEMPT={attempt}] Dispatching request.")
                try:
                    response = await client.post(OPENROUTER_API_URL, headers=headers, json=payload)
                    status_code = response.status_code
                    if status_code >= 400:
                        error_type = _classify_http_error(status_code)
                        text_sample = (response.text or "")[:250]
                        logging.warning(
                            f"[SELF_DESC][MODEL={model}][ATTEMPT={attempt}] HTTP {status_code} "
                            f"type={error_type} body_sample={text_sample}"
                        )
                        attempt_record.update({
                            "status": "http_error",
                            "http_status": status_code,
                            "error_type": error_type,
                            "body_sample": text_sample
                        })
                        attempts.append(attempt_record)
                        # Retry only on transient codes
                        if status_code in (408, 429, 500, 502, 503, 504):
                            await asyncio.sleep(min(2 ** (attempt - 1), 6))
                            continue
                        else:
                            break  # Move to next model (non-retriable)
                    data = response.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content")
                    if content:
                        logging.info(f"[SELF_DESC][MODEL={model}][ATTEMPT={attempt}] SUCCESS.")
                        attempt_record.update({
                            "status": "success",
                            "usage": data.get("usage", {}),
                            "finish_reason": data.get("choices", [{}])[0].get("finish_reason")
                        })
                        attempts.append(attempt_record)
                        return content.strip(), {
                            "llm_provider": "openrouter",
                            "model_name": model,
                            "processing_status": "completed",
                            "attempts": attempts
                        }
                    else:
                        logging.error(f"[SELF_DESC][MODEL={model}][ATTEMPT={attempt}] Empty content.")
                        attempt_record.update({
                            "status": "empty_content",
                            "error_type": "empty_response"
                        })
                        attempts.append(attempt_record)
                        # Retry (empty content treated as transient)
                        await asyncio.sleep(min(2 ** (attempt - 1), 6))
                except httpx.RequestError as e:
                    logging.error(
                        f"[SELF_DESC][MODEL={model}][ATTEMPT={attempt}] Network error: {e}"
                    )
                    attempt_record.update({
                        "status": "network_error",
                        "error_type": "network",
                        "error_details": str(e)
                    })
                    attempts.append(attempt_record)
                    await asyncio.sleep(min(2 ** (attempt - 1), 6))
                    continue
                except Exception as e:
                    logging.exception(
                        f"[SELF_DESC][MODEL={model}][ATTEMPT={attempt}] Unexpected failure."
                    )
                    attempt_record.update({
                        "status": "unexpected_error",
                        "error_type": "unexpected",
                        "error_details": str(e)
                    })
                    attempts.append(attempt_record)
                    # Retry once for unexpected, then move to next model
                    if attempt < retries:
                        await asyncio.sleep(min(2 ** (attempt - 1), 6))
                        continue
                    break  # move to next model

    logging.error("[SELF_DESC] All models exhausted. Returning failure context.")
    return None, {
        "llm_provider": "openrouter",
        "processing_status": "failed",
        "attempts": attempts,
        "error_details": "All fallback models exhausted for self-description."
    }