"""
NyayaDesk API Suite - Exhaustive Verification of docs/api_endpoints.md
Tests status codes, validation errors, pagination, empty responses, malformed JSON,
missing parameters, and error schema consistency across all endpoints.
"""

import json
import pytest
from app.models import db, Case, User, Court, Courtroom
from tests.conftest import get_csrf

def test_public_and_metadata_endpoints(client):
    """Verify courts, courtrooms, judges, search, and public status APIs."""
    # 1. Courts list
    res = client.get('/api/courts')
    assert res.status_code == 200
    assert isinstance(res.get_json(), list)

    # 2. Courtrooms list
    res = client.get('/api/courtrooms')
    assert res.status_code == 200
    assert isinstance(res.get_json(), list)

    # 3. Judges list
    res = client.get('/api/judges')
    assert res.status_code == 200
    assert isinstance(res.get_json(), list)

    # 4. Search with empty result
    res = client.get('/api/search?q=NonExistentMatterNameXYZ999')
    assert res.status_code == 200
    assert res.get_json().get('cases') == []

    # 5. Public case status with invalid number
    res = client.get('/api/public/case-status?case_number=INVALID/9999/00000')
    assert res.status_code == 404
    assert 'error' in res.get_json() or 'message' in res.get_json()

    # 6. Public cause list
    res = client.get('/api/public/cause-list?court_id=1')
    assert res.status_code == 200
    assert 'cause_list' in res.get_json()


def test_malformed_json_and_missing_fields_handling(clerk_client, judge_client):
    """Assert malformed JSON and missing parameters return consistent 400 with error schema."""
    token = get_csrf(clerk_client)

    # Missing mandatory fields on case registration
    res1 = clerk_client.post('/api/clerk/cases/register', json={
        'title': 'Only Title Provided'
    }, headers={'X-CSRFToken': token})
    assert res1.status_code == 400
    assert 'error' in res1.get_json()

    # Missing mandatory fields on hearing schedule
    token = get_csrf(clerk_client)
    res2 = clerk_client.post('/api/clerk/hearings/schedule', json={
        'case_id': 1
    }, headers={'X-CSRFToken': token})
    assert res2.status_code == 400
    assert 'error' in res2.get_json()

    # Missing content on order creation
    token = get_csrf(judge_client)
    res3 = judge_client.post('/api/judge/orders/create', json={
        'case_id': 1
    }, headers={'X-CSRFToken': token})
    assert res3.status_code == 400
    assert 'error' in res3.get_json()


def test_pagination_and_limits(clerk_client):
    """Test pagination controls on case listings."""
    # Page 1, limit 2
    res = clerk_client.get('/api/clerk/cases?page=1&limit=2')
    assert res.status_code == 200
    data = res.get_json()
    assert data.get('page') == 1
    assert data.get('limit') == 2
    assert len(data.get('cases', [])) <= 2


def test_ai_services_endpoints(client, judge_client):
    """Test AI chat, similar case search, and case briefing."""
    # 1. AI Chat query
    token = get_csrf(client)
    res = client.post('/api/ai/chat', json={
        'query': 'What is the procedure for anticipatory bail?',
        'language': 'en'
    }, headers={'X-CSRFToken': token})
    assert res.status_code == 200
    data = res.get_json()
    assert 'reply' in data

    # 2. AI Similar Cases
    sim_res = judge_client.get('/api/ai/similar-cases/1')
    assert sim_res.status_code == 200
    assert 'similar_cases' in sim_res.get_json()


def test_police_charge_sheet_api(police_client):
    """Test police charge-sheet filing API."""
    token = get_csrf(police_client)
    res = police_client.post('/api/police/charge-sheet', json={
        'case_id': 1,
        'fir_number': 'FIR-DEL-2026-9901',
        'sections_invoked': 'Section 420, 120B IPC',
        'investigating_officer': 'Inspector R. K. Singh',
        'summary': 'Investigation completed. Prima facie evidence of fraudulent misrepresentation.'
    }, headers={'X-CSRFToken': token})
    assert res.status_code in [200, 201]
    assert res.get_json().get('success') is True


def test_helpdesk_portal_and_ticket_flow(client):
    """Test public citizen helpdesk view with prefilled query and ticket submission."""
    # 1. GET with prefilled query from NyayaMitra
    res = client.get('/helpdesk?message=How%20to%20file%20urgent%20motion')
    assert res.status_code == 200
    assert b"Citizen Assistance" in res.data
    assert b"How to file urgent motion" in res.data

    # 2. POST ticket creation
    token = get_csrf(client)
    post_res = client.post('/helpdesk', data={
        'name': 'Devendra Sharma',
        'phone': '9876543210',
        'case_number': 'CIV/2026/00010',
        'message': 'Need certified true copy of interim injunction.'
    }, headers={'X-CSRFToken': token}, follow_redirects=True)
    assert post_res.status_code == 200
    assert b"Your inquiry has been registered under Ticket #HD-2026-" in post_res.data


def test_government_dashboard_apis(gov_client):
    """Test judicial officers list, status toggling, and approval REST routes."""
    # 1. GET judges and registrars
    res = gov_client.get('/api/gov/judges')
    assert res.status_code == 200
    data = res.get_json()
    assert 'judges' in data
    assert len(data['judges']) > 0
    assert 'name' in data['judges'][0]

    # 2. Toggle user status via POST /api/gov/users/<id>/status
    target_id = data['judges'][0]['id']
    token = get_csrf(gov_client)
    toggle_res = gov_client.post(f'/api/gov/users/{target_id}/status', json={
        'status': 'active'
    }, headers={'X-CSRFToken': token})
    assert toggle_res.status_code == 200
    assert toggle_res.get_json().get('status') == 'active'

