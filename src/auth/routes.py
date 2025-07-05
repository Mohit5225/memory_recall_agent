import logging
import secrets , string
import redis



import phonenumbers
from redis.asyncio import Redis
from src.config.settings import REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, REDIS_DB_OTP
from datetime import datetime, timezone
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

 

@router.post("/phone", status_code=200)
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

    return {"success": True, "message": "Phone number verified successfully."}


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


 
@router.get("/google")
async def google_login(request: Request):
    """Initiate Google OAuth login with enhanced security"""
    try:
        # Rate limiting check
        client_ip = get_client_ip(request)
        if not check_rate_limit(client_ip):
            log_security_event(
                "RATE_LIMIT_EXCEEDED", 
                {"ip": client_ip, "endpoint": "/auth/google"},
                "WARNING"
            )
            raise HTTPException(
                status_code=429, 
                detail="Too many login attempts. Please try again later."
            )
        
        # Generate and store CSRF state token
        state = secrets.token_urlsafe(32)
        request.session['_google_state'] = state
        logger.debug(f"Generated and saved state to session: {state}")
        # Add logging after state storage
        logger.debug(f"Generated OAuth State: {state}")
        logger.debug(f"Updated Session State: {request.session}")
        logger.debug(f"Session Keys Present: {request.session.keys()}")

        logger.debug(f"Stored OAuth state in session: {state}")
         # Verify session was updated
        logger.debug(f"Generated state: {state}")
        logger.debug(f"Updated Session: {request.session}")
        logger.debug(f"Session contains state: {'oauth_state' in request.session}")


        # Enhanced authorization with state parameter
        redirect_uri = str(request.url_for('google_callback'))
        google_client = cast(Any, google_oauth.google)
        authorization_url = await google_client.create_authorization_url(
            redirect_uri,
            state=state,
            # Additional security parameters
            access_type='offline',
            prompt='consent',
            include_granted_scopes='true'
        )
        
        log_security_event(
            "OAUTH_INITIATION", 
            {"ip": client_ip, "provider": "google"}
        )
        logger.info(f"authorization_url type: {type(authorization_url)}, value: {authorization_url}")
        url = authorization_url['url']
        return RedirectResponse(url)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OAuth initiation failed: {e}")
        raise HTTPException(status_code=500, detail="Authentication service unavailable")

@router.get("/google/callback")
async def google_callback(request: Request, response: Response):
    """Handle Google OAuth callback with comprehensive security validation"""
    logger.debug("\n=== OAuth Callback Debug ===")
    logger.debug(f"Full Callback URL: {request.url}")
    logger.debug(f"Callback Headers: {dict(request.headers)}")
    logger.debug(f"Callback Session State: {request.session}")
    logger.debug(f"Callback Query Params: {dict(request.query_params)}")
    logger.debug(f"Callback Cookies: {request.cookies}")
    
    client_ip = get_client_ip(request)
    try:
        # Add logging before token fetch
        logger.debug("Attempting to get token from Google")
        google_client = getattr(google_oauth, "google", None)
        if google_client is None:
            logger.error("Google OAuth client is not initialized (google_oauth.google is None)")
            raise HTTPException(status_code=500, detail="Google OAuth client not available")
        token = await google_client.authorize_access_token(request)
        logger.debug("Successfully retrieved token from Google")
        
        logger.debug("Attempting to get user info")
        user_info = await google_client.parse_id_token(request, token)
        logger.debug(f"User info received: {json.dumps(user_info, default=str)}")
        
        # Extract essential user information
        google_sub: Optional[str] = user_info.get('sub')
        email: Optional[str] = user_info.get('email')
        name: str = user_info.get('name', email.split('@')[0] if email else 'Unknown')
        
        if not google_sub or not email:
            log_security_event(
                "OAUTH_INCOMPLETE_DATA",
                {"ip": client_ip, "missing_fields": [k for k in ['sub', 'email'] if not user_info.get(k)]},
                "WARNING"
            )
            raise HTTPException(status_code=400, detail="Incomplete user data from OAuth provider")
        
        # Comprehensive security validation
        try:
            validate_email_security(email, user_info)
        except SecurityValidationError as e:
            log_security_event(
                "OAUTH_SECURITY_VIOLATION",
                {
                    "ip": client_ip, 
                    "email": email, 
                    "reason": str(e),
                    "user_data": {
                        "email_verified": user_info.get('email_verified', False),
                        "domain": email.split('@')[-1] if '@' in email else None
                    }
                },
                "WARNING"
            )
            raise HTTPException(status_code=403, detail=str(e))
        
        # Enhance user data with security metadata
        enhanced_user_data = enhance_user_data_security(user_info)
        # Extract essential user information
        google_sub: Optional[str] = user_info.get('sub')
        email: Optional[str] = user_info.get('email')
        name: str = user_info.get('name', email.split('@')[0] if email else 'Unknown')
        
        if not google_sub or not email:
            log_security_event(
                "OAUTH_INCOMPLETE_DATA",
                {"ip": client_ip, "missing_fields": [k for k in ['sub', 'email'] if not user_info.get(k)]},
                "WARNING"
            )
            raise HTTPException(status_code=400, detail="Incomplete user data from OAuth provider")
        
        # Comprehensive security validation
        try:
            validate_email_security(email, user_info)
        except SecurityValidationError as e:
            log_security_event(
                "OAUTH_SECURITY_VIOLATION",
                {
                    "ip": client_ip, 
                    "email": email, 
                    "reason": str(e),
                    "user_data": {
                        "email_verified": user_info.get('email_verified', False),
                        "domain": email.split('@')[-1] if '@' in email else None
                    }
                },
                "WARNING"
            )
            raise HTTPException(status_code=403, detail=str(e))
        
        # Enhance user data with security metadata
        enhanced_user_data = enhance_user_data_security(user_info)
        
        # Get or create user
        user = await get_or_create_user(google_sub, email, name)
        
        if not user:
            log_security_event(
                "USER_CREATION_FAILED",
                {"ip": client_ip, "email": email, "google_sub": google_sub},
                "ERROR"
            )
            log_security_event(
                "USER_CREATION_FAILED",
                {"ip": client_ip, "email": email, "google_sub": google_sub},
                "ERROR"
            )
            raise HTTPException(status_code=500, detail="Failed to create or retrieve user")
        
        # Create JWT token with enhanced claims
        
        # Create JWT token with enhanced claims
        jwt_token = create_jwt_token(
            google_sub=google_sub,
            email=email,
            user_id=google_sub,  # user_id = google_sub for system consistency
            roles=user.get('roles', ['user'])
        )
        
        # Log successful authentication
        log_security_event(
            "OAUTH_SUCCESS",
            {
                "ip": client_ip,
                "email": email,
                "google_sub": google_sub,
                "email_verified": user_info.get('email_verified', False)
            }
        )
        
        # Set secure cookie and redirect
    
        # Log successful authentication
        
        # Set secure cookie and redirect
        redirect_response = RedirectResponse("http://localhost:5173/dashboard")
        redirect_response.set_cookie(
            key="access_token",
            value=jwt_token,
            httponly=True,
            secure=False,  # Set to True in production with HTTPS
            samesite="lax",
            max_age=JWT_EXPIRATION_DAYS * 24 * 60 * 60
        )
        
        return redirect_response
        
    except OAuthError as e:
        log_security_event(
            "OAUTH_ERROR",
            {"ip": client_ip, "error": str(e)},
            "WARNING"
        )
        log_security_event(
            "OAUTH_ERROR",
            {"ip": client_ip, "error": str(e)},
            "WARNING"
        )
        logger.error(f"OAuth error: {e}")
        raise HTTPException(status_code=400, detail=f"OAuth authentication failed: {str(e)}")
    except Exception as e:
        # Handle non-HTTPException, non-OAuthError cases (e.g., database errors)
        log_security_event(
            "OAUTH_SYSTEM_ERROR",
            {"ip": client_ip, "error": str(e)},
            "ERROR"
        )
        logger.error(f"Authentication system error: {e}")
        raise HTTPException(status_code=500, detail="Authentication service error")
    

@router.get("/me")
async def get_current_user(request: Request):
    """Get current user info from JWT cookie"""
    token = request.cookies.get("access_token")
    
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")    
    try:
        payload = await decode_jwt_token(token)
        return {
            "user_id": payload['user_id'],  # This is Google's sub
            "email": payload['email'],
            "roles": payload['roles']
        }
    except HTTPException:
        raise

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
    
from upstash_redis import Redis as UpstashRedis
from src.config.settings import OTP_REDIS_URL, OTP_REDIS_TOKEN

# Ensure OTP_REDIS_URL and OTP_REDIS_TOKEN are set (not None)
if OTP_REDIS_URL is None or OTP_REDIS_TOKEN is None:
    raise RuntimeError("OTP_REDIS_URL and OTP_REDIS_TOKEN must be set in the environment/config.")

# Singleton Upstash client for OTP logic (not per-request)
otp_redis = UpstashRedis(url=OTP_REDIS_URL, token=OTP_REDIS_TOKEN)