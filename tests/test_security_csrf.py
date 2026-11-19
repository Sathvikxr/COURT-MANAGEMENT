"""
NyayaDesk Security Tests - Cross-Site Request Forgery (CSRF) Hardening
Asserts that all state-changing endpoints (POST/PUT/DELETE/PATCH) strictly
reject requests without valid CSRF tokens with HTTP 403 Forbidden.
"""

import pytest
from tests.conftest import get_csrf

def test_csrf_missing_token_rejected_with_403(app, clerk_client, judge_client, litigant_client):
    """Verify state-changing POST requests without CSRF token are blocked with 403."""
    # 1. Clerk case register without CSRF
    res1 = clerk_client.post('/api/clerk/cases/register', json={
        'title': 'CSRF Attack Test Case',
        'case_type': 'Civil',
        'court_id': 1,
        'petitioner_name': 'Hacker',
        'respondent_name': 'Target'
    })
    assert res1.status_code == 403
    assert b"CSRF token missing or invalid" in res1.data

    # 2. Judge order creation without CSRF
    res2 = judge_client.post('/api/judge/orders/create', json={
        'case_id': 1,
        'title': 'Forged Judicial Order',
        'content': 'This order was attempted via CSRF.'
    })
    assert res2.status_code == 403
    assert b"CSRF token missing or invalid" in res2.data

    # 3. Litigant payment creation without CSRF
    res3 = litigant_client.post('/api/payments/create', json={
        'case_id': 1,
        'amount': 99999.0
    })
    assert res3.status_code == 403
    assert b"CSRF token missing or invalid" in res3.data

    # 4. Notification mark read without CSRF
    res4 = litigant_client.post('/api/notifications/mark-read')
    assert res4.status_code == 403


def test_csrf_invalid_token_rejected_with_403(app, clerk_client):
    """Verify requests with forged or corrupted tokens are blocked with 403."""
    res = clerk_client.post(
        '/api/clerk/cases/register',
        json={'title': 'Forged Token Case', 'petitioner_name': 'Attacker', 'respondent_name': 'Defender'},
        headers={'X-CSRFToken': 'forged_fake_token_1234567890abcdef'}
    )
    assert res.status_code == 403
    assert b"CSRF token missing or invalid" in res.data


def test_csrf_valid_token_accepted(app, clerk_client):
    """Verify request with authentic CSRF token in header succeeds."""
    token = get_csrf(clerk_client)
    res = clerk_client.post(
        '/api/clerk/cases/register',
        json={
            'title': 'Legitimate CSRF-Verified Case',
            'case_type': 'Civil',
            'court_id': 1,
            'petitioner_name': 'Legit Petitioner',
            'respondent_name': 'Legit Respondent'
        },
        headers={'X-CSRFToken': token}
    )
    assert res.status_code == 201
    assert res.get_json().get('success') is True
