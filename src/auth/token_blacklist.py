import redis
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Set
from src.config.settings import REDIS_HOST, REDIS_PORT

logger = logging.getLogger(__name__)

class RedisConnectionError(Exception):
    """Raised when Redis is unavailable and authentication should fail"""
    pass

class TokenBlacklist:
    """
    Redis-based token blacklist for JWT revocation.
    Stores revoked tokens with their expiration time for automatic cleanup.
    
    SECURITY: Implements fail-secure behavior - denies access when Redis is unavailable.
    """
    
    def __init__(self, fail_secure: bool = True):
        """
        Initialize Redis connection for token blacklist
        
        Args:
            fail_secure: If True, authentication fails when Redis is unavailable (SECURE)
                        If False, allows access when Redis is down (INSECURE - only for dev)
        """
        self.fail_secure = fail_secure
        self._redis_available = False
        
        try:
            self.redis_client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=1,  # Use different DB than Celery (which uses DB 0)
                decode_responses=True,
                socket_connect_timeout=5,  # 5 second timeout
                socket_timeout=5,
                retry_on_timeout=True
            )
            # Test connection
            self.redis_client.ping()
            self._redis_available = True
            logger.info("Connected to Redis for token blacklist (fail-secure mode enabled)")
        except redis.ConnectionError as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self.redis_client = None
            if self.fail_secure:
                logger.critical("Redis unavailable and fail_secure=True - authentication will be DENIED for security")
            else:
                logger.warning("Redis unavailable and fail_secure=False - authentication will be ALLOWED (INSECURE)")
    
    def _check_redis_health(self) -> bool:
        """Check if Redis is available and update status"""
        if not self.redis_client:
            return False
            
        try:
            self.redis_client.ping()
            if not self._redis_available:
                logger.info("Redis connection restored")
            self._redis_available = True
            return True
        except Exception as e:
            if self._redis_available:
                logger.error(f"Redis connection lost: {e}")
            self._redis_available = False
            return False    
    def _get_token_key(self, jti: str) -> str:
        """Generate Redis key for token"""
        return f"blacklist:token:{jti}"
    
    async def revoke_token(self, jti: str, exp_timestamp: int) -> bool:
        """
        Add token to blacklist with automatic expiration.
        
        Args:
            jti: JWT ID (unique token identifier)
            exp_timestamp: Token expiration timestamp
            
        Returns:
            bool: True if successfully added to blacklist
            
        Raises:
            RedisConnectionError: If Redis is unavailable and fail_secure=True
        """
        if not self._check_redis_health():
            if self.fail_secure:
                raise RedisConnectionError("Cannot revoke token: Redis is unavailable")
            else:
                logger.warning("Redis unavailable - token revocation failed (fail_secure=False)")
                return False
        
        try:
            key = self._get_token_key(jti)
            
            # Calculate TTL (time until token would naturally expire)
            current_time = datetime.now(timezone.utc).timestamp()
            ttl_seconds = max(0, int(exp_timestamp - current_time))
            
            if ttl_seconds <= 0:
                # Token already expired, no need to blacklist
                return True
            
            # Store token in blacklist with TTL
            revocation_data = {
                "revoked_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": datetime.fromtimestamp(exp_timestamp, timezone.utc).isoformat()
            }
            
            self.redis_client.setex(
                key,
                ttl_seconds,
                json.dumps(revocation_data)
            )
            
            logger.info(f"Token {jti} added to blacklist, expires in {ttl_seconds}s")
            return True
            
        except Exception as e:
            logger.error(f"Failed to revoke token {jti}: {e}")
            if self.fail_secure:
                raise RedisConnectionError(f"Token revocation failed: {e}")
            return False    
    async def is_token_revoked(self, jti: str) -> bool:
        """
        Check if token is in blacklist.
        
        Args:
            jti: JWT ID to check
            
        Returns:
            bool: True if token is revoked OR if Redis is down and fail_secure=True
                 False only if token is confirmed NOT revoked and Redis is healthy
                 
        Raises:
            RedisConnectionError: If Redis is unavailable and fail_secure=True
        """
        if not self._check_redis_health():
            if self.fail_secure:
                logger.warning(f"Redis unavailable - DENYING access for token {jti} (fail-secure mode)")
                raise RedisConnectionError("Cannot verify token: Redis is unavailable")
            else:
                logger.warning(f"Redis unavailable - ALLOWING access for token {jti} (fail-open mode - INSECURE)")
                return False
        
        try:
            key = self._get_token_key(jti)
            exists = self.redis_client.exists(key)
            
            if exists:
                logger.info(f"Token {jti} found in blacklist - revoked")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to check token blacklist for {jti}: {e}")
            if self.fail_secure:
                logger.warning(f"Redis error - DENYING access for token {jti} (fail-secure mode)")
                raise RedisConnectionError(f"Token verification failed: {e}")
            else:
                logger.warning(f"Redis error - ALLOWING access for token {jti} (fail-open mode - INSECURE)")
                return False    
    async def revoke_all_user_tokens(self, user_sub: str) -> int:
        """
        Revoke all tokens for a specific user (for account security).
        This is a more aggressive approach that uses a user-level blacklist.
        
        Args:
            user_sub: User's Google sub identifier
            
        Returns:
            int: Number of tokens potentially affected
            
        Raises:
            RedisConnectionError: If Redis is unavailable and fail_secure=True
        """
        if not self._check_redis_health():
            if self.fail_secure:
                raise RedisConnectionError("Cannot revoke user tokens: Redis is unavailable")
            else:
                logger.warning("Redis unavailable - user token revocation failed (fail_secure=False)")
                return 0
        
        try:
            user_key = f"blacklist:user:{user_sub}"
            
            # Set user-level revocation timestamp
            revocation_time = datetime.now(timezone.utc).isoformat()
            
            # Store with 7 days TTL (same as JWT expiration)
            self.redis_client.setex(
                user_key,
                7 * 24 * 60 * 60,  # 7 days
                revocation_time
            )
            
            logger.info(f"All tokens revoked for user {user_sub}")
            return 1  # We don't know exact count, but indicate success
            
        except Exception as e:
            logger.error(f"Failed to revoke all tokens for user {user_sub}: {e}")
            if self.fail_secure:
                raise RedisConnectionError(f"User token revocation failed: {e}")
            return 0    
    async def is_user_tokens_revoked(self, user_sub: str, token_issued_at: datetime) -> bool:
        """
        Check if user's tokens were revoked after this token was issued.
        
        Args:
            user_sub: User's Google sub identifier
            token_issued_at: When the token was issued
            
        Returns:
            bool: True if user's tokens were revoked after token issuance 
                 OR if Redis is down and fail_secure=True
                 False only if user tokens are confirmed NOT revoked and Redis is healthy
                 
        Raises:
            RedisConnectionError: If Redis is unavailable and fail_secure=True
        """        if not self._check_redis_health():
            if self.fail_secure:
                logger.warning(f"Redis unavailable - DENYING access for user {user_sub} (fail-secure mode)")
                raise RedisConnectionError("Cannot verify user tokens: Redis is unavailable")
            else:
                logger.warning(f"Redis unavailable - ALLOWING access for user {user_sub} (fail-open mode - INSECURE)")
                return False
        
        try:
            user_key = f"blacklist:user:{user_sub}"
            revocation_time_str = self.redis_client.get(user_key)
            
            if not revocation_time_str:
                return False
            
            revocation_time = datetime.fromisoformat(revocation_time_str)
            
            # If user revocation happened after token was issued, token is invalid
            if revocation_time > token_issued_at:
                logger.info(f"User {user_sub} tokens revoked after token issuance")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to check user token revocation for {user_sub}: {e}")
            if self.fail_secure:
                logger.warning(f"Redis error - DENYING access for user {user_sub} (fail-secure mode)")
                raise RedisConnectionError(f"User token verification failed: {e}")
            else:
                logger.warning(f"Redis error - ALLOWING access for user {user_sub} (fail-open mode - INSECURE)")
                return False

# Global blacklist instance - FAIL SECURE by default (production-ready)
token_blacklist = TokenBlacklist(fail_secure=True)

# For development/testing only - uncomment the line below to use fail-open mode
# token_blacklist = TokenBlacklist(fail_secure=False)
