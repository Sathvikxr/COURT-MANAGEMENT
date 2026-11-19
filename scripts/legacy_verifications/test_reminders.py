import os
os.environ['DISABLE_SQLALCHEMY_CEXT'] = '1'
import sys
sys.path.insert(0, r'C:\CourtMS')

from app import create_app
from app.models import db, User, Hearing, Notification, HearingReminder, AuditLog
from app.services.notifier import send_notification, handle_inbound_reply, OUTBOX_LOG_PATH, render_message
from app.services.scheduler import scan_and_send_hearing_reminders

app = create_app()

print("==================================================================")
print("  NyayaDesk CMS - Reminder & Notification Verification Suite     ")
print("==================================================================")

# -------------------------------------------------------------------------
# Test 1: Multilingual Templates (English, Telugu, Hindi)
# -------------------------------------------------------------------------
print("\n--- 1. Testing Multilingual Templates (EN, TE, HI) ---")
ctx = {
    'name': 'Ramesh Chandra Gupta',
    'case_number': 'CIV/2026/00010',
    'date': '17-11-2026',
    'time': '10:30 AM',
    'courtroom': 'Courtroom 1',
    'court_name': 'High Court of Delhi',
    'judge_name': "Hon'ble Justice Rajesh Sharma"
}

for lang in ['en', 'te', 'hi']:
    subj, body = render_message('hearing_reminder_2h', lang, ctx)
    print(f"[{lang.upper()}] Subject: {subj}")
    print(f"[{lang.upper()}] Body: {body[:90]}...")
    assert len(body) > 20, f"Template body empty for language {lang}"
    assert 'CIV/2026/00010' in body or 'CIV' in body

print("✓ All 3 language templates verified successfully!")

# -------------------------------------------------------------------------
# Test 2: Trigger Reminder Job (First Run) & Outbox Logging
# -------------------------------------------------------------------------
print("\n--- 2. Testing First Run of Reminder Scanner ---")
with app.app_context():
    # Clear reminders table for a clean test
    HearingReminder.query.delete()
    db.session.commit()

    stats1 = scan_and_send_hearing_reminders()
    print(f"First Run Stats -> Scanned: {stats1['hearings_scanned']}, Reminders Dispatched: {stats1['reminders_sent']}")
    assert stats1['reminders_sent'] > 0, "Expected reminders to be sent for demo hearings!"

    # Verify outbox.log exists and contains entries
    assert os.path.exists(OUTBOX_LOG_PATH), f"Outbox log file not found at {OUTBOX_LOG_PATH}"
    with open(OUTBOX_LOG_PATH, 'r', encoding='utf-8') as f:
        log_content = f.read()
    assert len(log_content) > 100
    assert "PROVIDER: DEMO_GATEWAY" in log_content
    assert "STATUS: DELIVERED" in log_content
    print(f"✓ Verified C:\\CourtMS\\data\\outbox.log exists ({len(log_content)} bytes written)")

# -------------------------------------------------------------------------
# Test 3: Duplicate Suppression (Second Run)
# -------------------------------------------------------------------------
print("\n--- 3. Testing Duplicate Prevention (Second Run) ---")
with app.app_context():
    stats2 = scan_and_send_hearing_reminders()
    print(f"Second Run Stats -> Scanned: {stats2['hearings_scanned']}, Reminders Dispatched: {stats2['reminders_sent']}")
    assert stats2['reminders_sent'] == 0, f"Expected 0 duplicates sent, but got {stats2['reminders_sent']}!"
    print("✓ Duplicate prevention confirmed: exactly 0 duplicates sent on 2nd run!")

# -------------------------------------------------------------------------
# Test 4: Retry and Fallback Pipeline & Channel Preferences
# -------------------------------------------------------------------------
print("\n--- 4. Testing Channel Fallback & User Preferences ---")
with app.app_context():
    litigant = User.query.filter_by(role='litigant').first()
    assert litigant is not None

    # Disable SMS, so it falls back to WhatsApp or Email
    prefs = litigant.get_notification_prefs()
    prefs['sms'] = False
    prefs['whatsapp'] = True
    litigant.set_notification_prefs(prefs)
    db.session.commit()

    ok, notif = send_notification(
        user=litigant,
        template_key='hearing_reminder_1d',
        context=ctx,
        preferred_channel='SMS'
    )
    assert ok is True
    print(f"Fallback check -> Preferred: SMS (disabled) -> Dispatched via: {notif.channel} (Fallback from: {notif.fallback_from})")
    assert notif.channel in ['WhatsApp', 'Email', 'In-App']
    assert notif.fallback_from == 'SMS'

    # Restore SMS pref
    prefs['sms'] = True
    litigant.set_notification_prefs(prefs)
    db.session.commit()
    print("✓ Channel fallback cascade and user preference opt-in/opt-out verified!")

# -------------------------------------------------------------------------
# Test 5: Two-Way Attendance Simulation (CONFIRM Reply)
# -------------------------------------------------------------------------
print("\n--- 5. Testing Two-Way Inbound Reply Simulator ---")
with app.app_context():
    litigant = User.query.filter_by(role='litigant').first()
    litigant_phone = litigant.phone

    # Find upcoming scheduled hearing
    hearing = Hearing.query.filter_by(status='Scheduled').order_by(Hearing.scheduled_at.asc()).first()
    assert hearing is not None
    # Reset attendance
    hearing.attendance_status = 'Unconfirmed'
    db.session.commit()

    # Simulate inbound reply from litigant
    reply_res = handle_inbound_reply(sender_contact=litigant_phone, message_text="CONFIRM")
    print(f"Reply Result: {reply_res}")
    assert reply_res['success'] is True
    assert reply_res['action'] == 'CONFIRMED'

    # Verify hearing updated in database
    confirmed_hearing = Hearing.query.get(reply_res['hearing_id'])
    assert confirmed_hearing.attendance_status == 'Confirmed'
    assert confirmed_hearing.attendance_confirmed_at is not None
    print(f"✓ Hearing ID {confirmed_hearing.id} attendance status updated to: {confirmed_hearing.attendance_status}")

    # Verify audit log recorded
    audit = AuditLog.query.filter_by(action='ATTENDANCE_CONFIRMED').order_by(AuditLog.id.desc()).first()
    assert audit is not None
    print(f"✓ AuditLog confirmed: {audit.details}")

# -------------------------------------------------------------------------
# Test 6: API Endpoints & New Dashboard Pages
# -------------------------------------------------------------------------
print("\n--- 6. Testing New Frontend Routes & Endpoints ---")
client = app.test_client()

# Login as clerk
client.post('/auth/login', data={'email': 'clerk@nyaya.in', 'password': 'Clerk@12345'})

# Test /notifications page
r = client.get('/notifications')
assert r.status_code == 200, f"/notifications returned {r.status_code}"
print("✓ GET /notifications -> HTTP 200 OK")

# Test /outbox page
r = client.get('/outbox')
assert r.status_code == 200, f"/outbox returned {r.status_code}"
print("✓ GET /outbox -> HTTP 200 OK")

# Test /reminders page
r = client.get('/reminders')
assert r.status_code == 200, f"/reminders returned {r.status_code}"
print("✓ GET /reminders -> HTTP 200 OK")

# Test /api/outbox/logs
r = client.get('/api/outbox/logs')
assert r.status_code == 200
logs = r.get_json().get('logs', [])
print(f"✓ GET /api/outbox/logs -> HTTP 200 OK ({len(logs)} log records returned)")
assert len(logs) > 0

# Test /api/reminders/upcoming
r = client.get('/api/reminders/upcoming')
assert r.status_code == 200
hearings_res = r.get_json().get('hearings', [])
print(f"✓ GET /api/reminders/upcoming -> HTTP 200 OK ({len(hearings_res)} upcoming hearings)")
assert len(hearings_res) > 0

# Test /api/notifications/preferences GET & POST
r = client.get('/api/notifications/preferences')
assert r.status_code == 200
prefs_data = r.get_json()
print(f"✓ GET /api/notifications/preferences -> {prefs_data['language_pref']}, {prefs_data['preferences']}")

r = client.post('/api/notifications/preferences', json={'sms': True, 'language_pref': 'te'})
assert r.status_code == 200
assert r.get_json()['language_pref'] == 'te'
print("✓ POST /api/notifications/preferences -> updated to Telugu ('te')")

# Test /api/notifications/simulate-reply via HTTP POST
r = client.post('/api/notifications/simulate-reply', json={'sender_contact': '9810011008', 'message_text': 'CONFIRM'})
assert r.status_code == 200
assert r.get_json()['success'] is True
print("✓ POST /api/notifications/simulate-reply -> HTTP 200 (CONFIRMED)")

print("\n==================================================================")
print("  ALL REMINDER & NOTIFICATION TESTS PASSED WITH ZERO ERRORS!      ")
print("==================================================================")
