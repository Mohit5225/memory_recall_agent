import logging
import secrets
from datetime import datetime, timezone
from typing import Dict, Any, Optional, cast
import secrets
from datetime import datetime, timezone
from typing import Dict, Any, Optional, cast
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuthError
import json
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

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/auth", tags=["authentication"])

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
          # Enhanced authorization with state parameter
        redirect_uri = request.url_for('google_callback')
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
        
        return RedirectResponse(authorization_url)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OAuth initiation failed: {e}")
        raise HTTPException(status_code=500, detail="Authentication service unavailable")

@router.get("/google/callback")
async def google_callback(request: Request, response: Response):
    """Handle Google OAuth callback with comprehensive security validation"""
    client_ip = get_client_ip(request)
    
    """Handle Google OAuth callback with comprehensive security validation"""
    client_ip = get_client_ip(request)
    
    try:
        # Get token from Google with type casting for dynamic attribute
        google_client = cast(Any, google_oauth.google)
        token = await google_client.authorize_access_token(request)
        user_info = await google_client.get('userinfo', token=token)
        user_data: Dict[str, Any] = user_info.json()  # Explicit type annotation
        
        # Extract essential user information
        google_sub: Optional[str] = user_data.get('sub')
        email: Optional[str] = user_data.get('email')
        name: str = user_data.get('name', email.split('@')[0] if email else 'Unknown')
        
        if not google_sub or not email:
            log_security_event(
                "OAUTH_INCOMPLETE_DATA",
                {"ip": client_ip, "missing_fields": [k for k in ['sub', 'email'] if not user_data.get(k)]},
                "WARNING"
            )
            raise HTTPException(status_code=400, detail="Incomplete user data from OAuth provider")
        
        # Comprehensive security validation
        try:
            validate_email_security(email, user_data)
        except SecurityValidationError as e:
            log_security_event(
                "OAUTH_SECURITY_VIOLATION",
                {
                    "ip": client_ip, 
                    "email": email, 
                    "reason": str(e),
                    "user_data": {
                        "email_verified": user_data.get('email_verified', False),
                        "domain": email.split('@')[-1] if '@' in email else None
                    }
                },
                "WARNING"
            )
            raise HTTPException(status_code=403, detail=str(e))
        
        # Enhance user data with security metadata
        enhanced_user_data = enhance_user_data_security(user_data)
        # Extract essential user information
        google_sub: Optional[str] = user_data.get('sub')
        email: Optional[str] = user_data.get('email')
        name: str = user_data.get('name', email.split('@')[0] if email else 'Unknown')
        
        if not google_sub or not email:
            log_security_event(
                "OAUTH_INCOMPLETE_DATA",
                {"ip": client_ip, "missing_fields": [k for k in ['sub', 'email'] if not user_data.get(k)]},
                "WARNING"
            )
            raise HTTPException(status_code=400, detail="Incomplete user data from OAuth provider")
        
        # Comprehensive security validation
        try:
            validate_email_security(email, user_data)
        except SecurityValidationError as e:
            log_security_event(
                "OAUTH_SECURITY_VIOLATION",
                {
                    "ip": client_ip, 
                    "email": email, 
                    "reason": str(e),
                    "user_data": {
                        "email_verified": user_data.get('email_verified', False),
                        "domain": email.split('@')[-1] if '@' in email else None
                    }
                },
                "WARNING"
            )
            raise HTTPException(status_code=403, detail=str(e))
        
        # Enhance user data with security metadata
        enhanced_user_data = enhance_user_data_security(user_data)
        
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
                "email_verified": user_data.get('email_verified', False)
            }
        )
        
        # Set secure cookie and redirect
    
        # Log successful authentication
        
        # Set secure cookie and redirect
        success_response = Response("✅ Login successful! You can close this window.")
        success_response.set_cookie(
            key="access_token",
            value=jwt_token,
            httponly=True,
            secure=False,  # Set to True in production with HTTPS
            samesite="lax",
            max_age=JWT_EXPIRATION_DAYS * 24 * 60 * 60
        )
        
        return success_response
        
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
            "warning": None if redis_status else "Redis unavailable - authentication will fail in fail-secure mode"
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "redis_available": False,
            "fail_secure_mode": token_blacklist.fail_secure,
            "error": str(e)
        }