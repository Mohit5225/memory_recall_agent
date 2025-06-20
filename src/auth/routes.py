import logging
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

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/auth", tags=["authentication"])

@router.get("/google")
async def google_login(request: Request):
    """Start Google OAuth login"""
    redirect_uri = "http://localhost:8000/auth/google/callback"
    return await google_oauth.google.authorize_redirect(request, redirect_uri)

@router.get("/google/callback")
async def google_callback(request: Request, response: Response):
    """Handle Google OAuth callback"""
    try:
        # Get token from Google
        token = await google_oauth.google.authorize_access_token(request)
        user_info = await google_oauth.google.get('userinfo', token=token)
        user_data = user_info.json()
        
        google_sub = user_data['sub']
        email = user_data['email']
        name = user_data.get('name', email.split('@')[0])
        
        # Get or create user
        user = await get_or_create_user(google_sub, email, name)
        
        if not user:
            raise HTTPException(status_code=500, detail="Failed to create or retrieve user")
        
        # Create JWT token
        jwt_token = create_jwt_token(
            google_sub=google_sub,
            email=email,
            user_id=name,
            roles=user.get('roles', ['user'])
        )
        
        # Set cookie and redirect
        response = Response("Login successful! You can close this window.")
        response.set_cookie(
            key="access_token",
            value=jwt_token,
            httponly=True,
            secure=False,  # Set to True in production
            samesite="lax",
            max_age=JWT_EXPIRATION_DAYS * 24 * 60 * 60
        )
        
        return response
        
    except OAuthError as e:
        logger.error(f"OAuth error: {e}")
        raise HTTPException(status_code=400, detail=f"OAuth error: {str(e)}")
    except Exception as e:
        logger.error(f"Authentication failed: {e}")
        raise HTTPException(status_code=500, detail=f"Authentication failed: {str(e)}")

@router.get("/me")
async def get_current_user(request: Request):
    """Get current user info from JWT cookie"""
    token = request.cookies.get("access_token")
    
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        payload = await decode_jwt_token(token)
        return {
            "google_sub": payload['sub'],
            "email": payload['email'],
            "user_id": payload['user_id'],
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