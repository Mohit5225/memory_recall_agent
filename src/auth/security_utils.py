# src/auth/security_utils.py
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, Set, Optional
from src.config.settings import (
    OAUTH_REQUIRE_EMAIL_VERIFICATION, 
    OAUTH_BLOCK_DISPOSABLE_EMAILS,
    OAUTH_ALLOWED_DOMAINS,
    OAUTH_MAX_LOGIN_ATTEMPTS,
    OAUTH_RATE_LIMIT_WINDOW
)

logger = logging.getLogger(__name__)

# Known disposable email domains (expandable list)
DISPOSABLE_EMAIL_DOMAINS = {
    # Temporary email services
    '10minutemail.com', '10minutemail.net', '20minutemail.com', '2prong.com',
    '30minutemail.com', '33mail.com', '3d-game.com', '4warding.com',
    '7tags.com', '9ox.net', 'amilegit.com', 'anonbox.net', 'anonymbox.com',
    'antichef.com', 'antichef.net', 'antispam.de', 'armyspy.com',
    
    # Guerrilla mail variants
    'guerrillamail.biz', 'guerrillamail.com', 'guerrillamail.de', 
    'guerrillamail.info', 'guerrillamail.net', 'guerrillamail.org',
    'guerrillamailblock.com', 'sharklasers.com', 'pokemail.net',
    
    # Mailinator variants
    'mailinator.com', 'mailinator.net', 'mailinator.org', 'mailinator2.com',
    'notmailinator.com', 'themailinator.com', 'mailinator.gq',
    
    # YOPmail variants
    'yopmail.com', 'yopmail.fr', 'yopmail.net', 'cool.fr.nf', 'jetable.fr.nf',
    'nospam.ze.tc', 'nomail.xl.cx', 'mega.zik.dj', 'speed.1s.fr',
    
    # TempMail variants
    'tempmail.org', 'temp-mail.org', 'temp-mail.ru', 'tempmail.net',
    'tempmail.co', 'tempmailaddress.com', 'tempinbox.com',
    
    # Other popular disposable services
    'throwaway.email', 'throwawaymail.com', 'trashmail.com', 'maildrop.cc',
    'mailnesia.com', 'emailondeck.com', 'fakeinbox.com', 'spamgourmet.com',
    'incognitomail.org', 'mytemp.email', 'temp-mail.io', 'tempail.com',
    'mohmal.com', 'emailfake.com', 'emkei.cz', 'fake-mail.ml',
    
    # Burner email services
    'burnermail.io', 'guerrillamail.org', 'getnada.com', 'tempmailo.com',
    'dispostable.com', 'mailcatch.com', 'mailhazard.com', 'tempemailgen.com',
    
    # 10 minute variants
    '10minemail.com', '10minutesmail.com', '10minutesemail.com',
    '2mailnext.com', 'correotemporal.org', 'fakedisposableemailgenerator.com',
    
    # Regional/language specific
    'wegwerfmail.de', 'wegwerfemail.de', 'trashmail.de', 'byom.de',
    'jetable.org', 'jetable.net', 'jetable.com', 'jourrapide.com',
    'correo.blogos.net', 'dropcatch.com', 'emailto.de', 'emeil.in',
}

# Rate limiting storage (in production, use Redis)
login_attempts: Dict[str, Dict[str, any]] = {}

class SecurityValidationError(Exception):
    """Raised when security validation fails"""
    pass

def validate_email_security(email: str, user_data: Dict) -> None:
    """
    Comprehensive email security validation
    
    Args:
        email: Email address to validate
        user_data: User data from OAuth provider
        
    Raises:
        SecurityValidationError: If validation fails
    """
    # 1. Email verification check
    if OAUTH_REQUIRE_EMAIL_VERIFICATION:
        email_verified = user_data.get('email_verified', False)
        if not email_verified:
            logger.warning(f"Authentication attempt with unverified email: {email}")
            raise SecurityValidationError(
                "Email not verified. Please verify your email with Google first."
            )
    
    # 2. Disposable email check
    if OAUTH_BLOCK_DISPOSABLE_EMAILS and is_disposable_email(email):
        logger.warning(f"Authentication attempt with disposable email: {email}")
        raise SecurityValidationError(
            "Disposable email addresses are not allowed. Please use a permanent email address."
        )
    
    # 3. Domain whitelist check
    if OAUTH_ALLOWED_DOMAINS and not is_allowed_domain(email):
        logger.warning(f"Authentication attempt with non-whitelisted domain: {email}")
        raise SecurityValidationError(
            f"Email domain not allowed. Allowed domains: {', '.join(OAUTH_ALLOWED_DOMAINS)}"
        )
    
    # 4. Email format validation (additional check)
    if not is_valid_email_format(email):
        logger.warning(f"Authentication attempt with invalid email format: {email}")
        raise SecurityValidationError("Invalid email format.")

def is_disposable_email(email: str) -> bool:
    """Check if email is from a known disposable email provider"""
    try:
        domain = email.split('@')[-1].lower().strip()
        return domain in DISPOSABLE_EMAIL_DOMAINS
    except (IndexError, AttributeError):
        return True  # Treat malformed emails as suspicious

def is_allowed_domain(email: str) -> bool:
    """Check if email domain is in the allowed list"""
    if not OAUTH_ALLOWED_DOMAINS:
        return True  # No restrictions if no domains specified
    
    try:
        domain = email.split('@')[-1].lower().strip()
        return domain in [d.lower().strip() for d in OAUTH_ALLOWED_DOMAINS]
    except (IndexError, AttributeError):
        return False

def is_valid_email_format(email: str) -> bool:
    """Validate email format using regex"""
    email_pattern = re.compile(
        r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    )
    return bool(email_pattern.match(email))

def check_rate_limit(ip_address: str) -> bool:
    """
    Check if IP address has exceeded login attempt rate limit
    
    Args:
        ip_address: Client IP address
        
    Returns:
        True if rate limit not exceeded, False otherwise
    """
    now = datetime.now(timezone.utc)
    
    # Clean up old entries
    cleanup_rate_limit_data(now)
    
    if ip_address not in login_attempts:
        login_attempts[ip_address] = {
            'count': 0,
            'first_attempt': now,
            'last_attempt': now
        }
    
    attempt_data = login_attempts[ip_address]
    
    # Check if we're within the rate limit window
    time_diff = (now - attempt_data['first_attempt']).total_seconds()
    
    if time_diff > OAUTH_RATE_LIMIT_WINDOW:
        # Reset counter for new window
        login_attempts[ip_address] = {
            'count': 1,
            'first_attempt': now,
            'last_attempt': now
        }
        return True
    
    # Check if limit exceeded
    if attempt_data['count'] >= OAUTH_MAX_LOGIN_ATTEMPTS:
        logger.warning(f"Rate limit exceeded for IP: {ip_address}")
        return False
    
    # Increment counter
    attempt_data['count'] += 1
    attempt_data['last_attempt'] = now
    
    return True

def cleanup_rate_limit_data(now: datetime) -> None:
    """Clean up old rate limit data"""
    expired_ips = []
    
    for ip, data in login_attempts.items():
        if (now - data['last_attempt']).total_seconds() > OAUTH_RATE_LIMIT_WINDOW * 2:
            expired_ips.append(ip)
    
    for ip in expired_ips:
        del login_attempts[ip]

def get_client_ip(request) -> str:
    """Extract client IP address from request"""
    # Check for forwarded IP first (behind proxy/load balancer)
    forwarded_for = request.headers.get('X-Forwarded-For')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    
    # Check other common headers
    real_ip = request.headers.get('X-Real-IP')
    if real_ip:
        return real_ip.strip()
    
    # Fall back to direct client IP
    return request.client.host if request.client else '127.0.0.1'

def log_security_event(event_type: str, details: Dict, severity: str = "INFO") -> None:
    """
    Log security-related events for monitoring
    
    Args:
        event_type: Type of security event
        details: Event details
        severity: Log severity level
    """
    log_message = f"SECURITY_EVENT: {event_type} - {details}"
    
    if severity == "WARNING":
        logger.warning(log_message)
    elif severity == "ERROR":
        logger.error(log_message)
    else:
        logger.info(log_message)

def validate_oauth_state(state_param: str, session_state: str) -> bool:
    """
    Validate OAuth state parameter to prevent CSRF attacks
    
    Args:
        state_param: State parameter from OAuth callback
        session_state: State stored in session
        
    Returns:
        True if state is valid, False otherwise
    """
    if not state_param or not session_state:
        return False
    
    return state_param == session_state

def enhance_user_data_security(user_data: Dict) -> Dict:
    """
    Enhance user data with security-related fields
    
    Args:
        user_data: Original user data from OAuth
        
    Returns:
        Enhanced user data with security fields
    """
    enhanced_data = user_data.copy()
    
    # Add security metadata
    enhanced_data.update({
        'email_verified_at': datetime.now(timezone.utc).isoformat(),
        'oauth_provider': 'google',
        'security_flags': {
            'email_verified': user_data.get('email_verified', False),
            'disposable_email_check': not is_disposable_email(user_data.get('email', '')),
            'domain_allowed': is_allowed_domain(user_data.get('email', ''))
        }
    })
    
    return enhanced_data