"""
NyayaDesk Security Tests - Sessions, Authentication Hardening, Rate Limiting & HTTP Headers
Verifies cookie security attributes, session fixation defense, logout invalidation,
brute-force rate limiting (5 attempts = 1 min lock), password hashing, and HTTP security headers.
"""

import time
import pytest
from app.models import db, User
from app.auth import FAILED_LOGIN_ATTEMPTS
from tests.conftest import get_csrf

def test_session_cookie_security_flags(app):
    """Verify session cookie flags: HttpOnly=True, SameSite=Lax, and proper timeout."""
    assert app.config.get('SESSION_COOKIE_HTTPONLY') is True
    assert app.config.get('SESSION_COOKIE_SAMESITE') in ['Lax', 'Strict']
    lifetime = app.config.get('PERMANENT_SESSION_LIFETIME')
    assert lifetime is not None
    assert lifetime.total_seconds() <= 3600 # 60 minutes max session timeout


def test_session_fixation_and_logout_invalidation(app, client):
    """Verify CSRF token is regenerated on login and session is cleared upon logout."""
    # Pre-login token
    token1 = get_csrf(client)

    # Login
    res_login = client.post('/auth/login', json={
        'email': 'lawyer1@nyaya.in',
        'password': 'Lawyer@12345'
    }, headers={'X-CSRFToken': token1})
    assert res_login.status_code == 200

    # Token must be refreshed upon login to prevent session fixation
    with client.session_transaction() as sess:
        token2 = sess.get('_csrf_token')
        assert sess.get('user_id') is not None
    assert token2 != token1, "CSRF token was not regenerated on login (Session Fixation Risk)"

    # Logout
    res_logout = client.get('/auth/logout', follow_redirects=False)
    assert res_logout.status_code in [302, 200]

    # Session user_id must be cleared
    with client.session_transaction() as sess:
        assert sess.get('user_id') is None

    # Subsequent access to protected dashboard must be denied (redirected)
    res_dash = client.get('/dashboards/lawyer')
    assert res_dash.status_code in [302, 401]


def test_login_rate_limiting_lockout(client):
    """Assert 5 failed login attempts trigger a 1-minute lockout with HTTP 429."""
    # Clear prior failed attempt counters for clean test
    FAILED_LOGIN_ATTEMPTS.clear()

    target_email = 'target_lockout@nyaya.in'
    token = get_csrf(client)

    # 4 Failed attempts -> 401
    for attempt in range(4):
        res = client.post('/auth/login', json={
            'email': target_email,
            'password': 'WrongPassword123'
        }, headers={'X-CSRFToken': token})
        assert res.status_code == 401, f"Attempt {attempt + 1} expected 401, got {res.status_code}"

    # 5th Attempt -> Lockout HTTP 429
    res5 = client.post('/auth/login', json={
        'email': target_email,
        'password': 'WrongPassword123'
    }, headers={'X-CSRFToken': token})
    assert res5.status_code == 429, f"5th failed attempt should trigger 429 lockout, got {res5.status_code}"
    assert b"Too many failed login attempts" in res5.data or b"locked" in res5.data.lower()

    # Even with correct password, account remains locked during the 1-minute penalty
    res_locked = client.post('/auth/login', json={
        'email': target_email,
        'password': 'CorrectPassword@123'
    }, headers={'X-CSRFToken': token})
    assert res_locked.status_code == 429

    # Clean up counters after test
    FAILED_LOGIN_ATTEMPTS.clear()


def test_password_hashing_algorithm(app):
    """Verify modern password hashing algorithm is enforced (no plaintext, using scrypt or pbkdf2)."""
    with app.app_context():
        u = User.query.first()
        assert u.password_hash is not None
        assert not u.password_hash.startswith("Password")
        assert u.password_hash.startswith("scrypt:") or u.password_hash.startswith("pbkdf2:sha256:")


def test_security_headers_present_on_all_responses(client):
    """
    Verify vital defense-in-depth security headers are present on responses:
    - Content-Security-Policy
    - X-Frame-Options: DENY
    - X-Content-Type-Options: nosniff
    - Referrer-Policy: strict-origin-when-cross-origin
    """
    res = client.get('/')
    assert res.status_code == 200

    headers = res.headers
    assert headers.get('X-Frame-Options') == 'DENY'
    assert headers.get('X-Content-Type-Options') == 'nosniff'
    assert headers.get('Referrer-Policy') == 'strict-origin-when-cross-origin'
    assert 'Content-Security-Policy' in headers
    csp = headers.get('Content-Security-Policy')
    assert "default-src" in csp


def test_error_pages_do_not_leak_stack_traces(client):
    """Assert 404 and error responses do not leak Python stack traces or environment secrets."""
    res = client.get('/non-existent-route-for-404-test-9999')
    assert res.status_code == 404
    html = res.data.decode('utf-8', errors='ignore')
    assert "Traceback (most recent call last)" not in html
    assert "SECRET_KEY" not in html
