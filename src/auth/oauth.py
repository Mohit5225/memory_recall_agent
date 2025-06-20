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
        authorize_url='https://accounts.google.com/o/oauth2/auth',
        access_token_url='https://oauth2.googleapis.com/token',
        userinfo_endpoint='https://openidconnect.googleapis.com/v1/userinfo',
        client_kwargs={'scope': 'openid email profile'}
    )
    return oauth

# Initialize OAuth on module import
google_oauth = setup_google_oauth()