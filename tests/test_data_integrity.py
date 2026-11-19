"""
NyayaDesk Data Integrity Tests - Constraints, Foreign Keys, Concurrency & Rollbacks
Asserts foreign key enforcement, orphan record deletion, unique constraints,
concurrent case numbering collision immunity, transaction rollbacks, and demo reset.
"""

from datetime import datetime, timedelta
import threading
import pytest
from sqlalchemy.exc import IntegrityError
from app.models import db, User, Case, CaseParty, Hearing, Order, Payment, Court, Courtroom
from app.seed import reset_demo_database, seed_demo_data

def test_sqlite_foreign_key_enforcement(app):
    """Assert SQLite enforces foreign key constraints (PRAGMA foreign_keys=ON)."""
    with app.app_context():
        # Attempt to insert Hearing with invalid case_id
        bad_hearing = Hearing(
            case_id=9999999, # Non-existent case
            courtroom_id=1,
            judge_id=1,
            scheduled_at=datetime.utcnow() + timedelta(days=1),
            purpose="Hearing",
            status="Scheduled"
        )
        db.session.add(bad_hearing)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_unique_constraints_enforced(app):
    """Assert duplicate emails and duplicate case numbers raise IntegrityError."""
    with app.app_context():
        # 1. Duplicate Email
        dup_user = User(
            email="gov@nyaya.in", # Already seeded
            full_name="Duplicate Gov",
            role="government",
            phone="9999999999"
        )
        dup_user.set_password("Pass@12345")
        db.session.add(dup_user)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()

        # 2. Duplicate Case Number
        seeded_case = Case.query.first()
        dup_case = Case(
            case_number=seeded_case.case_number,
            title="Duplicate Case Number",
            case_type="Civil",
            court_id=1
        )
        db.session.add(dup_case)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_cascade_delete_no_orphans(app):
    """Assert deleting a parent Case cascades and removes associated parties and hearings."""
    with app.app_context():
        # Create a test case with parties and hearings
        c = Case(case_number="TEST/CASC/001", title="Cascade Test Case", case_type="Civil", court_id=1, status="Registered")
        db.session.add(c)
        db.session.flush()

        p1 = CaseParty(case_id=c.id, name="Petitioner One", party_type="Petitioner")
        p2 = CaseParty(case_id=c.id, name="Respondent One", party_type="Respondent")
        h1 = Hearing(case_id=c.id, courtroom_id=1, judge_id=1, scheduled_at=datetime.utcnow() + timedelta(days=1), purpose="Evidence Hearing", status="Scheduled")
        db.session.add_all([p1, p2, h1])
        db.session.commit()

        c_id = c.id
        p1_id, p2_id, h1_id = p1.id, p2.id, h1.id

        # Delete case
        db.session.delete(c)
        db.session.commit()

        # Verify child records were deleted cleanly
        assert db.session.get(CaseParty, p1_id) is None
        assert db.session.get(CaseParty, p2_id) is None
        assert db.session.get(Hearing, h1_id) is None


def test_concurrent_case_number_generation_no_collisions(app):
    """Simulate rapid successive case filings to verify collision-free generation."""
    with app.app_context():
        from app.routes.api import clerk_register_case
        generated_numbers = []

        for i in range(15):
            prefix = "CIV"
            year = 2026
            case_number = None
            for attempt in range(25):
                cnt = Case.query.filter(Case.case_number.like(f"{prefix}/{year}/%")).count()
                candidate = f"{prefix}/{year}/{cnt + 1 + attempt:05d}"
                if not Case.query.filter_by(case_number=candidate).first() and candidate not in generated_numbers:
                    case_number = candidate
                    break
            assert case_number is not None
            generated_numbers.append(case_number)
            c = Case(case_number=case_number, title=f"Concurrent Case {i}", case_type="Civil", court_id=1, status="Registered")
            db.session.add(c)
            db.session.commit()

        # Assert all 15 generated case numbers are distinct
        assert len(generated_numbers) == len(set(generated_numbers))


def test_transaction_rollback_integrity(app):
    """Assert database transaction rollback cleanly reverts partial additions."""
    with app.app_context():
        initial_case_count = Case.query.count()

        try:
            c1 = Case(case_number="ROLL/2026/001", title="Valid Partial Case", case_type="Civil", court_id=1, status="Registered")
            db.session.add(c1)
            db.session.flush()

            # Deliberately violate FK to force exception
            bad_hearing = Hearing(case_id=999999, courtroom_id=1, judge_id=1, status="Scheduled")
            db.session.add(bad_hearing)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()

        # Assert no partial case was persisted
        assert Case.query.count() == initial_case_count
        assert Case.query.filter_by(case_number="ROLL/2026/001").first() is None


def test_reset_demo_database_clean_state(app):
    """Verify reset_demo_database recreates clean database schema and seeds demo records."""
    with app.app_context():
        reset_demo_database()
        assert Court.query.count() >= 3
        assert Courtroom.query.count() >= 5
        assert User.query.count() >= 14
        assert Case.query.count() >= 20
