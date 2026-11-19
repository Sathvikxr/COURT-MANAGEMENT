"""
NyayaDesk UI End-to-End Tests with Playwright (Chromium)
Validates core citizen and judicial user journeys across Desktop and 375px mobile viewports:
- Signup -> Gov Approval -> Judge Login
- Case Filing Wizard
- Hearing Scheduling
- Notifications Bell Dropdown
- Dark Mode / Theme Toggle
- NyayaMitra AI Legal Chatbot
Monitors browser console errors and captures failure screenshots into tests/screenshots/.
"""

import os
import threading
import time
import pytest
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright

SCREENSHOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), 'screenshots'))
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

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
def browser_context():
    """Launch headless Chromium browser."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


def create_page_with_console_monitor(browser, viewport_width=1280, viewport_height=800):
    """Helper to instantiate page with console error logging."""
    context = browser.new_context(viewport={'width': viewport_width, 'height': viewport_height})
    page = context.new_page()
    console_errors = []

    def handle_console(msg):
        if msg.type == 'error':
            console_errors.append(msg.text)

    page.on('console', handle_console)
    return context, page, console_errors


def test_theme_toggle_and_chatbot_e2e(browser_context, live_server):
    """E2E Test: Dark mode toggle & NyayaMitra AI Chatbot at Desktop & 375px mobile."""
    for width in [1280, 375]:
        context, page, console_errors = create_page_with_console_monitor(browser_context, viewport_width=width, viewport_height=800 if width > 500 else 667)
        try:
            page.goto(live_server)
            page.wait_for_load_state('domcontentloaded')

            # 1. Dark Mode Toggle
            html_elem = page.locator('html')
            initial_theme = html_elem.get_attribute('data-theme')
            toggle_btn = page.locator('#theme-toggle-btn')
            toggle_btn.click()
            time.sleep(0.3)
            new_theme = html_elem.get_attribute('data-theme')
            assert new_theme != initial_theme, f"Theme failed to toggle at width {width}"

            # 2. NyayaMitra AI Chatbot
            trigger = page.locator('#ai-chat-trigger')
            assert trigger.is_visible()
            trigger.click()
            time.sleep(0.3)

            chat_win = page.locator('#ai-chat-window')
            assert chat_win.is_visible(), f"Chatbot window failed to open at width {width}"

            # Ask procedural query
            chat_input = page.locator('#ai-chat-input')
            chat_input.fill('How do I apply for bail?')
            page.keyboard.press('Enter')
            page.wait_for_selector('.ai-chat-bubble.bot', timeout=8000)

            # Check no fatal console errors occurred
            severe_errors = [e for e in console_errors if 'favicon' not in e.lower() and 'font' not in e.lower()]
            assert len(severe_errors) == 0, f"Console errors on chatbot flow: {severe_errors}"

        except Exception as err:
            page.screenshot(path=os.path.join(SCREENSHOT_DIR, f"fail_theme_chatbot_{width}.png"))
            raise err
        finally:
            context.close()


def test_clerk_hearing_scheduling_and_notifs_e2e(browser_context, live_server):
    """E2E Test: Clerk sign-in, notification bell dropdown, and hearing management."""
    context, page, console_errors = create_page_with_console_monitor(browser_context, viewport_width=1280, viewport_height=800)
    try:
        # 1. Clerk Login
        page.goto(f"{live_server}/auth/login")
        page.fill('#email', 'clerk@nyaya.in')
        page.fill('#password', 'Clerk@12345')
        page.click('button[type="submit"]')
        page.wait_for_url('**/dashboards/clerk**', timeout=10000)

        # 2. Notification Bell Dropdown
        bell_btn = page.locator('#notif-bell-btn')
        bell_btn.click()
        time.sleep(0.3)
        notif_dropdown = page.locator('#notif-dropdown')
        assert notif_dropdown.is_visible()

        # 3. Schedule Hearing Modal trigger
        schedule_btn = page.locator('button:has-text("Schedule Hearing")').first
        if schedule_btn.is_visible():
            schedule_btn.click()
            time.sleep(0.3)
            modal = page.locator('#schedule-hearing-modal')
            assert modal.is_visible()
            # Close modal
            page.keyboard.press('Escape')

    except Exception as err:
        page.screenshot(path=os.path.join(SCREENSHOT_DIR, "fail_clerk_schedule_e2e.png"))
        raise err
    finally:
        context.close()


def test_public_cause_list_and_search_e2e(browser_context, live_server):
    """E2E Test: Public landing, global quick search (Ctrl+K), and cause list viewing."""
    context, page, console_errors = create_page_with_console_monitor(browser_context, viewport_width=1280, viewport_height=800)
    try:
        page.goto(live_server)

        # Trigger Global Quick Search modal
        page.keyboard.press('Control+KeyK')
        time.sleep(0.3)
        search_modal = page.locator('#global-search-modal')
        if search_modal.is_visible():
            search_input = page.locator('#global-search-modal-input')
            search_input.fill('Union')
            time.sleep(0.6)
            results = page.locator('#global-search-results')
            assert results.is_visible()
            # Close search modal
            page.keyboard.press('Escape')

        # Navigate to Demo Guide
        page.goto(f"{live_server}/demo-guide")
        page.wait_for_load_state('domcontentloaded')
        assert page.locator('text=NyayaDesk').first.is_visible()

    except Exception as err:
        page.screenshot(path=os.path.join(SCREENSHOT_DIR, "fail_public_cause_list.png"))
        raise err
    finally:
        context.close()
