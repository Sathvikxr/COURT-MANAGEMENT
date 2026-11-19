"""
NyayaDesk Functional Tests - Case Lifecycle, Scrutiny, Scheduling, Orders & QR Verification
Covers complete judicial pipeline from registration to disposal and certified QR checks.
"""

import io
from datetime import datetime, timedelta, date
import pytest
from app.models import db, Case, Hearing, Order, Document, Payment, Courtroom, User
from tests.conftest import get_csrf

def test_case_registration_and_scrutiny(app, lawyer_client, reg_client):
    """Test case registration via lawyer e-filing and subsequent scrutiny by registrar."""
    token = get_csrf(lawyer_client)
    res = lawyer_client.post('/api/lawyer/efiling', json={
        'title': 'Union of India vs Horizon Infrastructure Ltd',
        'case_type': 'Civil',
        'court_id': 1,
        'description': 'Dispute regarding highway concession contract arbitration clause.',
        'petitioner_name': 'Union of India (NHAI)',
        'respondent_name': 'Horizon Infrastructure Ltd'
    }, headers={'X-CSRFToken': token})
    assert res.status_code == 201
    data = res.get_json()
    assert data.get('success') is True
    case_id = data.get('case_id')
    assert case_id is not None
    case_number = data.get('case_number')
    assert case_number.startswith('CIV/') or case_number.startswith('CASE/')

    with app.app_context():
        c = db.session.get(Case, case_id)
        assert c.status == 'Scrutiny'

    # Registrar Scrutiny - Defect action
    token = get_csrf(reg_client)
    defect_res = reg_client.post(f'/api/registrar/scrutiny/{case_id}/action', json={
        'action': 'defect',
        'defect_notes': 'Vakalatnama not signed by authorized representative.'
    }, headers={'X-CSRFToken': token})
    assert defect_res.status_code == 200

    with app.app_context():
        c = db.session.get(Case, case_id)
        assert c.status == 'Defective'

    # Registrar Scrutiny - Cleared action
    token = get_csrf(reg_client)
    clear_res = reg_client.post(f'/api/registrar/scrutiny/{case_id}/action', json={
        'action': 'pass'
    }, headers={'X-CSRFToken': token})
    assert clear_res.status_code == 200

    with app.app_context():
        c = db.session.get(Case, case_id)
        assert c.status == 'Scrutiny Passed'


def test_bench_allocation_and_hearing_scheduling(app, reg_client, clerk_client):
    """Test bench allocation to judge and hearing scheduling with conflict checks."""
    with app.app_context():
        case = Case.query.filter_by(status='Scrutiny Passed').first()
        if not case:
            case = Case.query.first()
        case_id = case.id
        judge = User.query.filter_by(role='judge', status='active').first()
        judge_id = judge.id
        courtroom = Courtroom.query.filter_by(court_id=case.court_id).first()
        courtroom_id = courtroom.id

    # 1. Assign Judge
    token = get_csrf(reg_client)
    assign_res = reg_client.post(f'/api/registrar/cases/{case_id}/assign', json={
        'judge_id': judge_id
    }, headers={'X-CSRFToken': token})
    assert assign_res.status_code == 200

    with app.app_context():
        c = db.session.get(Case, case_id)
        assert c.judge_id == judge_id

    # 2. Schedule Hearing (Ensure on future business day: Monday at 11:00 AM)
    today = date.today()
    days_ahead = (7 - today.weekday()) % 7 # Next Monday
    if days_ahead == 0:
        days_ahead = 7
    target_date = today + timedelta(days=days_ahead)
    sched_dt = datetime.combine(target_date, datetime.min.time()).replace(hour=11, minute=0)
    sched_str = sched_dt.strftime('%Y-%m-%dT%H:%M')

    token = get_csrf(clerk_client)
    sched_res = clerk_client.post('/api/clerk/hearings/schedule', json={
        'case_id': case_id,
        'courtroom_id': courtroom_id,
        'scheduled_at': sched_str,
        'purpose': 'Admission & Interim Relief Hearing'
    }, headers={'X-CSRFToken': token})
    assert sched_res.status_code == 200
    hearing_id = sched_res.get_json().get('hearing_id')
    assert hearing_id is not None

    with app.app_context():
        c = db.session.get(Case, case_id)
        assert c.status == 'Hearing Scheduled'

    # 3. Conflict Detection: Same Judge within 30 minutes
    # Attempt to schedule another case with the SAME judge at 11:15 AM (15 min overlap)
    with app.app_context():
        case2 = Case.query.filter(Case.id != case_id).first()
        case2_id = case2.id
        other_cr = Courtroom.query.filter(Courtroom.id != courtroom_id).first()
        other_cr_id = other_cr.id

    overlap_dt = (sched_dt + timedelta(minutes=15)).strftime('%Y-%m-%dT%H:%M')
    token = get_csrf(clerk_client)
    conflict1 = clerk_client.post('/api/clerk/hearings/schedule', json={
        'case_id': case2_id,
        'courtroom_id': other_cr_id,
        'scheduled_at': overlap_dt,
        'purpose': 'Conflicting Hearing'
    }, headers={'X-CSRFToken': token})
    assert conflict1.status_code == 409
    assert b"Judge" in conflict1.data

    # 4. Conflict Detection: Same Courtroom within 30 minutes
    with app.app_context():
        judge2 = User.query.filter(User.role == 'judge', User.id != judge_id).first()
        if not judge2:
            judge2 = judge
        case3 = Case.query.filter(Case.id != case_id, Case.id != case2_id).first()
        case3_id = case3.id

    token = get_csrf(clerk_client)
    conflict2 = clerk_client.post('/api/clerk/hearings/schedule', json={
        'case_id': case3_id,
        'courtroom_id': courtroom_id,
        'scheduled_at': overlap_dt,
        'purpose': 'Courtroom Conflict'
    }, headers={'X-CSRFToken': token})
    assert conflict2.status_code == 409
    assert b"Courtroom" in conflict2.data

    # 5. Conflict Detection: Sunday / Court Holiday
    # Schedule on next Sunday
    sunday_dt = datetime.combine(target_date + timedelta(days=6), datetime.min.time()).replace(hour=11, minute=0)
    sunday_str = sunday_dt.strftime('%Y-%m-%dT%H:%M')
    token = get_csrf(clerk_client)
    sun_res = clerk_client.post('/api/clerk/hearings/schedule', json={
        'case_id': case2_id,
        'courtroom_id': other_cr_id,
        'scheduled_at': sunday_str,
        'purpose': 'Sunday Hearing'
    }, headers={'X-CSRFToken': token})
    assert sun_res.status_code in [400, 409]
    assert b"Sunday" in sun_res.data


def test_adjournment_orders_disposal_and_qr(app, judge_client, client):
    """Test adjournment, order pronouncement, case disposal, and QR verification."""
    with app.app_context():
        hearing = Hearing.query.filter_by(status='Scheduled').first()
        assert hearing is not None
        hearing_id = hearing.id
        case_id = hearing.case_id

    # 1. Adjourn Hearing
    next_date = (date.today() + timedelta(days=14)).strftime('%Y-%m-%d')
    token = get_csrf(judge_client)
    adj_res = judge_client.post(f'/api/judge/hearings/{hearing_id}/adjourn', json={
        'adjourn_reason': 'Counsel for respondent requests additional time to file counter affidavit.',
        'next_date': next_date
    }, headers={'X-CSRFToken': token})
    assert adj_res.status_code == 200

    with app.app_context():
        h = db.session.get(Hearing, hearing_id)
        assert h.status == 'Adjourned'
        c = db.session.get(Case, case_id)
        assert c.status == 'Adjourned'

    # 2. Issue Interim Order
    token = get_csrf(judge_client)
    order_res = judge_client.post(f'/api/judge/cases/{case_id}/orders', json={
        'title': 'Interim Injunction Order',
        'order_type': 'Interim',
        'content': 'Status quo shall be maintained by all parties until the next date of hearing.'
    }, headers={'X-CSRFToken': token})
    assert order_res.status_code == 201
    order_data = order_res.get_json()
    assert order_data.get('order_id') is not None
    v_code = order_data.get('verification_code')
    assert v_code is not None

    # 3. QR Order Verification (API and Public Portal)
    api_verify = client.get(f'/api/orders/verify/{v_code}')
    assert api_verify.status_code == 200
    assert api_verify.get_json().get('valid') is True
    assert api_verify.get_json().get('title') == 'Interim Injunction Order'

    web_verify = client.get(f'/orders/verify/{v_code}')
    assert web_verify.status_code == 200
    assert b"Digitally Certified Judicial Order" in web_verify.data

    # 4. Issue Judgment -> Status becomes Disposed
    token = get_csrf(judge_client)
    disp_res = judge_client.post(f'/api/judge/cases/{case_id}/orders', json={
        'title': 'Final Judgment and Decree',
        'order_type': 'Judgment',
        'content': 'The petition is allowed with costs. Arbitral award stands confirmed.'
    }, headers={'X-CSRFToken': token})
    assert disp_res.status_code == 201

    with app.app_context():
        c = db.session.get(Case, case_id)
        assert c.status == 'Disposed'


def test_document_upload_and_versioning(app, clerk_client):
    """Test document upload and automatic version incrementing."""
    with app.app_context():
        case = Case.query.first()
        case_id = case.id

    token = get_csrf(clerk_client)
    # Upload version 1
    doc1 = (io.BytesIO(b'%PDF-1.4 Initial Petition draft'), 'petition_v1.pdf')
    res1 = clerk_client.post(f'/api/cases/{case_id}/documents', data={
        'csrf_token': token,
        'doc_type': 'Petition',
        'file': doc1
    }, content_type='multipart/form-data')
    assert res1.status_code == 201
    v1 = res1.get_json().get('version')

    # Upload version 2 (same doc_type on same case)
    token = get_csrf(clerk_client)
    doc2 = (io.BytesIO(b'%PDF-1.4 Amended Petition draft'), 'petition_v2.pdf')
    res2 = clerk_client.post(f'/api/cases/{case_id}/documents', data={
        'csrf_token': token,
        'doc_type': 'Petition',
        'file': doc2
    }, content_type='multipart/form-data')
    assert res2.status_code == 201
    v2 = res2.get_json().get('version')

    assert v2 == v1 + 1


def test_litigant_payment_receipt(app, litigant_client):
    """Test litigant statutory fee payment and receipt generation."""
    with app.app_context():
        case = Case.query.first()
        case_id = case.id

    token = get_csrf(litigant_client)
    res = litigant_client.post('/api/payments/create', json={
        'case_id': case_id,
        'amount': 2500.0,
        'payment_type': 'Court Fee'
    }, headers={'X-CSRFToken': token})
    assert res.status_code == 201
    data = res.get_json()
    assert data.get('success') is True
    assert data.get('status') == 'Success'
    assert data.get('payment_reference').startswith('PAY-')
