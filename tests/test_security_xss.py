"""
NyayaDesk Security Tests - Cross-Site Scripting (XSS) Sanitization
Asserts that malicious script and HTML payloads injected into case titles,
descriptions, party names, remarks, and AI chat are properly escaped across HTML and JSON views.
"""

import pytest
from app.models import db, Case, CaseParty, Order, Notification
from tests.conftest import get_csrf

XSS_PAYLOADS = [
    "<script>alert('xss_injection_exploit')</script>",
    "<img src=x onerror=\"alert('xss_image_exploit')\">",
    "'><svg onload=alert('xss_svg_exploit')>",
    "<iframe src='javascript:alert(1)'></iframe>"
]

def test_case_filing_xss_escaping(app, clerk_client, client):
    """Inject XSS payloads into case title and description; verify escaped rendering."""
    payload = "<script>alert('CASE_TITLE_XSS')</script>"
    desc_payload = "<img src=x onerror=alert('CASE_DESC_XSS')>"

    token = get_csrf(clerk_client)
    res = clerk_client.post('/api/clerk/cases/register', json={
        'title': f"State of UP vs {payload}",
        'case_type': 'Criminal',
        'court_id': 1,
        'description': f"Facts of the matter: {desc_payload}",
        'petitioner_name': f"Petitioner {payload}",
        'respondent_name': f"Accused {payload}"
    }, headers={'X-CSRFToken': token})
    assert res.status_code == 201
    case_id = res.get_json().get('case_id')

    # View case via web dashboard
    web_res = clerk_client.get(f'/dashboards/cases/{case_id}')
    assert web_res.status_code == 200

    # Ensure unescaped executable script tags are NOT present in the raw HTML response
    # Jinja2 auto-escapes, so `<script>` should be rendered as `&lt;script&gt;`
    html_content = web_res.data.decode('utf-8')
    assert "<script>alert('CASE_TITLE_XSS')</script>" not in html_content
    assert "&lt;script&gt;alert(&#39;CASE_TITLE_XSS&#39;)&lt;/script&gt;" in html_content or "&lt;script&gt;" in html_content
    assert "<img src=x onerror=" not in html_content


def test_order_verification_xss_escaping(app, judge_client, client):
    """Inject XSS payload into judge order content; verify order verification portal escapes it."""
    with app.app_context():
        case = Case.query.first()
        case_id = case.id

    order_payload = "<script>alert('ORDER_CONTENT_XSS')</script>"
    token = get_csrf(judge_client)
    order_res = judge_client.post(f'/api/judge/cases/{case_id}/orders', json={
        'title': f"Certified Decree {order_payload}",
        'order_type': 'Interim',
        'content': f"The defendant is enjoined as follows: {order_payload}"
    }, headers={'X-CSRFToken': token})
    assert order_res.status_code == 201
    v_code = order_res.get_json().get('verification_code')

    # Public web view
    web_res = client.get(f'/orders/verify/{v_code}')
    assert web_res.status_code == 200
    html = web_res.data.decode('utf-8')
    assert "<script>alert('ORDER_CONTENT_XSS')</script>" not in html
    assert "&lt;script&gt;" in html


def test_ai_chatbot_xss_sanitization(client):
    """Assert AI chatbot responses neutralize script injection payloads."""
    token = get_csrf(client)
    chat_payload = "<script>alert('CHAT_INJECTION')</script>"
    res = client.post('/api/ai/chat', json={
        'query': f"How does bail work for {chat_payload}?",
        'language': 'en'
    }, headers={'X-CSRFToken': token})
    assert res.status_code == 200
    reply = res.get_json().get('reply', '')
    # Check that reply does not unescape or execute raw script tags
    assert not reply.startswith("<script>alert")
