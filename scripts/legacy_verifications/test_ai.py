import os
os.environ['DISABLE_SQLALCHEMY_CEXT'] = '1'
import sys
sys.path.insert(0, r'C:\CourtMS')

from app import create_app
from app.models import db, User, Case, Hearing, Order, Document, AuditLog
from app.services.ai import (
    get_ai_mode,
    generate_case_summary,
    draft_judicial_order,
    citizen_legal_chat,
    calculate_case_priority,
    suggest_cause_list_ordering,
    suggest_smart_scheduling_slots,
    assess_delay_risk,
    find_similar_cases,
    auto_tag_document
)

app = create_app()

print("==================================================================")
print("  NyayaDesk CMS - AI Judicial Intelligence Verification Suite     ")
print("==================================================================")

with app.app_context():
    # ---------------------------------------------------------------------
    # Test 1: AI Mode Detection & Status Endpoint
    # ---------------------------------------------------------------------
    print("\n--- 1. Testing AI Mode Detection ---")
    mode, provider = get_ai_mode()
    print(f"Mode: {mode.upper()} | Provider: {provider}")
    assert mode in ['demo', 'live'], f"Unexpected AI mode: {mode}"
    print("✓ AI Mode detection verified.")

    # ---------------------------------------------------------------------
    # Test 2: Case Summarizer
    # ---------------------------------------------------------------------
    print("\n--- 2. Testing Case Summarizer ---")
    target_case = Case.query.first()
    assert target_case is not None, "No cases found in DB for testing"
    print(f"Testing summary for Case #{target_case.id} ({target_case.case_number}): {target_case.title}")

    summary_res = generate_case_summary(target_case.id, user_id=None)
    assert summary_res.get('success') is True, f"Summary failed: {summary_res}"
    summary = summary_res.get('summary', {})
    print(f"  Facts: {summary.get('facts')[:75]}...")
    print(f"  Parties Count: {len(summary.get('parties', []))}")
    print(f"  Timeline Events: {len(summary.get('timeline', []))}")
    print(f"  Key Legal Issues: {len(summary.get('issues', []))}")
    print(f"  Next Steps: {len(summary.get('next_steps', []))}")
    assert len(summary.get('facts', '')) > 10, "Summary facts missing"
    assert len(summary.get('issues', [])) > 0, "Summary issues missing"
    print("✓ Case Summarizer brief generated successfully!")

    # ---------------------------------------------------------------------
    # Test 3: Order Drafting Assistant
    # ---------------------------------------------------------------------
    print("\n--- 3. Testing Order Drafting Assistant ---")
    draft_res = draft_judicial_order(
        case_id=target_case.id,
        hearing_notes="Both parties appeared. Respondent requests 2 weeks for reply. Interim injunction continued.",
        order_type="Interim Injunction",
        user_id=None
    )
    assert draft_res.get('success') is True, f"Draft failed: {draft_res}"
    print(f"  Draft Title: {draft_res.get('title')}")
    print(f"  Draft Preview: {draft_res.get('content')[:120]}...")
    assert "Interim Injunction" in draft_res.get('title') or "Interim" in draft_res.get('title')
    assert len(draft_res.get('content', '')) > 50
    print("✓ Order Drafting Assistant synthesized draft order successfully!")

    # ---------------------------------------------------------------------
    # Test 4: Citizen Legal Help Chatbot (Multilingual & Case Status)
    # ---------------------------------------------------------------------
    print("\n--- 4. Testing Citizen Legal Chatbot (English, Telugu, Hindi) ---")
    litigant = User.query.filter_by(role='litigant').first()
    assert litigant is not None, "No litigant found"

    # English query
    chat_en = citizen_legal_chat("How do I file a bail application?", user_id=litigant.id, language='en')
    print(f"  [EN] Answer: {chat_en['reply'][:100]}...")
    assert "bail" in chat_en['reply'].lower() or "439" in chat_en['reply'] or "court" in chat_en['reply'].lower()
    assert "legal advice" in chat_en['disclaimer'].lower()

    # Telugu query
    chat_te = citizen_legal_chat("బెయిల్ దరఖాస్తు ఎలా దాఖలు చేయాలి?", user_id=litigant.id, language='te')
    print(f"  [TE] Answer: {chat_te['reply'][:100]}...")
    assert len(chat_te['reply']) > 20

    # Hindi query
    chat_hi = citizen_legal_chat("जमानत याचिका कैसे दायर करें?", user_id=litigant.id, language='hi')
    print(f"  [HI] Answer: {chat_hi['reply'][:100]}...")
    assert len(chat_hi['reply']) > 20

    # Litigant status inquiry
    chat_status = citizen_legal_chat("What is the status of my case?", user_id=litigant.id, language='en')
    print(f"  [Case Status Inquiry] Answer: {chat_status['reply'][:120]}...")
    assert len(chat_status['reply']) > 20
    print("✓ Citizen Legal Help Chatbot passed all multilingual & case lookup checks!")

    # ---------------------------------------------------------------------
    # Test 5: Case Priority Scoring
    # ---------------------------------------------------------------------
    print("\n--- 5. Testing Case Priority Scoring Engine ---")
    p_res = calculate_case_priority(target_case.id)
    assert p_res.get('success') is True, f"Priority calc failed: {p_res}"
    print(f"  Score: {p_res.get('priority_score')}/100")
    print(f"  Badge Label: {p_res.get('badge_label')}")
    print(f"  Color: {p_res.get('badge_color')}")
    print(f"  Factors: {p_res.get('factors')}")
    assert 0 <= p_res.get('priority_score') <= 100
    assert p_res.get('badge_label') in ['Critical', 'High Priority', 'Moderate', 'Standard']
    print("✓ Case Priority Scoring verified!")

    # ---------------------------------------------------------------------
    # Test 6: Suggested Cause List Ordering for Judges
    # ---------------------------------------------------------------------
    print("\n--- 6. Testing Suggested Cause List Ordering ---")
    judge = User.query.filter_by(role='judge').first()
    cause_order = suggest_cause_list_ordering(judge_id=judge.id)
    assert cause_order.get('success') is True, f"Cause ordering failed: {cause_order}"
    ordered_hearings = cause_order.get('ordered_hearings', [])
    print(f"  Hearings sequenced: {len(ordered_hearings)}")
    if ordered_hearings:
        first_h = ordered_hearings[0]
        print(f"  Top hearing item: {first_h['case_number']} - Score: {first_h['priority_score']} ({first_h['badge_label']})")
    print("✓ Suggested Cause List Ordering verified!")

    # ---------------------------------------------------------------------
    # Test 7: Smart Scheduling Suggestions
    # ---------------------------------------------------------------------
    print("\n--- 7. Testing Smart Scheduling Suggestions ---")
    courtroom = target_case.court.courtrooms[0] if target_case.court and target_case.court.courtrooms else None
    courtroom_id = courtroom.id if courtroom else None
    slots_res = suggest_smart_scheduling_slots(
        case_id=target_case.id,
        judge_id=target_case.judge_id or judge.id,
        courtroom_id=courtroom_id,
        days_ahead=14
    )
    assert slots_res.get('success') is True, f"Slot suggestion failed: {slots_res}"
    slots = slots_res.get('slots', [])
    print(f"  Generated conflict-free slots: {len(slots)}")
    for i, s in enumerate(slots, 1):
        print(f"    Slot {i}: {s['display']} (Score: {s['score']}, Reason: {s['reason']})")
    assert len(slots) >= 1, "At least one scheduling slot expected"
    print("✓ Smart Scheduling Suggestions verified!")

    # ---------------------------------------------------------------------
    # Test 8: Delay Risk Indicator
    # ---------------------------------------------------------------------
    print("\n--- 8. Testing Delay Risk Indicator ---")
    delay_info = assess_delay_risk(target_case.id)
    print(f"  Adjournments: {delay_info.get('adjournment_count')}")
    print(f"  Risk Level: {delay_info.get('risk_level')}")
    print(f"  Badge Label: {delay_info.get('badge_label')}")
    print(f"  Explanation: {delay_info.get('tooltip')}")
    assert delay_info.get('risk_level') in ['low', 'moderate', 'high']
    print("✓ Delay Risk Indicator verified!")

    # ---------------------------------------------------------------------
    # Test 9: Similar Case Finder (TF-IDF Cosine Similarity)
    # ---------------------------------------------------------------------
    print("\n--- 9. Testing Similar Case Finder ---")
    similar_res = find_similar_cases(target_case.id, top_n=3)
    assert similar_res.get('success') is True, f"Similar case search failed: {similar_res}"
    matches = similar_res.get('similar_cases', [])
    print(f"  Method Used: {similar_res.get('method')}")
    print(f"  Found {len(matches)} similar precedents:")
    for m in matches:
        print(f"    - [{m['case_number']}] {m['title']} | Similarity: {m['similarity_score']}% ({m['match_quality']})")
    assert len(matches) <= 3
    print("✓ Similar Case Finder verified!")

    # ---------------------------------------------------------------------
    # Test 10: Document Auto-Tagging & Entity Extraction
    # ---------------------------------------------------------------------
    print("\n--- 10. Testing Document Auto-Tagging ---")
    sample_text = (
        "IN THE COURT OF CHIEF METROPOLITAN MAGISTRATE, NEW DELHI\n"
        "COMPLAINT UNDER SECTION 138 OF NEGOTIABLE INSTRUMENTS ACT, 1881\n"
        "CASE NO: CC/2026/00142\n"
        "M/S ABC TRADERS ... COMPLAINANT\n"
        "VERSUS\n"
        "XYZ INFRASTRUCTURE PVT LTD ... ACCUSED\n"
        "Cheque bearing no. 482019 dated 15/09/2025 for Rs. 25,00,000 returned unpaid with remarks Funds Insufficient.\n"
        "Legal notice issued on 01/10/2025."
    )
    tag_res = auto_tag_document(sample_text, filename="cheque_dishonour_complaint_signed.pdf")
    assert tag_res.get('success') is True, f"Tagging failed: {tag_res}"
    print(f"  Suggested Doc Type: {tag_res.get('suggested_doc_type')} ({tag_res.get('confidence')}%)")
    print(f"  Identified Acts/Sections: {tag_res.get('identified_acts')}")
    print(f"  Extracted Case Numbers: {tag_res.get('extracted_case_numbers')}")
    print(f"  Extracted Monetary Amounts: {tag_res.get('extracted_amounts')}")
    print(f"  Extracted Dates: {tag_res.get('extracted_dates')}")
    assert tag_res.get('suggested_doc_type') in ['Petition / Complaint', 'Affidavit', 'Notice', 'Order / Judgment']
    assert len(tag_res.get('identified_acts', [])) > 0
    print("✓ Document Auto-Tagging & Entity Extraction verified!")

    # ---------------------------------------------------------------------
    # Test 11: Audit Trail Verification
    # ---------------------------------------------------------------------
    print("\n--- 11. Testing AI Audit Trail Logging ---")
    recent_ai_logs = AuditLog.query.filter(AuditLog.action.ilike('%ai%')).order_by(AuditLog.id.desc()).limit(10).all()
    print(f"  Recent AI Audit Log Count: {len(recent_ai_logs)}")
    for l in recent_ai_logs[:5]:
        print(f"    - Action: {l.action} | Entity: {l.entity} ({l.entity_id}) | Details: {l.details}")
    assert len(recent_ai_logs) > 0, "Expected AI operations to be recorded in audit_logs"
    print("✓ AI Audit Logging verified!")

# -------------------------------------------------------------------------
# Test 12: Flask REST API Endpoints via Test Client
# -------------------------------------------------------------------------
print("\n--- 12. Testing Flask REST API Endpoints ---")
with app.test_client() as client:
    # Authenticate as Judge for RBAC protected endpoints
    login_resp = client.post('/auth/login', data={'email': 'judge1@nyaya.in', 'password': 'Judge@12345'})
    assert login_resp.status_code == 302, f"Judge login failed: {login_resp.status_code}"

    # 1. AI Status
    res = client.get('/api/ai/status')
    assert res.status_code == 200
    data = res.get_json()
    assert 'mode' in data
    print("  ✓ GET /api/ai/status -> 200 OK")

    # 2. Case Summary API
    res = client.get('/api/ai/summary/1')
    assert res.status_code == 200
    data = res.get_json()
    assert 'summary' in data
    print("  ✓ GET /api/ai/summary/1 -> 200 OK")

    # 3. Order Draft API
    res = client.post('/api/ai/order-draft', json={
        'case_id': 1,
        'order_type': 'Interim Order',
        'notes': 'Hearing proceeded. Time granted for counter.'
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data.get('success') is True
    print("  ✓ POST /api/ai/order-draft -> 200 OK")

    # 4. Chat API
    res = client.post('/api/ai/chat', json={
        'query': 'How do I file a bail application?',
        'language': 'en'
    })
    assert res.status_code == 200
    data = res.get_json()
    assert 'reply' in data
    print("  ✓ POST /api/ai/chat -> 200 OK")

    # 5. Priority API
    res = client.get('/api/ai/priority/1')
    assert res.status_code == 200
    data = res.get_json()
    assert 'priority' in data
    print("  ✓ GET /api/ai/priority/1 -> 200 OK")

    # 6. Cause List Ordering API
    res = client.get('/api/ai/cause-list-ordering')
    assert res.status_code == 200
    data = res.get_json()
    assert 'hearings' in data
    print("  ✓ GET /api/ai/cause-list-ordering -> 200 OK")

    # 7. Smart Schedule Slots API
    res = client.get('/api/ai/smart-schedule-slots?case_id=1')
    assert res.status_code == 200
    data = res.get_json()
    assert 'slots' in data
    print("  ✓ GET /api/ai/smart-schedule-slots -> 200 OK")

    # 8. Similar Cases API
    res = client.get('/api/ai/similar-cases/1')
    assert res.status_code == 200
    data = res.get_json()
    assert 'similar_cases' in data
    print("  ✓ GET /api/ai/similar-cases/1 -> 200 OK")

    # 9. Auto Tag API
    res = client.post('/api/ai/auto-tag', json={
        'filename': 'notice_sec_138.pdf',
        'text_content': 'Notice under section 138 of negotiable instruments act'
    })
    assert res.status_code == 200
    data = res.get_json()
    assert 'suggested_doc_type' in data
    print("  ✓ POST /api/ai/auto-tag -> 200 OK")

print("\n==================================================================")
print("  ALL 12 AI VERIFICATION CHECKS PASSED WITH ZERO ERRORS!          ")
print("==================================================================")
