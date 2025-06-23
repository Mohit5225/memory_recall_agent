import os
from authlib.integrations.starlette_client import OAuth
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from authlib.integrations.starlette_client import StarletteOAuth2App

class GoogleOAuthClient(Protocol):
    """Type stub for dynamically created google oauth client"""
    async def create_authorization_url(self, redirect_uri: str, **kwargs: Any) -> str: ...
    async def authorize_access_token(self, request: Any) -> Any: ...
    async def get(self, endpoint: str, **kwargs: Any) -> Any: ...

# OAuth configuration
oauth = OAuth()

def setup_google_oauth() -> OAuth:
    """Initialize Google OAuth client with enhanced security scopes"""
    oauth.register(
        name='google',
        client_id=os.getenv('GOOGLE_OAUTH_CLIENT_ID'),
        client_secret=os.getenv('GOOGLE_OAUTH_CLIENT_SECRET'),
        authorize_url='https://accounts.google.com/o/oauth2/auth',
        access_token_url='https://oauth2.googleapis.com/token',
        userinfo_endpoint='https://openidconnect.googleapis.com/v1/userinfo',
        client_kwargs={
            'scope': 'openid email profile',
            # Enhanced security parameters
            'access_type': 'offline',
            'prompt': 'consent',
            'include_granted_scopes': 'true',
            # Request additional claims for security
            'claims': '{"userinfo":{"email_verified":{"essential":true}}}'
        }
    )
    return oauth

# Initialize OAuth on module import
google_oauth = setup_google_oauth()

# Type-safe accessor for the google client
def get_google_client() -> GoogleOAuthClient:
    """Get the Google OAuth client with proper typing"""
    return getattr(google_oauth, 'google')  # type: ignore