"""
NyayaDesk Accessibility Audit with axe-core via Playwright
Audits public landing, login, register, demo guide, and judicial dashboards
for WCAG compliance, verifying zero critical or serious accessibility violations.
"""

import threading
import pytest
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright
from axe_playwright_python.sync_playwright import Axe

@pytest.fixture(scope='module')
def live_server(app):
    """Start local WSGI server for Playwright browser execution."""
    server = make_server('127.0.0.1', 0, app, threaded=True)
    port = server.socket.getsockname()[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    yield base_url
    server.shutdown()


@pytest.fixture(scope='module')
def browser():
    """Launch headless Chromium browser."""
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()


def audit_page_accessibility(page, url):
    """Navigate to URL and run axe accessibility scan."""
    page.goto(url)
    page.wait_for_load_state('domcontentloaded')
    page.wait_for_timeout(400)
    results = Axe().run(page)
    violations = results.response.get('violations', [])
    critical_and_serious = [
        v for v in violations if v.get('impact') in ['critical', 'serious']
    ]
    if critical_and_serious:
        err_details = []
        for v in critical_and_serious:
            err_details.append(f"[{v.get('impact').upper()}] {v.get('id')}: {v.get('help')}")
            for n in v.get('nodes', []):
                err_details.append(f"  Target: {n.get('target')} | HTML: {n.get('html')} | {n.get('failureSummary')}")
        assert len(critical_and_serious) == 0, f"Accessibility violations on {url}:\n" + "\n".join(err_details)


def test_public_pages_accessibility(browser, live_server):
    """Audit accessibility on public landing, login, register, and demo guide."""
    context = browser.new_context()
    page = context.new_page()
    try:
        # 1. Landing Page
        audit_page_accessibility(page, live_server)

        # 2. Login Page
        audit_page_accessibility(page, f"{live_server}/auth/login")

        # 3. Registration Page
        audit_page_accessibility(page, f"{live_server}/auth/register")

        # 4. Demo Guide
        audit_page_accessibility(page, f"{live_server}/demo-guide")
    finally:
        context.close()


def test_clerk_dashboard_accessibility(browser, live_server):
    """Audit accessibility on Clerk judicial workspace."""
    context = browser.new_context()
    page = context.new_page()
    try:
        # Login as clerk
        page.goto(f"{live_server}/auth/login")
        page.fill('#email', 'clerk@nyaya.in')
        page.fill('#password', 'Clerk@12345')
        page.click('button[type="submit"]')
        page.wait_for_url('**/dashboards/clerk**', timeout=10000)

        # Audit clerk workspace
        page.wait_for_timeout(400)
        results = Axe().run(page)
        violations = results.response.get('violations', [])
        critical_and_serious = [
            v for v in violations if v.get('impact') in ['critical', 'serious']
        ]
        if critical_and_serious:
            err_details = []
            for v in critical_and_serious:
                err_details.append(f"[{v.get('impact').upper()}] {v.get('id')}: {v.get('help')}")
                for n in v.get('nodes', []):
                    err_details.append(f"  Target: {n.get('target')} | HTML: {n.get('html')} | {n.get('failureSummary')}")
            assert len(critical_and_serious) == 0, "Accessibility violations on Clerk Dashboard:\n" + "\n".join(err_details)
    finally:
        context.close()
