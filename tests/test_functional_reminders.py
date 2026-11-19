"""
NyayaDesk Functional Tests - Notifications, Hearing Reminders & Scheduler
Covers multi-channel dispatches, quiet hours, templates, deduplication, and inbound replies.
"""

from datetime import datetime, timedelta, date
import pytest
from app.models import db, User, Hearing, HearingReminder, Notification, Case
from app.services.scheduler import scan_and_send_hearing_reminders
from app.services.notifier import render_message, is_in_quiet_hours, handle_inbound_reply
from tests.conftest import get_csrf

def test_notification_center_and_preferences(app, lawyer_client):
    """Test notification listing, mark-read, and channel preference management."""
    # 1. Fetch notifications
    res = lawyer_client.get('/api/notifications')
    assert res.status_code == 200
    data = res.get_json()
    assert 'notifications' in data
    assert 'unread_count' in data

    # 2. Mark all read
    token = get_csrf(lawyer_client)
    mark_res = lawyer_client.post('/api/notifications/mark-read', headers={'X-CSRFToken': token})
    assert mark_res.status_code == 200

    # 3. Verify unread count becomes 0
    res2 = lawyer_client.get('/api/notifications')
    assert res2.get_json().get('unread_count') == 0

    # 4. Get preferences
    pref_res = lawyer_client.get('/api/notifications/preferences')
    assert pref_res.status_code == 200
    pdata = pref_res.get_json()
    assert 'language_pref' in pdata
    assert 'preferences' in pdata

    # 5. Update preferences: language to Telugu, quiet hours active
    token = get_csrf(lawyer_client)
    upd_res = lawyer_client.post('/api/notifications/preferences', json={
        'language': 'te',
        'channels': {'SMS': True, 'WhatsApp': True, 'Email': False, 'In-App': True},
        'quiet_hours_start': '21:00',
        'quiet_hours_end': '07:00'
    }, headers={'X-CSRFToken': token})
    assert upd_res.status_code == 200
    assert upd_res.get_json().get('language_pref') == 'te'


def test_multilingual_templates():
    """Verify notification templates render in English, Telugu, and Hindi."""
    context = {
        'name': 'Advocate Sharma',
        'case_number': 'CIV/2026/00101',
        'date': '25-11-2026',
        'time': '10:30 AM',
        'courtroom': 'Courtroom 4',
        'court_name': 'Delhi High Court',
        'judge_name': 'Justice Mehta'
    }

    # English: returns (subject, body)
    en_subj, en_body = render_message('hearing_reminder_7d', 'en', context)
    assert 'CIV/2026/00101' in en_body
    assert 'Courtroom 4' in en_body

    # Telugu: returns (subject, body)
    te_subj, te_body = render_message('hearing_reminder_7d', 'te', context)
    assert 'CIV/2026/00101' in te_body
    assert len(te_body) > 10

    # Hindi: returns (subject, body)
    hi_subj, hi_body = render_message('hearing_reminder_7d', 'hi', context)
    assert 'CIV/2026/00101' in hi_body
    assert len(hi_body) > 10


def test_reminder_scan_and_deduplication(app):
    """
    Test 7-day, 1-day, and 2-hour reminder dispatch and ensure that
    running scan a second time produces 0 duplicate dispatches.
    """
    with app.app_context():
        # Clean any prior reminders for isolated test
        HearingReminder.query.delete()
        db.session.commit()

        # Run Scan 1
        stats1 = scan_and_send_hearing_reminders(app)
        assert stats1['hearings_scanned'] > 0
        reminders_sent_first = stats1['reminders_sent']

        # Run Scan 2 immediately: must NOT dispatch duplicate notifications
        stats2 = scan_and_send_hearing_reminders(app)
        assert stats2['reminders_sent'] == 0, "Duplicate reminders were dispatched on re-run!"

        # Verify reminders in database
        total_reminders = HearingReminder.query.count()
        assert total_reminders == reminders_sent_first


def test_inbound_sms_reply_confirm(app):
    """Test citizen/lawyer SMS reply with 'CONFIRM'."""
    with app.app_context():
        # Get active litigant user
        litigant = User.query.filter_by(role='litigant', email='litigant1@nyaya.in').first()
        phone = litigant.phone

        # Simulate inbound SMS: CONFIRM
        result = handle_inbound_reply(phone, "CONFIRM")
        assert result.get('success') is True
        assert result.get('action') in ['CONFIRMED', 'ACKNOWLEDGED']
