import os
os.environ['DISABLE_SQLALCHEMY_CEXT'] = '1'
import sys
sys.path.insert(0, r'C:\CourtMS')

from app import create_app
from app.models import db, User, Court, Case, ApprovalRequest, Hearing, Order, Payment
from app.auth import FAILED_LOGIN_ATTEMPTS

FAILED_LOGIN_ATTEMPTS.clear()

app = create_app()

print("==================================================")
print("  NyayaDesk CMS - Full Verification Test Suite    ")
print("==================================================")

# 1. Database Counts
print("\n--- 1. Database Model Health & Counts ---")
with app.app_context():
    print(f"Users: {User.query.count()} (Approved + Pending)")
    print(f"Courts: {Court.query.count()}")
    print(f"Cases: {Case.query.count()}")
    print(f"Hearings: {Hearing.query.count()}")
    print(f"Orders: {Order.query.count()}")
    print(f"Payments: {Payment.query.count()}")
    print(f"Pending Approvals: {ApprovalRequest.query.filter_by(status='Pending').count()}")

client = app.test_client()

# 2. Public Endpoints
print("\n--- 2. Public & Guest Routes ---")
for route in ['/', '/health', '/auth/login', '/auth/register', '/auth/forgot-password']:
    r = client.get(route)
    assert r.status_code == 200, f"Route {route} failed with {r.status_code}"
    print(f"✓ GET {route} -> HTTP 200 OK")

# 3. All 7 Roles Authentication & Dashboard Access
print("\n--- 3. Testing RBAC & Dashboards for All 7 Roles ---")
roles = [
    ('government', 'gov@nyaya.in', 'Gov@12345', '/gov'),
    ('registrar', 'registrar@nyaya.in', 'Reg@12345', '/registrar'),
    ('judge', 'judge1@nyaya.in', 'Judge@12345', '/judge'),
    ('clerk', 'clerk@nyaya.in', 'Clerk@12345', '/clerk'),
    ('lawyer', 'lawyer1@nyaya.in', 'Lawyer@12345', '/lawyer'),
    ('litigant', 'litigant1@nyaya.in', 'Litigant@12345', '/litigant'),
    ('police', 'police@nyaya.in', 'Police@12345', '/police')
]

for role_name, email, password, target_url in roles:
    c = app.test_client()
    resp = c.post('/auth/login', data={'email': email, 'password': password}, follow_redirects=False)
    assert resp.status_code == 302, f"Login for {email} failed: {resp.status_code}"
    # Verify redirected to proper dashboard
    assert target_url in resp.headers.get('Location', ''), f"Expected redirect to {target_url}, got {resp.headers.get('Location')}"
    # Fetch dashboard page
    page_resp = c.get(target_url)
    assert page_resp.status_code == 200, f"Access to {target_url} failed with {page_resp.status_code}"
    print(f"✓ Role {role_name:<11} | Login -> 302 -> {target_url} HTTP 200 OK")

# 4. Pending Approval Flow
print("\n--- 4. Pending Approval Workflow ---")
c_pending = app.test_client()
r_pend_login = c_pending.post('/auth/login', data={'email': 'judge_pending1@nyaya.in', 'password': 'Judge@12345'}, follow_redirects=False)
assert r_pend_login.status_code == 302
assert '/auth/pending-approval' in r_pend_login.headers.get('Location', '')
r_pend_page = c_pending.get('/auth/pending-approval')
assert r_pend_page.status_code == 200
print(f"✓ Pending Judge login correctly routed to /auth/pending-approval (HTTP 200)")

# Ensure pending judge CANNOT access judge dashboard
r_blocked = c_pending.get('/judge')
assert r_blocked.status_code == 302
assert '/auth/pending-approval' in r_blocked.headers.get('Location', '')
print(f"✓ Pending Judge strictly blocked from /judge dashboard (RBAC enforced)")

# 5. Government API & Approval Actions
print("\n--- 5. Government APIs & Actions ---")
c_gov = app.test_client()
c_gov.post('/auth/login', data={'email': 'gov@nyaya.in', 'password': 'Gov@12345'})

r = c_gov.get('/api/gov/stats')
assert r.status_code == 200
stats = r.get_json()
print(f"✓ /api/gov/stats -> courts={stats['total_courts']}, judges={stats['total_judges']}, pending={stats['pending_approvals']}")

r = c_gov.get('/api/gov/approvals')
assert r.status_code == 200
approvals = r.get_json()
print(f"✓ /api/gov/approvals -> retrieved {len(approvals)} approval requests")

r = c_gov.get('/api/gov/analytics')
assert r.status_code == 200
print(f"✓ /api/gov/analytics -> HTTP 200 with chart data breakdowns")

r = c_gov.get('/api/gov/audit-logs')
assert r.status_code == 200
print(f"✓ /api/gov/audit-logs -> retrieved {len(r.get_json())} audit log records")

# 6. Judge APIs & Cause List
print("\n--- 6. Judge APIs & Cause List ---")
c_judge = app.test_client()
c_judge.post('/auth/login', data={'email': 'judge1@nyaya.in', 'password': 'Judge@12345'})

r = c_judge.get('/api/judge/calendar-events')
assert r.status_code == 200
events = r.get_json()
print(f"✓ /api/judge/calendar-events -> {len(events)} FullCalendar hearing events")

r = c_judge.get('/api/judge/cases/1')
assert r.status_code == 200
case_det = r.get_json()
print(f"✓ /api/judge/cases/1 -> Case '{case_det['case_number']}' with {len(case_det['parties'])} parties, {len(case_det['hearings'])} hearings, {len(case_det['orders'])} orders")

r = c_judge.get('/api/judge/ai-summary/1')
assert r.status_code == 200
summary_res = r.get_json()
print(f"✓ /api/judge/ai-summary/1 -> AI Summary generated ({len(summary_res['summary'])} chars)")

# 7. Global Search & Notifications
print("\n--- 7. Global Search & Notifications ---")
r = c_judge.get('/api/search?q=CIV')
assert r.status_code == 200
res = r.get_json()
print(f"✓ /api/search?q=CIV -> Found {len(res['cases'])} cases")

r = c_judge.get('/api/notifications')
assert r.status_code == 200
notifs = r.get_json()
print(f"✓ /api/notifications -> {len(notifs['notifications'])} notifications for user")

# 8. Forgot Password Flow
print("\n--- 8. Forgot Password Simulated OTP Flow ---")
c_anon = app.test_client()
r_otp = c_anon.post('/auth/forgot-password', data={'action': 'request_otp', 'email': 'lawyer1@nyaya.in'}, follow_redirects=True)
assert r_otp.status_code == 200
assert b'DEMO SMS / EMAIL GATEWAY' in r_otp.data
print(f"✓ /auth/forgot-password -> Simulated OTP successfully generated on-screen")

print("\n==================================================")
print("  ALL 8 TEST PHASES PASSED WITH ZERO ERRORS!       ")
print("==================================================")
