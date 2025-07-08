import logging
import secrets , string
import redis



import phonenumbers
from redis.asyncio import Redis
from src.config.settings import REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, REDIS_DB_OTP
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, cast
import secrets
from datetime import datetime, timezone
from typing import Dict, Any, Optional, cast
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuthError
import json
from src.auth.jwt_utils import get_current_user_from_token
from src.db.mongo import get_user_collection
from fastapi import APIRouter, HTTPException, Request, status, Body
from .oauth import google_oauth
from .jwt_utils import (
    create_jwt_token, decode_jwt_token, create_mock_jwt_token, 
    JWT_EXPIRATION_DAYS, revoke_token_from_request, revoke_all_user_tokens_safe
)
from .user_service import get_or_create_user
from .token_blacklist import token_blacklist, RedisConnectionError
from .security_utils import (
    validate_email_security, check_rate_limit, get_client_ip,
    log_security_event, enhance_user_data_security, SecurityValidationError
)
from .security_utils import (
    validate_email_security, check_rate_limit, get_client_ip,
    log_security_event, enhance_user_data_security, SecurityValidationError
)
from twilio.rest import Client
from src.config.settings import (
        REDIS_HOST, REDIS_PORT, REDIS_PASSWORD,
        TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN , TWILIO_WHATSAPP_NUMBER
    )

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/auth", tags=["authentication"])

from upstash_redis import Redis as UpstashRedis
from src.config.settings import OTP_REDIS_URL, OTP_REDIS_TOKEN

if OTP_REDIS_URL is None or OTP_REDIS_TOKEN is None:
    raise RuntimeError("OTP_REDIS_URL and OTP_REDIS_TOKEN must be set in the environment/config.")

otp_redis = UpstashRedis(url=OTP_REDIS_URL, token=OTP_REDIS_TOKEN)

 

@router.post("/whatsapp", status_code=200)
async def set_whatsapp_number(
    request: Request,
    whatsapp_number: str = Body(..., embed=True)
):
    """
    Set or update the WhatsApp number for the authenticated user.
    Only allows the logged-in user to update their own number.
    """
    # 1. Extract user from JWT (cookie)
    whatsapp_number = whatsapp_number.strip()
    try:
        parsed = phonenumbers.parse(whatsapp_number, None)
        if not phonenumbers.is_valid_number(parsed):
            raise ValueError("Invalid phone number")
    except phonenumbers.NumberParseException:
        raise HTTPException(status_code=400, detail="Invalid WhatsApp number format")

    user = await get_current_user_from_token(request)
    if not user or not user.get("user_id"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    user_id = user["user_id"]

    # 2. Validate WhatsApp number (basic check: starts with + and digits, min length)
    if not isinstance(whatsapp_number, str) or not whatsapp_number.startswith("+") or len(whatsapp_number) < 10:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid WhatsApp number format")

    # 3. Update in MongoDB (atomic $set)
    collection = await get_user_collection()
    result = await collection.update_one(
        {"user_id": user_id},
        {"$set": {"whatsapp_number": whatsapp_number, "whatsapp_verified": False}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="User not found or number unchanged")
    elif result.matched_count == 0:
        return {"success" : True , "message": "WhatsApp number already set to this value."}
    # 1. Generate secure 6-digit OTP
    otp = ''.join(secrets.choice(string.digits) for _ in range(6))

    # 2. Store OTP in Redis with 5 min TTL
     
    redis_key = f"otp:{user_id}"
    await asyncio.to_thread(otp_redis.set, redis_key, otp, ex=300) # 5 min TTL

    # 3. (Optional) Rate limit key for resend (1 per 60s)
    rate_key = f"otp_rate:{user_id}"
    if await asyncio.to_thread(otp_redis.exists, rate_key):
        raise HTTPException(status_code=429, detail="OTP recently sent. Please wait before resending.")
    await asyncio.to_thread(otp_redis.set, rate_key, 1, ex=60)

    # 4. Send OTP via Twilio WhatsApp
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            body=f"Your verification code is: {otp}",
            from_=TWILIO_WHATSAPP_NUMBER,
            to=f"whatsapp:{whatsapp_number}"
        )
        # 5. Log masked send event (never log full OTP)
        logging.info(f"OTP sent to user_id={user_id}, phone=****{whatsapp_number[-4:]}, msg_sid={message.sid}")
    except Exception as e:
        logging.error(f"Failed to send OTP via Twilio: {e}")
        raise HTTPException(status_code=500, detail="Failed to send OTP. Try again later.")

    return {"success": True, "message": "WhatsApp number updated. OTP sent for verification."}



import asyncio  # Needed for to_thread wrapping
@router.post("/verify-phone", status_code=200)
async def verify_phone(request: Request, otp: str = Body(..., embed=True)):
    """
    Verify the OTP sent to the user's WhatsApp number.
    Adds brute force protection: max 5 attempts in 5 minutes.
    """
    # 1. Authenticate user via JWT
    user = await get_current_user_from_token(request)
    if not user or not user.get("user_id"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    user_id = user["user_id"]

    redis_key = f"otp:{user_id}"
    attempt_key = f"otp_attempts:{user_id}"

    # 2. Brute force protection: check and increment attempts
    attempts = await asyncio.to_thread(otp_redis.get, attempt_key)
    attempts = int(attempts) if attempts else 0
    if attempts >= 5:
        logger.warning(f"User {user_id} locked out of OTP verification (too many attempts)")
        raise HTTPException(status_code=429, detail="Too many incorrect OTP attempts. Try again in 5 minutes.")

    # 3. Fetch OTP from Redis
    stored_otp = await asyncio.to_thread(otp_redis.get, redis_key)
    if not stored_otp:
        logger.info(f"OTP expired or not found for user {user_id}")
        raise HTTPException(status_code=400, detail="OTP expired or not found. Please request a new one.")

    # 4. Compare OTPs
    if otp != stored_otp:
        # Increment brute force attempts and set TTL to 5 min
        await asyncio.to_thread(otp_redis.incr, attempt_key)
        await asyncio.to_thread(otp_redis.expire, attempt_key, 300)
        logger.info(f"User {user_id} failed OTP verification attempt {attempts + 1}")
        raise HTTPException(status_code=400, detail="Invalid OTP. Please try again.")

    # 5. Success: update MongoDB, cleanup Redis
    collection = await get_user_collection()
    await collection.update_one(
        {"user_id": user_id},
        {"$set": {"whatsapp_verified": True}}
    )
    await asyncio.to_thread(otp_redis.delete, redis_key)
    await asyncio.to_thread(otp_redis.delete, attempt_key)
    logger.info(f"User {user_id} verified successfully via WhatsApp OTP.")

    # return {"success": True, "message": "Phone number verified successfully."}


@router.post("/send-otp", status_code=200)
async def resend_otp(request: Request):
    """
    Manually resend OTP to the user's WhatsApp number.
    Rate-limited to 1 per 60 seconds.
    """
    import secrets, string
    import redis

    # 1. Authenticate user
    user = await get_current_user_from_token(request)
    if not user or not user.get("user_id"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    user_id = user["user_id"]

    # 2. Fetch WhatsApp number from DB
    collection = await get_user_collection()
    user_doc = await collection.find_one({"user_id": user_id})
    whatsapp_number = user_doc.get("whatsapp_number") if user_doc else None
    if not whatsapp_number:
        raise HTTPException(status_code=400, detail="No WhatsApp number found for user.")

    # 3. Rate limit: block if sent in last 60s
    rate_key = f"otp_rate:{user_id}"
    if await asyncio.to_thread(otp_redis.exists, rate_key):
        raise HTTPException(status_code=429, detail="OTP recently sent. Please wait before resending.")
    await asyncio.to_thread(otp_redis.set, rate_key, 1, ex=60)

    # 4. Generate secure 6-digit OTP
    otp = ''.join(secrets.choice(string.digits) for _ in range(6))

    # 5. Store OTP in Redis with 5 min TTL
    redis_key = f"otp:{user_id}"
    await asyncio.to_thread(otp_redis.set, redis_key, otp, ex=300)  # 5 min TTL


    # 6. Send OTP via Twilio WhatsApp
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            body=f"Your verification code is: {otp}",
            from_=TWILIO_WHATSAPP_NUMBER,
            to=f"whatsapp:{whatsapp_number}"
        )
        logging.info(f"OTP resent to user_id={user_id}, phone=****{whatsapp_number[-4:]}, msg_sid={message.sid}")
    except Exception as e:
        logging.error(f"Failed to resend OTP via Twilio: {e}")
        raise HTTPException(status_code=500, detail="Failed to resend OTP. Try again later.")

    return {"success": True, "message": "OTP resent to your WhatsApp number."}


OAUTH_STATE_PREFIX = "oauth_state:"
OAUTH_STATE_EXPIRY_SECONDS = 300  # 5 minutes

@router.get("/google")
async def google_login(request: Request):
    """
    Initiates Google OAuth login using an explicit, Redis-backed state token.
    This bypasses the faulty SessionMiddleware cookie mechanism.
    """
    client_ip = get_client_ip(request)
    if not check_rate_limit(client_ip):
        log_security_event("OAUTH_RATE_LIMIT", {"ip": client_ip}, "WARNING")
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Please try again later."
        )

    # 1. Generate a cryptographically secure state token.
    #    `secrets.token_urlsafe(32)` creates a random, URL-friendly string.
    #    This is our CSRF protection token.
    state = secrets.token_urlsafe(32)
    redis_key = f"{OAUTH_STATE_PREFIX}{state}"

    try:
        # 2. Store the state token in Redis with a 5-minute expiry.
        #    `setex` is an atomic "set with expiry" command.
        #    We store the value '1' just as a placeholder; the existence of the key is what matters.
        await asyncio.to_thread(otp_redis.setex, redis_key, OAUTH_STATE_EXPIRY_SECONDS, 1)
        logger.info(f"Stored OAuth state in Redis with key: {redis_key}")
    except Exception as e:
        logger.error(f"Failed to store OAuth state in Redis: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error: Could not prepare login.")

    # 3. Create the authorization URL, passing our explicit state.
    redirect_uri = str(request.url_for('google_callback'))
    google_client = cast(Any, google_oauth.google)
    
    # Authlib's `create_authorization_url` will now use the `state` we provide
    # instead of trying to generate and save one to the broken session.
    authorization_url_dict = await google_client.create_authorization_url(
        redirect_uri,
        access_type='offline',
        prompt='consent',
        include_granted_scopes='true',
        state=state  # Explicitly providing our state token.
    )
    
    log_security_event(
        "OAUTH_INITIATION", 
        {"ip": client_ip, "provider": "google"}
    )
    
    url = authorization_url_dict['url']
    return RedirectResponse(url)

import os

FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "http://localhost:3000")

@router.get("/google/callback")
async def google_callback(request: Request, response: Response):
    """
    Handles Google OAuth callback, validating the state against Redis.
    """
    logger.debug("\n=== OAuth Callback (Redis State) Debug ===")
    logger.debug(f"Full Callback URL: {request.url}")
    logger.debug(f"Callback Query Params: {dict(request.query_params)}")
    
    client_ip = get_client_ip(request)
    
    # 1. Get the state returned by Google from the query parameters.
    returned_state = request.query_params.get('state')
    if not returned_state:
        log_security_event("OAUTH_ERROR", {"ip": client_ip, "error": "state_missing"}, "CRITICAL")
        raise HTTPException(status_code=400, detail="OAuth callback is missing state parameter.")

    redis_key = f"{OAUTH_STATE_PREFIX}{returned_state}"

    try:
        # 2. Atomically check for and delete the state from Redis.
        #    `getdel` gets the value and deletes the key in one atomic operation.
        #    This prevents the same state token from being used twice (replay attack).
        stored_state = await asyncio.to_thread(otp_redis.getdel, redis_key)

        if stored_state is None:
            # If the key does not exist, it's either expired or invalid.
            log_security_event("OAUTH_ERROR", {"ip": client_ip, "error": "state_mismatch_or_expired"}, "CRITICAL")
            raise HTTPException(status_code=400, detail="Invalid or expired OAuth state. Please try logging in again.")
        
        logger.info(f"Successfully validated and consumed OAuth state from Redis: {redis_key}")

    except Exception as e:
        logger.error(f"Failed to validate OAuth state from Redis: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error: Could not validate login.")

    # --- State is now validated. Proceed with fetching the token. ---
    try:
        google_client = cast(Any, google_oauth.google)
        
        # ==================================================================
        # THE FIX: Replace the single line below.
        # ==================================================================
        code = request.query_params.get('code')
        if not code:
            raise HTTPException(status_code=400, detail="Authorization code missing from callback.")

        

        token = await google_client.fetch_access_token(
            code=code,
            redirect_uri=str(request.url_for('google_callback'))
        )
        
        userinfo = await google_client.userinfo(token=token)
        if not userinfo:
            raise HTTPException(status_code=400, detail="Could not fetch user info from Google.")

        validate_email_security(userinfo.get('email'), userinfo)
        
        user = await get_or_create_user(
            google_sub=userinfo.get('sub'),
            email=userinfo.get('email'),
            name=userinfo.get('name')
        )

        if not user:
            raise HTTPException(status_code=500, detail="Could not create or retrieve user.")

        enhanced_user = enhance_user_data_security(user)
        jwt_token = create_jwt_token(
            google_sub=enhanced_user['user_id'],
            email=enhanced_user['email'],
            user_id=str(enhanced_user['_id']),
            roles=enhanced_user['roles']
        )
        response = RedirectResponse(url=f"{FRONTEND_BASE_URL}/whatsapp")
        response.set_cookie(
            key="access_token",
            value=jwt_token,
            httponly=True,
            secure=False, # Set True in production
            samesite="lax",
            max_age=int(timedelta(days=JWT_EXPIRATION_DAYS).total_seconds())
        )
        
        log_security_event("OAUTH_SUCCESS", {"ip": client_ip, "user_id": user['user_id']})

        return response

    except SecurityValidationError as e:
        log_security_event("OAUTH_SECURITY_FAIL", {"ip": client_ip, "error": str(e)}, "CRITICAL")
        raise HTTPException(status_code=403, detail=str(e))
    except OAuthError as e:
        log_security_event("OAUTH_ERROR", {"ip": client_ip, "error": e.error}, "CRITICAL")
        logger.error(f"OAuth error: {e.error}")
        raise HTTPException(status_code=400, detail=f"OAuth error: {e.error}")
    except Exception as e:
        logger.error(f"Unexpected error during Google OAuth callback: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.post("/logout")
async def logout(request: Request):
    """Logout user by revoking token and clearing cookie"""
    try:
        # Revoke the token server-side
        revoked = await revoke_token_from_request(request)
        
        # Clear cookie regardless of revocation success
        response = Response(
            content='{"message": "Logged out successfully"}', 
            media_type="application/json"
        )
        response.delete_cookie("access_token")
        
        if revoked:
            logger.info("Token successfully revoked and cookie cleared")
        else:
            logger.warning("Failed to revoke token, but cookie cleared")
        
        return response
        
    except Exception as e:
        logger.error(f"Logout error: {e}")
        # Still clear cookie even if revocation fails
        response = Response(
            content='{"message": "Logged out (with errors)"}', 
            media_type="application/json"
        )
        response.delete_cookie("access_token")
        return response

@router.get("/mock-login")
async def mock_login(user: str, response: Response):
    """Mock login for development (creates fake JWT + cookie)"""
    if not user:
        raise HTTPException(status_code=400, detail="User parameter required")
    
    # Create mock JWT token
    jwt_token = create_mock_jwt_token(user)
    
    # Set cookie
    response.set_cookie(
        key="access_token",
        value=jwt_token,
        httponly=True,
        secure=False,  # False for development
        samesite="lax",
        max_age=JWT_EXPIRATION_DAYS * 24 * 60 * 60
    )
    
    return {"message": f"Mock login successful for {user}", "token_set": True}

@router.post("/revoke-all-tokens")
async def revoke_all_user_tokens_endpoint(request: Request):
    """Emergency endpoint to revoke all tokens for current user with fail-safe handling"""
    token = request.cookies.get("access_token")
    
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        # Get user info from current token
        payload = await decode_jwt_token(token, check_blacklist=False)  # Skip blacklist check for this operation
        user_sub = payload['sub']
        
        # Attempt to revoke all tokens with safe error handling
        result = await revoke_all_user_tokens_safe(user_sub)
        
        # Clear current cookie regardless of revocation success
        response = Response(
            content=f'{{"success": {str(result["success"]).lower()}, "message": "{result["message"]}", "affected_tokens": {result["revoked_count"]}}}',
            media_type="application/json"
        )
        response.delete_cookie("access_token")
        
        if result["success"]:
            logger.info(f"All tokens successfully revoked for user {user_sub}")
        else:
            logger.warning(f"Token revocation failed for user {user_sub}: {result.get('error', 'Unknown error')}")
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to revoke all tokens: {e}")
        # Still clear cookie even if everything fails
        response = Response(
            content='{"success": false, "message": "Token revocation service error - please change password and re-login", "affected_tokens": 0}',
            media_type="application/json"
        )
        response.delete_cookie("access_token")
        return response

@router.get("/health")
async def auth_health_check():
    """Health check endpoint for authentication service"""
    try:
        # Check Redis connection
        redis_status = token_blacklist._check_redis_health()
        
        return {
            "status": "healthy" if redis_status else "degraded",
            "redis_available": redis_status,
            "fail_secure_mode": token_blacklist.fail_secure,
            "warning": None if redis_status else "Redis unavailable - "
            "authentication will fail in fail-secure mode"
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "redis_available": False,
            "fail_secure_mode": token_blacklist.fail_secure,
            "error": str(e)
        }
    
@router.get("/me", status_code=200)
async def get_current_user_profile(request: Request):
    """
    Returns the authenticated user's profile info for Redux hydration.
    - Reads JWT from cookie (via get_current_user_from_token)
    - Fetches user from MongoDB
    - Returns minimal, safe user info as JSON
    - 401 if not authenticated
    """
    # 1. Extract user from JWT in cookie
    user_jwt = await get_current_user_from_token(request)
    if not user_jwt or not user_jwt.get("user_id"):
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id = user_jwt["user_id"]

    # 2. Fetch user from MongoDB
    collection = await get_user_collection()
    user = await collection.find_one({"user_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 3. Build safe response (only expose minimal fields)
    return {
        "user_id": user.get("user_id"),
        "display_name": user.get("display_name"),
        "email": user.get("email"),
        "roles": user.get("roles", []),
        "whatsapp_number": user.get("whatsapp_number"),
        "whatsapp_verified": user.get("whatsapp_verified", False),
        "last_login": user.get("last_login"),
    }
