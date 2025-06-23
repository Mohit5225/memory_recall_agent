import os
import jwt
import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from fastapi import HTTPException, Request
from .token_blacklist import token_blacklist, RedisConnectionError

logger = logging.getLogger(__name__)

# JWT Configuration
JWT_SECRET = os.getenv('JWT_SECRET_KEY')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRATION_DAYS = 7

def create_jwt_token(google_sub: str, email: str, user_id: str, roles: Optional[List[str]] = None) -> str:
    """Create JWT token with user data and unique JTI for revocation"""
    if not JWT_SECRET:
        raise ValueError("JWT_SECRET_KEY not configured")
    
    now = datetime.now(timezone.utc)
    jti = str(uuid.uuid4())  # Unique token ID for revocation
    
    payload = {
        'sub': google_sub,
        'email': email,
        'user_id': user_id,
        'roles': roles or ['user'],
        'jti': jti,  # JWT ID for token revocation
        'exp': now + timedelta(days=JWT_EXPIRATION_DAYS),
        'iat': now
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

async def decode_jwt_token(token: str, check_blacklist: bool = True) -> Dict[str, Any]:
    """Decode and validate JWT token with blacklist checking"""
    if not JWT_SECRET:
        raise ValueError("JWT_SECRET_KEY not configured")
    
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        
        # Check if token is blacklisted (revoked)
        if check_blacklist:
            jti = payload.get('jti')
            if jti:
                try:
                    if await token_blacklist.is_token_revoked(jti):
                        raise HTTPException(status_code=401, detail="Token has been revoked")
                except RedisConnectionError:
                    # Redis is down and fail_secure=True - deny access
                    logger.error(f"Redis unavailable during token verification - denying access (fail-secure)")
                    raise HTTPException(status_code=503, detail="Authentication service unavailable")
            
            # Check if user's tokens were revoked after this token was issued
            user_sub = payload.get('sub')
            iat = payload.get('iat')
            if user_sub and iat:
                token_issued_at = datetime.fromtimestamp(iat, timezone.utc)
                try:
                    if await token_blacklist.is_user_tokens_revoked(user_sub, token_issued_at):
                        raise HTTPException(status_code=401, detail="User tokens have been revoked")
                except RedisConnectionError:
                    # Redis is down and fail_secure=True - deny access
                    logger.error(f"Redis unavailable during user token verification - denying access (fail-secure)")
                    raise HTTPException(status_code=503, detail="Authentication service unavailable")
        
        return payload
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def get_current_user_from_token(request: Request) -> Optional[Dict[str, Any]]:
    """Extract current user from JWT token in request cookies"""
    token = request.cookies.get("access_token")
    
    if not token:
        return None
    
    try:
        return await decode_jwt_token(token)
    except HTTPException:
        return None

async def revoke_token_from_request(request: Request) -> bool:
    """Revoke the JWT token from the request"""
    token = request.cookies.get("access_token")
    
    if not token:
        return True  # No token to revoke
    
    try:
        # Decode without blacklist check to get token data
        payload = await decode_jwt_token(token, check_blacklist=False)
        jti = payload.get('jti')
        exp = payload.get('exp')
        
        if jti and exp:
            try:
                return await token_blacklist.revoke_token(jti, exp)
            except RedisConnectionError:
                # Redis is down - log error but don't fail logout
                logger.error("Redis unavailable during token revocation - logout will proceed")
                return False  # Indicate revocation failed but allow logout to continue
        
        return False
        
    except Exception as e:
        logger.error(f"Failed to revoke token: {e}")
        return False

async def revoke_all_user_tokens_safe(google_sub: str) -> Dict[str, Any]:
    """Safely revoke all tokens for a user with proper error handling"""
    try:
        count = await token_blacklist.revoke_all_user_tokens(google_sub)
        return {
            "success": True,
            "revoked_count": count,
            "message": f"All tokens revoked for user {google_sub}"
        }
    except RedisConnectionError as e:
        logger.error(f"Redis unavailable during emergency token revocation for user {google_sub}: {e}")
        return {
            "success": False,
            "revoked_count": 0,
            "message": "Token revocation service unavailable - user should change password and re-login",
            "error": str(e)
        }
    except Exception as e:
        logger.error(f"Failed to revoke all tokens for user {google_sub}: {e}")
        return {
            "success": False,
            "revoked_count": 0,
            "message": "Token revocation failed due to system error",
            "error": str(e)
        }

def create_mock_jwt_token(user: str) -> str:
    """Create mock JWT token for development"""
    return create_jwt_token(
        google_sub=f"mock_{user}",
        email=f"{user}@mock.com",
        user_id=user,
        roles=["user"]
    )