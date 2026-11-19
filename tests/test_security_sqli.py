"""
NyayaDesk Security Tests - SQL Injection (SQLi) Defense
Asserts that search, filter, and authentication parameters safely use parameterized
ORM queries and reject/neutralize classic SQL injection strings without syntax errors or data loss.
"""

import pytest
from app.models import db, User, Case
from tests.conftest import get_csrf

SQLI_PAYLOADS = [
    "' OR '1'='1",
    "' OR 1=1 --",
    "admin' --",
    "'; DROP TABLE audit_logs; --",
    "' UNION SELECT id, email, password_hash, role, status FROM users --",
    "1' ORDER BY 1,2,3--",
    "\" OR \"\"=\"",
    "1' AND SLEEP(5) --"
]

def test_search_endpoint_sqli_resilience(client):
    """Verify global search query parameter is impervious to SQL injection."""
    for payload in SQLI_PAYLOADS:
        res = client.get(f'/api/search?q={payload}')
        assert res.status_code == 200, f"Search failed with status {res.status_code} on payload: {payload}"
        data = res.get_json()
        assert 'cases' in data
        assert isinstance(data['cases'], list)


def test_destructive_sqli_does_not_drop_tables(app, client):
    """Assert that injection attempting table drops leaves schema completely intact."""
    drop_payload = "'; DROP TABLE users; --"
    res = client.get(f'/api/search?q={drop_payload}')
    assert res.status_code == 200

    with app.app_context():
        # Assert users table exists and still holds users
        assert User.query.count() > 0


def test_auth_login_sqli_authentication_bypass_fails(client):
    """Assert SQL injection in login email field fails to bypass authentication."""
    bypass_payload = "' OR '1'='1"
    token = get_csrf(client)
    res = client.post('/auth/login', json={
        'email': bypass_payload,
        'password': 'AnyPassword123'
    }, headers={'X-CSRFToken': token})
    assert res.status_code in [401, 404]
    assert res.get_json().get('success') is not True


def test_cause_list_and_filter_sqli_resilience(client, clerk_client):
    """Assert filter parameters in cause list and case listings safely neutralize SQLi."""
    for payload in ["1' OR 1=1 --", "'; DELETE FROM cases; --"]:
        res = client.get(f'/api/public/cause-list?court_id={payload}')
        assert res.status_code in [200, 400]

        res_clerk = clerk_client.get(f'/api/clerk/cases?status={payload}')
        assert res_clerk.status_code == 200
