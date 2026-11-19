"""
NyayaDesk Automated Test Suite - Shared Fixtures and Setup
Configures isolated test application, SQLite database with PRAGMA foreign_keys,
seeded fixtures, role-based authenticated clients, and CSRF utilities.
"""

import os
import tempfile
import pytest
from app import create_app
from app.models import db, User, Case, Hearing, Court, Courtroom
from app.seed import seed_demo_data

@pytest.fixture(scope='session')
def app():
    """Session-wide application instance with isolated test database."""
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(db_fd)
    
    upload_dir = tempfile.mkdtemp(prefix='nyaya_test_uploads_')
    os.makedirs(os.path.join(upload_dir, 'id_proofs'), exist_ok=True)
    os.makedirs(os.path.join(upload_dir, 'cases'), exist_ok=True)

    test_config = {
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': f"sqlite:///{db_path.replace(os.sep, '/')}",
        'SQLALCHEMY_TRACK_MODIFICATIONS': False,
        'UPLOAD_FOLDER': upload_dir,
        'WTF_CSRF_ENABLED': True,
        'SECRET_KEY': 'test-secret-key-nyayadesk-audit-2026',
        'PRESERVE_CONTEXT_ON_EXCEPTION': False
    }

    application = create_app(test_config)

    with application.app_context():
        db.create_all()
        seed_demo_data()

    yield application

    # Tear down database & files
    with application.app_context():
        db.engine.dispose()
    
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except Exception:
        pass


@pytest.fixture
def client(app):
    """Anonymous client."""
    return app.test_client()


def get_csrf(client):
    """Utility to fetch an active CSRF token from the client session."""
    client.get('/')
    with client.session_transaction() as sess:
        return sess.get('_csrf_token', '')


def login_as(client, email, password):
    """Authenticate client with role credentials."""
    token = get_csrf(client)
    res = client.post(
        '/auth/login',
        json={'email': email, 'password': password},
        headers={'X-CSRFToken': token}
    )
    assert res.status_code == 200, f"Login failed for {email}: {res.data.decode('utf-8')}"
    return client


@pytest.fixture
def gov_client(app):
    c = app.test_client()
    return login_as(c, 'gov@nyaya.in', 'Gov@12345')


@pytest.fixture
def reg_client(app):
    c = app.test_client()
    return login_as(c, 'registrar@nyaya.in', 'Reg@12345')


@pytest.fixture
def judge_client(app):
    c = app.test_client()
    return login_as(c, 'judge1@nyaya.in', 'Judge@12345')


@pytest.fixture
def clerk_client(app):
    c = app.test_client()
    return login_as(c, 'clerk@nyaya.in', 'Clerk@12345')


@pytest.fixture
def lawyer_client(app):
    c = app.test_client()
    return login_as(c, 'lawyer1@nyaya.in', 'Lawyer@12345')


@pytest.fixture
def litigant_client(app):
    c = app.test_client()
    return login_as(c, 'litigant1@nyaya.in', 'Litigant@12345')


@pytest.fixture
def police_client(app):
    c = app.test_client()
    return login_as(c, 'police@nyaya.in', 'Police@12345')
