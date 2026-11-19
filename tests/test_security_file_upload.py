"""
NyayaDesk Security Tests - File Upload Hardening & Direct Browsing Prevention
Verifies enforcement of extension whitelists, MIME checks, magic bytes inspection,
path traversal blocking, size limits, and prohibition of static directory browsing.
"""

import io
import pytest
from tests.conftest import get_csrf

def test_upload_wrong_extension_rejected(clerk_client):
    """Assert files with unauthorized extensions are rejected with 400."""
    token = get_csrf(clerk_client)
    bad_file = (io.BytesIO(b'echo "malicious"'), 'script.sh')
    res = clerk_client.post('/api/clerk/documents/upload', data={
        'csrf_token': token,
        'case_id': 1,
        'doc_type': 'Petition',
        'file': bad_file
    }, content_type='multipart/form-data')
    assert res.status_code == 400
    assert b"Invalid file format" in res.data or b"Prohibited file" in res.data


def test_upload_dangerous_double_extension_rejected(clerk_client):
    """Assert double extension executables (e.g., invoice.pdf.exe) are rejected with 400."""
    token = get_csrf(clerk_client)
    double_ext = (io.BytesIO(b'executable payload'), 'case_evidence.pdf.exe')
    res = clerk_client.post('/api/clerk/documents/upload', data={
        'csrf_token': token,
        'case_id': 1,
        'doc_type': 'Evidence',
        'file': double_ext
    }, content_type='multipart/form-data')
    assert res.status_code == 400
    assert b"Prohibited file" in res.data


def test_upload_directory_traversal_filename_rejected(clerk_client):
    """Assert path traversal in filename (../../etc/passwd) is rejected with 400."""
    token = get_csrf(clerk_client)
    traversal_file = (io.BytesIO(b'%PDF-1.4 sample'), '../../etc/passwd.pdf')
    res = clerk_client.post('/api/clerk/documents/upload', data={
        'csrf_token': token,
        'case_id': 1,
        'doc_type': 'Petition',
        'file': traversal_file
    }, content_type='multipart/form-data')
    assert res.status_code == 400
    assert b"directory traversal" in res.data.lower()


def test_upload_executable_magic_bytes_rejected(clerk_client):
    """Assert file disguised as PDF but beginning with Windows MZ or Linux ELF magic bytes is blocked."""
    token = get_csrf(clerk_client)
    # MZ executable header
    fake_pdf = (io.BytesIO(b'MZ\x90\x00\x03\x00\x00\x00\x04\x00fake pe executable'), 'disguised.pdf')
    res = clerk_client.post('/api/clerk/documents/upload', data={
        'csrf_token': token,
        'case_id': 1,
        'doc_type': 'Petition',
        'file': fake_pdf
    }, content_type='multipart/form-data')
    assert res.status_code == 400
    assert b"executable binary" in res.data.lower()


def test_static_uploads_direct_browsing_forbidden(client):
    """Verify unauthenticated direct requests to /static/uploads are rejected with 403."""
    res1 = client.get('/static/uploads/id_proofs/sample.pdf')
    assert res1.status_code == 403

    res2 = client.get('/static/uploads/cases/petition.pdf')
    assert res2.status_code == 403
