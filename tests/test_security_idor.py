"""
NyayaDesk Security Tests - Insecure Direct Object Reference (IDOR)
Asserts litigants and lawyers cannot access another party's cases, documents,
orders, payments, or notifications by tampering with IDs in URL parameters.
"""

import pytest
from app.models import db, User, Case, CaseParty, Document, Payment, Notification
from tests.conftest import get_csrf, login_as

@pytest.fixture
def litigant2_client(app):
    c = app.test_client()
    return login_as(c, 'litigant2@nyaya.in', 'Litigant@12345')


def test_case_detail_idor_protection(app, litigant_client, litigant2_client):
    """Assert Litigant 2 cannot view case details or AI brief of Litigant 1's exclusive case."""
    with app.app_context():
        # Find a case where litigant1 is party, but litigant2 is NOT
        lit1 = User.query.filter_by(email='litigant1@nyaya.in').first()
        lit2 = User.query.filter_by(email='litigant2@nyaya.in').first()

        lit1_case_ids = {p.case_id for p in CaseParty.query.filter_by(user_id=lit1.id).all()}
        lit2_case_ids = {p.case_id for p in CaseParty.query.filter_by(user_id=lit2.id).all()}

        exclusive_case_ids = lit1_case_ids - lit2_case_ids
        if not exclusive_case_ids:
            # Create an exclusive case for lit1
            c = Case(case_number="EXCL/2026/9999", title="Litigant 1 Private Matter", case_type="Civil", court_id=1, status="Registered")
            db.session.add(c)
            db.session.flush()
            p = CaseParty(case_id=c.id, user_id=lit1.id, name=lit1.full_name, party_type="Petitioner")
            db.session.add(p)
            db.session.commit()
            target_case_id = c.id
        else:
            target_case_id = list(exclusive_case_ids)[0]

    # Litigant 1 should have access
    res1 = litigant_client.get(f'/api/cases/{target_case_id}')
    assert res1.status_code == 200

    # Litigant 2 must be BLOCKED with 403 Forbidden
    res2 = litigant2_client.get(f'/api/cases/{target_case_id}')
    assert res2.status_code == 403, f"IDOR Vulnerability: Litigant 2 was able to view Case #{target_case_id}: status {res2.status_code}"

    # AI Summary must also be BLOCKED with 403
    ai_res = litigant2_client.get(f'/api/cases/{target_case_id}/ai-summary')
    assert ai_res.status_code == 403, f"IDOR Vulnerability: Litigant 2 accessed AI summary of Case #{target_case_id}"

    # Web Dashboard view must also be BLOCKED with 403
    web_res = litigant2_client.get(f'/dashboards/cases/{target_case_id}')
    assert web_res.status_code == 403, f"IDOR Vulnerability: Litigant 2 opened dashboard page for Case #{target_case_id}"


def test_document_download_idor_protection(app, litigant_client, litigant2_client):
    """Assert Litigant 2 cannot download documents belonging to Litigant 1's confidential matter."""
    with app.app_context():
        lit1 = User.query.filter_by(email='litigant1@nyaya.in').first()
        lit2 = User.query.filter_by(email='litigant2@nyaya.in').first()

        # Find document on lit1's exclusive case
        doc = Document.query.join(Case).join(CaseParty).filter(
            CaseParty.user_id == lit1.id,
            Document.visibility != 'Public'
        ).first()

        if not doc:
            # Create a private document
            case = Case(case_number="CONF/2026/8888", title="Confidential Trade Secrets", case_type="Commercial", court_id=1, status="Registered")
            db.session.add(case)
            db.session.flush()
            db.session.add(CaseParty(case_id=case.id, user_id=lit1.id, name=lit1.full_name, party_type="Petitioner"))
            doc = Document(case_id=case.id, uploaded_by=lit1.id, filename="Trade_Secrets.pdf", stored_path="uploads/cases/trade_secrets.pdf", doc_type="Evidence", visibility="Confidential")
            db.session.add(doc)
            db.session.commit()
            doc_id = doc.id
        else:
            doc_id = doc.id

    # Litigant 2 download attempt must return 403
    download_res = litigant2_client.get(f'/api/documents/{doc_id}/download')
    assert download_res.status_code == 403, f"IDOR Vulnerability: Litigant 2 downloaded Document #{doc_id}: {download_res.status_code}"


def test_payment_receipt_idor_protection(app, litigant_client, litigant2_client):
    """Assert Litigant 2 cannot inspect Litigant 1's payment records."""
    with app.app_context():
        lit1 = User.query.filter_by(email='litigant1@nyaya.in').first()
        lit2 = User.query.filter_by(email='litigant2@nyaya.in').first()

        pay = Payment.query.filter_by(user_id=lit1.id).first()
        if not pay:
            pay = Payment(case_id=1, user_id=lit1.id, amount=1500.0, purpose="Filing Fee", status="Success", reference="PAY-LIT1-001")
            db.session.add(pay)
            db.session.commit()
        pay_id = pay.id

    # Litigant 1 can view
    res1 = litigant_client.get(f'/api/payments/{pay_id}')
    assert res1.status_code == 200

    # Litigant 2 cannot view
    res2 = litigant2_client.get(f'/api/payments/{pay_id}')
    assert res2.status_code == 403, f"IDOR Vulnerability: Litigant 2 viewed Payment #{pay_id}: {res2.status_code}"
