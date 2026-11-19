"""
NyayaDesk Functional Tests - Authentication & Role Approval Workflows
Covers role signups, approval queues, re-application, suspension, and password recovery.
"""

import io
import re
import pytest
from app.models import db, User, ApprovalRequest
from tests.conftest import get_csrf

def test_signup_roles_and_approval_states(app, client):
    """
    Assert signup status per role:
    - Judge & Registrar -> pending_gov
    - Clerk -> pending_registrar
    - Lawyer, Litigant, Police -> active
    """
    with app.app_context():
        court_id = db.session.execute(db.text("SELECT id FROM courts LIMIT 1")).scalar() or 1

    roles_and_expected_status = [
        ('judge', 'pending_gov', 'New Judge', 'newjudge@nyaya.in', '9811112201', 'JUD-APPT-901'),
        ('registrar', 'pending_gov', 'New Registrar', 'newreg@nyaya.in', '9811112202', 'REG-APPT-902'),
        ('clerk', 'pending_registrar', 'New Clerk', 'newclerk@nyaya.in', '9811112203', 'CLK-APPT-903'),
        ('lawyer', 'active', 'New Lawyer', 'newlawyer@nyaya.in', '9811112204', 'BAR-DEL-904'),
        ('litigant', 'active', 'New Litigant', 'newlitigant@nyaya.in', '9811112205', 'AADHAAR-905'),
        ('police', 'active', 'New Police Officer', 'newpolice@nyaya.in', '9811112206', 'POL-BADGE-906'),
    ]

    for role, expected_status, name, email, phone, id_proof_no in roles_and_expected_status:
        token = get_csrf(client)
        # Prepare multipart form with sample dummy PDF
        data = {
            'csrf_token': token,
            'role': role,
            'full_name': name,
            'email': email,
            'phone': phone,
            'password': 'SecurePassword@2026',
            'confirm_password': 'SecurePassword@2026',
            'designation': f'Official {role}',
            'employee_id': id_proof_no,
            'id_proof_no': id_proof_no,
            'bar_registration_no': id_proof_no,
            'badge_number': id_proof_no,
            'court_id': court_id,
            'city': 'New Delhi',
            'id_proof_file': (io.BytesIO(b'%PDF-1.4 test document'), 'id_doc.pdf')
        }
        res = client.post('/auth/register', data=data, content_type='multipart/form-data', follow_redirects=True)
        assert res.status_code == 200, f"Registration failed for role {role}: {res.data.decode('utf-8')}"

        with app.app_context():
            user = User.query.filter_by(email=email).first()
            assert user is not None, f"User {email} was not created in database"
            assert user.status == expected_status, f"Expected {expected_status} for {role}, got {user.status}"

            # Check ApprovalRequest created if pending
            if expected_status.startswith('pending_'):
                req = ApprovalRequest.query.filter_by(applicant_user_id=user.id).first()
                assert req is not None, f"ApprovalRequest missing for pending user {email}"
                assert req.status == 'Pending'


def test_signup_validation_errors(client):
    """Verify validation: password mismatch, weak password, duplicate email."""
    token = get_csrf(client)
    # Password mismatch
    res = client.post('/auth/register', data={
        'csrf_token': token,
        'role': 'litigant',
        'full_name': 'Mismatch Test',
        'email': 'mismatch@nyaya.in',
        'phone': '9899999999',
        'password': 'Password@123',
        'confirm_password': 'DifferentPassword@123',
    }, follow_redirects=True)
    assert b"Password" in res.data and b"match" in res.data

    # Weak password (< 8 chars)
    token = get_csrf(client)
    res = client.post('/auth/register', data={
        'csrf_token': token,
        'role': 'litigant',
        'full_name': 'Weak Pass Test',
        'email': 'weakpass@nyaya.in',
        'phone': '9899999998',
        'password': 'short',
        'confirm_password': 'short',
    }, follow_redirects=True)
    assert b"at least 8 characters" in res.data

    # Duplicate email
    token = get_csrf(client)
    res = client.post('/auth/register', data={
        'csrf_token': token,
        'role': 'litigant',
        'full_name': 'Duplicate Email',
        'email': 'litigant1@nyaya.in', # already seeded
        'phone': '9899999997',
        'password': 'Password@123',
        'confirm_password': 'Password@123',
    }, follow_redirects=True)
    assert b"already registered" in res.data


def test_approval_flow_government(app, gov_client, client):
    """Test government approval, rejection with remarks, and bulk approvals."""
    with app.app_context():
        # Find a pending user seeded for gov approval
        pending_judge = User.query.filter_by(email='judge_pending1@nyaya.in').first()
        assert pending_judge is not None
        req = ApprovalRequest.query.filter_by(applicant_user_id=pending_judge.id, status='Pending').first()
        assert req is not None
        req_id = req.id

    token = get_csrf(gov_client)
    # 1. Approve individual request
    res = gov_client.post(f'/api/gov/approvals/{req_id}/action', json={
        'action': 'approve'
    }, headers={'X-CSRFToken': token})
    assert res.status_code == 200
    assert res.get_json().get('success') is True

    with app.app_context():
        updated_user = db.session.get(User, pending_judge.id)
        assert updated_user.status == 'active'

    # 2. Rejection with remarks
    with app.app_context():
        pending_reg = User.query.filter_by(email='reg_pending@nyaya.in').first()
        req2 = ApprovalRequest.query.filter_by(applicant_user_id=pending_reg.id, status='Pending').first()
        req2_id = req2.id

    token = get_csrf(gov_client)
    res = gov_client.post(f'/api/gov/approvals/{req2_id}/action', json={
        'action': 'reject',
        'remarks': 'Official appointment notification gazette missing seal.'
    }, headers={'X-CSRFToken': token})
    assert res.status_code == 200

    with app.app_context():
        rejected_user = db.session.get(User, pending_reg.id)
        assert rejected_user.status == 'rejected'
        assert rejected_user.rejection_reason == 'Official appointment notification gazette missing seal.'

    # 3. Bulk Approve
    with app.app_context():
        pending_judge2 = User.query.filter_by(email='judge_pending2@nyaya.in').first()
        req3 = ApprovalRequest.query.filter_by(applicant_user_id=pending_judge2.id, status='Pending').first()
        req3_id = req3.id

    token = get_csrf(gov_client)
    res = gov_client.post('/api/gov/approvals/bulk-approve', json={
        'request_ids': [req3_id]
    }, headers={'X-CSRFToken': token})
    assert res.status_code == 200
    assert res.get_json().get('approved_count') >= 1

    with app.app_context():
        assert db.session.get(User, pending_judge2.id).status == 'active'


def test_reapply_after_rejection(app, client):
    """Test that a rejected user can log in, view remarks, and submit re-application."""
    with app.app_context():
        # Ensure user is in rejected state
        user = User.query.filter_by(email='reg_pending@nyaya.in').first()
        user.status = 'rejected'
        user.rejection_reason = 'Official appointment notification gazette missing seal.'
        db.session.commit()

    # Login as rejected user
    token = get_csrf(client)
    res = client.post('/auth/login', json={
        'email': 'reg_pending@nyaya.in',
        'password': 'Reg@12345'
    }, headers={'X-CSRFToken': token})
    assert res.status_code == 200
    assert '/auth/pending-approval' in res.get_json().get('redirect_url')

    # View pending approval / rejection page
    page_res = client.get('/auth/pending-approval')
    assert page_res.status_code == 200
    assert b"Official appointment notification gazette missing seal." in page_res.data

    # Submit Re-apply
    token = get_csrf(client)
    reapply_res = client.post('/auth/reapply', data={'csrf_token': token}, follow_redirects=True)
    assert reapply_res.status_code == 200

    with app.app_context():
        user = User.query.filter_by(email='reg_pending@nyaya.in').first()
        assert user.status == 'pending_gov'


def test_suspended_account_login(app, client):
    """Assert login is blocked with 403 for suspended users."""
    with app.app_context():
        suspended = User(
            email='suspended@nyaya.in',
            phone='9819999999',
            full_name='Suspended Personnel',
            role='clerk',
            status='suspended',
            designation='Clerk Under Inquiry'
        )
        suspended.set_password('Pass@12345')
        db.session.add(suspended)
        db.session.commit()

    token = get_csrf(client)
    res = client.post('/auth/login', json={
        'email': 'suspended@nyaya.in',
        'password': 'Pass@12345'
    }, headers={'X-CSRFToken': token})
    assert res.status_code == 403
    assert b"suspended" in res.data.lower()


def test_forgot_password_and_otp_reset(app, client):
    """Test OTP dispatch, verification, and password reset flow."""
    token = get_csrf(client)
    # Step 1: Request OTP
    res = client.post('/auth/forgot-password', data={
        'csrf_token': token,
        'action': 'request_otp',
        'email': 'lawyer2@nyaya.in'
    })
    assert res.status_code == 200
    assert b"Simulated SMS Gateway" in res.data

    with client.session_transaction() as sess:
        otp = sess.get('reset_otp')
    assert otp is not None, "reset_otp missing from session"

    # Step 2: Verify OTP and reset password
    token = get_csrf(client)
    res2 = client.post('/auth/forgot-password', data={
        'csrf_token': token,
        'action': 'verify_and_reset',
        'otp': otp,
        'new_password': 'BrandNewPassword@2026',
        'confirm_password': 'BrandNewPassword@2026'
    }, follow_redirects=True)
    assert res2.status_code == 200
    assert b"Password updated successfully" in res2.data

    # Step 3: Login with new password
    token = get_csrf(client)
    login_res = client.post('/auth/login', json={
        'email': 'lawyer2@nyaya.in',
        'password': 'BrandNewPassword@2026'
    }, headers={'X-CSRFToken': token})
    assert login_res.status_code == 200
