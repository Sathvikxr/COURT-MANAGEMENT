import os
import sys
import json
import time
import requests

BASE_URL = "http://127.0.0.1:8000"

def run_tests():
    print("=" * 70)
    print("  NYAYADESK COMPREHENSIVE END-TO-END QA & POLISH AUDIT SUITE")
    print("=" * 70)
    
    passed = 0
    failed = 0
    
    def assert_test(cond, title, detail=""):
        nonlocal passed, failed
        if cond:
            print(f"  [PASS] {title}")
            passed += 1
        else:
            print(f"  [FAIL] {title} -> {detail}")
            failed += 1
            
    # -------------------------------------------------------------
    # 1. PUBLIC PORTAL & STATIC ASSETS
    # -------------------------------------------------------------
    print("\n--- 1. Public Portal & Static Assets ---")
    s = requests.Session()
    r = s.get(f"{BASE_URL}/")
    assert_test(r.status_code == 200 and "NyayaDesk" in r.text, "Public Landing Page (/)", f"Status: {r.status_code}")
    
    r = s.get(f"{BASE_URL}/demo-guide")
    assert_test(r.status_code == 200 and "Demo Guide" in r.text and "Reset Demo Database" in r.text, "Demo Guide Page (/demo-guide)", f"Status: {r.status_code}")
    
    r = s.get(f"{BASE_URL}/favicon.ico")
    assert_test(r.status_code == 200 and "image/svg+xml" in r.headers.get("Content-Type", ""), "Favicon endpoint (/favicon.ico)", f"Status: {r.status_code}")
    
    r = s.get(f"{BASE_URL}/health")
    assert_test(r.status_code == 200 and r.json().get("status") == "healthy", "Health Check (/health)", f"Status: {r.status_code}")
    
    r = s.get(f"{BASE_URL}/this-route-does-not-exist-xyz")
    assert_test(r.status_code == 404 and "404" in r.text and "Not Found" in r.text, "Custom 404 Page", f"Status: {r.status_code}")
    
    # -------------------------------------------------------------
    # 2. ROLE-BASED ACCESS & DASHBOARD RENDERING
    # -------------------------------------------------------------
    print("\n--- 2. Role Dashboard Authentication & UI Rendering ---")
    roles_creds = [
        ("government", "gov@nyaya.in", "Gov@12345", "/gov", "National Judicial Governance"),
        ("registrar", "registrar@nyaya.in", "Reg@12345", "/registrar", "Registrar General"),
        ("judge", "judge1@nyaya.in", "Judge@12345", "/judge", "Presiding Judge"),
        ("clerk", "clerk@nyaya.in", "Clerk@12345", "/clerk", "Court Master"),
        ("lawyer", "lawyer1@nyaya.in", "Lawyer@12345", "/lawyer", "Advocate"),
        ("litigant", "litigant1@nyaya.in", "Litigant@12345", "/litigant", "Litigant"),
        ("police", "police@nyaya.in", "Police@12345", "/police", "Police")
    ]
    
    for role_name, email, pwd, url, expected_text in roles_creds:
        sess = requests.Session()
        res = sess.post(f"{BASE_URL}/auth/login", data={"email": email, "password": pwd}, allow_redirects=True)
        assert_test(res.status_code == 200 and expected_text in res.text, f"Login as {role_name.capitalize()} -> {url}", f"Status: {res.status_code}")
        
    # Shared pages for authenticated users
    sess = requests.Session()
    sess.post(f"{BASE_URL}/auth/login", data={"email": "gov@nyaya.in", "password": "Gov@12345"})
    for path, title in [("/notifications", "Notifications"), ("/reminders", "Hearing Reminders"), ("/outbox", "Outbox")]:
        r = sess.get(f"{BASE_URL}{path}")
        assert_test(r.status_code == 200, f"Access {path} ({title})", f"Status: {r.status_code}")
        
    # -------------------------------------------------------------
    # 3. RBAC SECURITY & URL GUESSING
    # -------------------------------------------------------------
    print("\n--- 3. RBAC Enforcement & Forbidden Interceptions ---")
    lawyer_sess = requests.Session()
    lawyer_sess.post(f"{BASE_URL}/auth/login", data={"email": "lawyer1@nyaya.in", "password": "Lawyer@12345"})
    
    # Lawyer trying to access /gov
    r = lawyer_sess.get(f"{BASE_URL}/gov", allow_redirects=False)
    assert_test(r.status_code == 403, "RBAC: Lawyer blocked from /gov (403)", f"Status: {r.status_code}")
    
    # Lawyer trying to access /judge
    r = lawyer_sess.get(f"{BASE_URL}/judge", allow_redirects=False)
    assert_test(r.status_code == 403, "RBAC: Lawyer blocked from /judge (403)", f"Status: {r.status_code}")
    
    # Litigant trying to call Gov API
    lit_sess = requests.Session()
    lit_sess.post(f"{BASE_URL}/auth/login", data={"email": "litigant1@nyaya.in", "password": "Litigant@12345"})
    r = lit_sess.get(f"{BASE_URL}/api/gov/analytics")
    assert_test(r.status_code == 403, "RBAC API: Litigant blocked from /api/gov/analytics", f"Status: {r.status_code}")
    
    # Litigant trying to issue judge order
    r = lit_sess.post(f"{BASE_URL}/api/judge/orders/issue", json={"case_id": 1, "title": "Illegal", "order_type": "Final", "content": "Bad"})
    assert_test(r.status_code == 403, "RBAC API: Litigant blocked from /api/judge/orders/issue", f"Status: {r.status_code}")

    # -------------------------------------------------------------
    # 4. REAL DB ANALYTICS API ENDPOINTS
    # -------------------------------------------------------------
    print("\n--- 4. Real DB Analytics Endpoints ---")
    # Gov Analytics
    gov_sess = requests.Session()
    gov_sess.post(f"{BASE_URL}/auth/login", data={"email": "gov@nyaya.in", "password": "Gov@12345"})
    r = gov_sess.get(f"{BASE_URL}/api/gov/analytics")
    gov_data = r.json()
    assert_test(r.status_code == 200 and "case_types" in gov_data and "status_ratio" in gov_data, "Gov Analytics API returns real metrics", f"Data: {r.text[:80]}")
    
    # Registrar Analytics
    reg_sess = requests.Session()
    reg_sess.post(f"{BASE_URL}/auth/login", data={"email": "registrar@nyaya.in", "password": "Reg@12345"})
    r = reg_sess.get(f"{BASE_URL}/api/registrar/analytics")
    reg_data = r.json()
    assert_test(r.status_code == 200 and "bench_caseload" in reg_data and "case_stages" in reg_data, "Registrar Analytics API returns pipeline & bench metrics", f"Data: {r.text[:80]}")
    
    # Judge Analytics
    judge_sess = requests.Session()
    judge_sess.post(f"{BASE_URL}/auth/login", data={"email": "judge1@nyaya.in", "password": "Judge@12345"})
    r = judge_sess.get(f"{BASE_URL}/api/judge/analytics")
    judge_data = r.json()
    assert_test(r.status_code == 200 and "case_types" in judge_data and "hearing_outcomes" in judge_data, "Judge Analytics API returns bench metrics", f"Data: {r.text[:80]}")

    # -------------------------------------------------------------
    # 5. ACCOUNT LIFECYCLE FLOW: NEW JUDGE REGISTRATION & APPROVAL
    # -------------------------------------------------------------
    print("\n--- 5. Account Lifecycle: Judge Registration -> Gov Approval -> Empty State ---")
    judge_email = f"qa_judge_{int(time.time())}@nyaya.in"
    judge_pwd = "TestJudge@123"
    
    # Step A: Sign up as new Judge
    signup_sess = requests.Session()
    reg_data = {
        "full_name": "Justice QA Automated",
        "email": judge_email,
        "phone": "+919876500112",
        "password": judge_pwd,
        "confirm_password": judge_pwd,
        "role": "judge",
        "court_id": "1",
        "court_name": "High Court of Delhi",
        "designation": "Additional District Judge",
        "employee_id": "EMP-JUDGE-QA-99",
        "years_service": "12",
        "language_pref": "en"
    }
    r = signup_sess.post(f"{BASE_URL}/auth/register", data=reg_data, allow_redirects=True)
    assert_test(r.status_code == 200 and ("Pending" in r.text or "Government" in r.text), "Judge Registration -> Pending Gov Screen", f"Status: {r.status_code}")
    
    # Step B: Try logging in as the pending judge
    pending_sess = requests.Session()
    r = pending_sess.post(f"{BASE_URL}/auth/login", data={"email": judge_email, "password": judge_pwd}, allow_redirects=True)
    assert_test(r.status_code == 200 and "pending" in r.url, "Pending Judge Login redirects to /auth/pending", f"URL: {r.url}")
    
    # Step C: Log in as Gov admin, find the approval request, and approve
    r = gov_sess.get(f"{BASE_URL}/api/gov/approvals")
    approvals_data = r.json()
    new_req = next((item for item in approvals_data.get("requests", []) if (item.get("email") == judge_email or item.get("applicant_email") == judge_email)), None)
    assert_test(new_req is not None, "Gov Admin finds new Judge Approval Request", f"Found: {new_req is not None}")
    
    if new_req:
        req_id = new_req["id"]
        # Approve request
        action_res = gov_sess.post(f"{BASE_URL}/api/gov/approvals/{req_id}/action", json={"action": "approve", "remarks": "Credentials verified via QA."})
        assert_test(action_res.status_code == 200 and action_res.json().get("success"), "Gov Admin approves Judge", f"Resp: {action_res.text}")
        
    # Step D: Verify Outbox / Notification generated
    time.sleep(0.5)
    outbox_file = r"C:\CourtMS\data\outbox.log"
    outbox_content = ""
    if os.path.exists(outbox_file):
        with open(outbox_file, "r", encoding="utf-8") as f:
            outbox_content = f.read()
    assert_test(judge_email in outbox_content or "+919876500112" in outbox_content, "Simulated SMS/Outbox generated for approved Judge", "Checked outbox.log")
    
    # Step E: Approved Judge logs in and reaches /judge with empty states
    approved_judge_sess = requests.Session()
    r = approved_judge_sess.post(f"{BASE_URL}/auth/login", data={"email": judge_email, "password": judge_pwd}, allow_redirects=True)
    assert_test(r.status_code == 200 and "/judge" in r.url, "Approved Judge reaches /judge dashboard", f"URL: {r.url}")
    assert_test("Welcome to Your Judicial Bench" in r.text or "No Cases Allocated Yet" in r.text, "Judge dashboard displays friendly empty state", "Checked empty state UI")

    # -------------------------------------------------------------
    # 6. ACCOUNT LIFECYCLE FLOW: REGISTRAR REJECTION WITH REMARKS
    # -------------------------------------------------------------
    print("\n--- 6. Account Lifecycle: Registrar Registration -> Rejection with Reason ---")
    reg_email = f"qa_reg_{int(time.time())}@nyaya.in"
    reg_pwd = "TestReg@123"
    
    # Register as Registrar
    reg_signup_data = {
        "full_name": "Shri QA Defective",
        "email": reg_email,
        "phone": "+919876500999",
        "password": reg_pwd,
        "confirm_password": reg_pwd,
        "role": "registrar",
        "court_id": "2",
        "court_name": "Patiala House District Courts Complex",
        "designation": "Deputy Registrar",
        "employee_id": "EMP-REG-INVALID",
        "years_service": "5",
        "language_pref": "en"
    }
    r = signup_sess.post(f"{BASE_URL}/auth/register", data=reg_signup_data, allow_redirects=True)
    assert_test(r.status_code == 200, "Registrar Registration submitted", f"Status: {r.status_code}")
    
    # Gov admin rejects
    r = gov_sess.get(f"{BASE_URL}/api/gov/approvals")
    approvals_data = r.json()
    reg_req = next((item for item in approvals_data.get("requests", []) if (item.get("email") == reg_email or item.get("applicant_email") == reg_email)), None)
    assert_test(reg_req is not None, "Gov Admin finds Registrar Request", f"Found: {reg_req is not None}")
    
    if reg_req:
        rejection_reason = "Defective Bar Council & Identity credentials."
        action_res = gov_sess.post(f"{BASE_URL}/api/gov/approvals/{reg_req['id']}/action", json={"action": "reject", "remarks": rejection_reason})
        assert_test(action_res.status_code == 200 and action_res.json().get("success"), "Gov Admin rejects Registrar with remarks", f"Resp: {action_res.text}")
        
    # Rejected Registrar tries to log in -> sees rejection reason
    rej_sess = requests.Session()
    r = rej_sess.post(f"{BASE_URL}/auth/login", data={"email": reg_email, "password": reg_pwd}, allow_redirects=True)
    assert_test("rejected" in r.text.lower() or "not approved" in r.text.lower() or "Defective" in r.text, "Rejected applicant sees rejection reason on status page", "Checked rejection UI")

    # -------------------------------------------------------------
    # 7. SECURITY: FILE UPLOAD RESTRICTION
    # -------------------------------------------------------------
    print("\n--- 7. Security: File Upload Whitelist Validation ---")
    clerk_sess = requests.Session()
    clerk_sess.post(f"{BASE_URL}/auth/login", data={"email": "clerk@nyaya.in", "password": "Clerk@12345"})
    
    # Attempt to upload dangerous .exe file
    files = {"file": ("malware.exe", b"MZDummyPayloadContent", "application/octet-stream")}
    data = {"case_id": "1", "doc_type": "Petition", "visibility": "Public"}
    r = clerk_sess.post(f"{BASE_URL}/api/clerk/documents/upload", files=files, data=data)
    assert_test(r.status_code == 400 and ("Invalid file" in r.text or "not permitted" in r.text), "Dangerous file extension (.exe) rejected with 400", f"Status: {r.status_code}, Resp: {r.text}")
    
    # Attempt to upload valid .pdf file
    valid_files = {"file": ("affidavit.pdf", b"%PDF-1.4 Mock Legal Content", "application/pdf")}
    r = clerk_sess.post(f"{BASE_URL}/api/clerk/documents/upload", files=valid_files, data=data)
    assert_test(r.status_code == 200 and r.json().get("success"), "Valid file extension (.pdf) accepted", f"Status: {r.status_code}")

    # -------------------------------------------------------------
    # 8. DEMO RESET ACTION VERIFICATION
    # -------------------------------------------------------------
    print("\n--- 8. Admin Reset Demo Database Verification ---")
    r = gov_sess.post(f"{BASE_URL}/api/admin/reset-demo")
    assert_test(r.status_code == 200 and r.json().get("success"), "POST /api/admin/reset-demo re-seeds database cleanly", f"Status: {r.status_code}, Resp: {r.text}")
    
    # Verify baseline metrics after reset
    r = gov_sess.get(f"{BASE_URL}/api/gov/analytics")
    data = r.json()
    assert_test(data.get("status_ratio", {}).get("pending", 0) > 0, "Post-reset database has all demo cases and records", f"Pending cases: {data.get('status_ratio', {}).get('pending')}")

    # -------------------------------------------------------------
    # FINAL SUMMARY
    # -------------------------------------------------------------
    print("\n" + "=" * 70)
    print(f"  TOTAL TESTS: {passed + failed} | PASSED: {passed} | FAILED: {failed}")
    print("=" * 70)
    return failed == 0

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
