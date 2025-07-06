import os
from authlib.integrations.starlette_client import OAuth

# OAuth configuration
oauth = OAuth()

def setup_google_oauth():
    """Initialize Google OAuth client"""
    oauth.register(
        name='google',
        client_id=os.getenv('GOOGLE_OAUTH_CLIENT_ID'),
        client_secret=os.getenv('GOOGLE_OAUTH_CLIENT_SECRET'),
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile'}
    )
    return oauth

# Initialize OAuth on module import
google_oauth = setup_google_oauth()