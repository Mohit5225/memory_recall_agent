import logging
import secrets
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuthError

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
        authorization_url = await google_oauth.google.create_authorization_url(
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
    
    try:
        # Get token from Google
        token = await google_oauth.google.authorize_access_token(request)
        user_info = await google_oauth.google.get('userinfo', token=token)
        user_data = user_info.json()
        
        # Extract essential user information
        google_sub = user_data.get('sub')
        email = user_data.get('email')
        name = user_data.get('name', email.split('@')[0] if email else 'Unknown')
        
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
            raise HTTPException(status_code=500, detail="Failed to create or retrieve user")
        
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
        logger.error(f"OAuth error: {e}")
        raise HTTPException(status_code=400, detail=f"OAuth authentication failed: {str(e)}")
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        log_security_event(
            "OAUTH_SYSTEM_ERROR",
            {"ip": client_ip, "error": str(e)},
            "ERROR"
        )
        logger.error(f"Authentication system error: {e}")
        raise HTTPException(status_code=500, detail="Authentication service error")

@router.get("/me")
async def get_current_user(request: Request):
    """Get current authenticated user information"""
    try:
        from .jwt_utils import get_current_user_from_token
        user = await get_current_user_from_token(request)
        
        if not user:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        # Return safe user information (exclude sensitive data)
        safe_user_data = {
            "user_id": user.get("user_id"),
            "email": user.get("email"),
            "google_sub": user.get("google_sub"),
            "roles": user.get("roles", ["user"]),
            "iat": user.get("iat"),
            "exp": user.get("exp")
        }
        
        return {"user": safe_user_data}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get current user failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve user information")

@router.post("/logout")
async def logout(request: Request):
    """Logout user and revoke token"""
    try:
        # Revoke the current token
        success = await revoke_token_from_request(request)
        
        # Create response with cleared cookie
        response = Response(
            content='{"message": "Successfully logged out"}',
            media_type="application/json"
        )
        response.delete_cookie("access_token")
        
        if success:
            log_security_event(
                "USER_LOGOUT",
                {"ip": get_client_ip(request)},
            )
        
        return response
            
    except Exception as e:
        logger.error(f"Logout failed: {e}")
        # Still clear cookie even if revocation fails
        response = Response(
            content='{"message": "Logged out (with errors)"}',
            media_type="application/json"
        )
        response.delete_cookie("access_token")
        return response

@router.get("/mock-login")
async def mock_login(user: str, response: Response):
    """Mock login for development/testing only"""
    if not user:
        raise HTTPException(status_code=400, detail="User parameter required")
    
    # Create mock JWT token
    mock_token = create_mock_jwt_token(user)
    
    # Set cookie
    response.set_cookie(
        key="access_token",
        value=mock_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=JWT_EXPIRATION_DAYS * 24 * 60 * 60
    )
    
    log_security_event(
        "MOCK_LOGIN",
        {"user": user},
        "WARNING"  # Mark as warning since this is for dev only
    )
    
    return {"message": f"Mock login successful for user: {user}"}

@router.post("/revoke-all-tokens")
async def revoke_all_user_tokens_endpoint(request: Request):
    """Revoke all tokens for the current user"""
    try:
        from .jwt_utils import get_current_user_from_token
        user = await get_current_user_from_token(request)
        
        if not user:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        google_sub = user.get("google_sub")
        if not google_sub:
            raise HTTPException(status_code=400, detail="Invalid user data")
        
        result = await revoke_all_user_tokens_safe(google_sub)
        
        # Clear current cookie
        response = Response(
            content=f'{{"success": {str(result["success"]).lower()}, "message": "{result["message"]}", "affected_tokens": {result.get("revoked_count", 0)}}}',
            media_type="application/json"
        )
        response.delete_cookie("access_token")
        
        log_security_event(
            "TOKEN_REVOCATION_ALL",
            {
                "ip": get_client_ip(request),
                "google_sub": google_sub,
                "success": result.get("success", False)
            }
        )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token revocation failed: {e}")
        # Still clear cookie
        response = Response(
            content='{"success": false, "message": "Token revocation service error", "affected_tokens": 0}',
            media_type="application/json"
        )
        response.delete_cookie("access_token")
        return response

@router.get("/health")
async def auth_health_check():
    """Health check endpoint for authentication service"""
    try:
        # Check token blacklist health
        blacklist_healthy = True
        try:
            # Test blacklist functionality
            test_result = await token_blacklist.is_token_revoked("health-check-token")
            if test_result is None:
                blacklist_healthy = False
        except Exception:
            blacklist_healthy = False
        
        health_status = {
            "status": "healthy" if blacklist_healthy else "degraded",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "components": {
                "token_blacklist": "healthy" if blacklist_healthy else "unhealthy",
                "oauth_provider": "healthy"  # Assume healthy if we can import
            }
        }
        
        status_code = 200 if blacklist_healthy else 503
        return Response(
            content=str(health_status),
            status_code=status_code,
            media_type="application/json"
        )
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return Response(
            content='{"status": "unhealthy", "error": "Health check failed"}',
            status_code=503,
            media_type="application/json"
        )
