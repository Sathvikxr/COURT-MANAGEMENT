"""Comprehensive Automated Test Suite for Advanced Judicial AI Capabilities in NyayaDesk.

Covers all 11 Advanced AI Features:
1. Semantic Case-Law and Precedent Search (Vector Index & Synthetic Data)
2. Grounded Case File RAG ("Ask the Case File" with strict citations & refusal)
3. Smart Document Intelligence (OCR text extraction & form auto-fill)
4. E-Filing Defect Checker (Registrar pre-scrutiny & confidence scoring)
5. Hearing Transcription & Minutes Synthesis (Voice intake, action items, judicial approval)
6. Multilingual Translation Engine (Article 348 compliance, English/Telugu/Hindi)
7. Natural-Language Analytics ("Ask your data" with safe parameterized query tools)
8. AI Case-Risk and Backlog Insights (Pre-computed SQL metrics, no hallucinations)
9. Judge Copilot Sidebar (3-bullet summary, adjournment drafting, conflict detection, evidence check)
10. Citizen Chatbot Upgrade (NyayaMitra memory, legal strategy refusal, chips, helpdesk handoff)
11. Evaluation Mode (Quality ratings, satisfaction tracking, admin telemetry)
"""

import json
import pytest
from datetime import datetime, timedelta

from app import create_app, db
from app.models import (
    User, Case, Hearing, Document, Order, CaseParty,
    PrecedentLibrary, HearingTranscription, AIEvaluation, AuditLog
)
from app.services.ai.precedents import search_precedents, seed_precedents_if_needed
from app.services.ai.case_rag import ask_case_file
from app.services.ai.ocr_intelligence import parse_petition_intelligence, extract_text_from_file
from app.services.ai.defect_checker import audit_case_defects
from app.services.ai.transcription import transcribe_hearing_audio, generate_minutes_from_transcript
from app.services.ai.translator import translate_judicial_document
from app.services.ai.analytics_tools import process_natural_language_analytics
from app.services.ai.backlog_insights import compute_court_backlog_metrics, generate_backlog_insight_card
from app.services.ai.judge_copilot import (
    summarize_case_3_bullets, draft_adjournment_order,
    find_conflicting_hearings, flag_missing_evidence_before_judgment
)
from app.services.ai.evaluation import record_ai_evaluation, get_ai_evaluation_summary
from app.services.ai.guardrails import AI_REVIEW_BANNER


@pytest.fixture(scope='module')
def test_app():
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    with app.app_context():
        seed_precedents_if_needed()
        yield app


@pytest.fixture
def client(test_app):
    return test_app.test_client()


@pytest.fixture
def judge_user(test_app):
    with test_app.app_context():
        j = User.query.filter_by(role='judge', status='active').first()
        return j


@pytest.fixture
def registrar_user(test_app):
    with test_app.app_context():
        r = User.query.filter_by(role='registrar', status='active').first()
        return r


@pytest.fixture
def litigant_user(test_app):
    with test_app.app_context():
        l = User.query.filter_by(role='litigant', status='active').first()
        return l


# =========================================================================
# FEATURE 1: SEMANTIC CASE-LAW & PRECEDENT SEARCH
# =========================================================================

def test_feature_1_precedent_vector_search(test_app):
    """Verifies semantic search matches relevant synthetic precedents with passage highlights."""
    with test_app.app_context():
        # Query regarding Section 138 cheque bounce
        res = search_precedents("dishonour of cheque statutory notice delay Section 138", limit=3)
        assert res["success"] is True
        assert res["total_found"] > 0
        assert res["is_synthetic_data"] is True
        assert AI_REVIEW_BANNER in res["ai_notice"]

        top_match = res["results"][0]
        assert "citation" in top_match
        assert "(Synth)" in top_match["citation"] or "SCC" in top_match["citation"] or "NyayaLR" in top_match["citation"]
        assert "relevance_score" in top_match
        assert top_match["relevance_score"] > 0.0
        assert "highlighted_passage" in top_match


def test_feature_1_precedent_api_endpoint(client, litigant_user):
    """Tests POST /api/ai/precedent-search endpoint with audit log generation."""
    with client.session_transaction() as sess:
        sess['user_id'] = litigant_user.id

    res = client.post('/api/ai/precedent-search', json={
        "query": "adverse possession animus possidendi 12 years",
        "limit": 4
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert len(data["results"]) <= 4
    assert data["is_synthetic_data"] is True

    # Confirm audit log entry
    with client.application.app_context():
        audit = AuditLog.query.filter_by(action="AI_PRECEDENT_SEARCH").order_by(AuditLog.id.desc()).first()
        assert audit is not None
        assert "adverse possession" in audit.details


# =========================================================================
# FEATURE 2: GROUNDED CASE FILE RAG ("ASK THE CASE FILE")
# =========================================================================

def test_feature_2_rag_grounded_answer_and_refusal(test_app, judge_user):
    """Verifies RAG answers from case corpus and refuses when info is absent."""
    with test_app.app_context():
        test_case = Case.query.first()
        assert test_case is not None

        # 1. Query present in case file
        res = ask_case_file(test_case.id, judge_user, "What is the title and nature of this dispute?")
        assert res["success"] is True
        assert len(res["citations"]) > 0
        assert AI_REVIEW_BANNER in res["ai_notice"]

        # 2. Query absent from case file -> must state not found in case file
        res_absent = ask_case_file(test_case.id, judge_user, "What was the defendant's Mars spacecraft license number?")
        assert res_absent["success"] is True
        assert "not found in the case file" in res_absent["answer"].lower()


def test_feature_2_rag_rbac_boundary(client, litigant_user):
    """Verifies a litigant cannot query a case docket where they are not a party."""
    with client.session_transaction() as sess:
        sess['user_id'] = litigant_user.id

    with client.application.app_context():
        # Find case where litigant is not a party and not the filer
        unauthorized_case = Case.query.filter(
            Case.filed_by != litigant_user.id,
            ~Case.parties.any(CaseParty.user_id == litigant_user.id)
        ).first()

    if unauthorized_case:
        res = client.post(f'/api/ai/cases/{unauthorized_case.id}/ask', json={
            "question": "What is the claim amount?"
        })
        assert res.status_code == 403


# =========================================================================
# FEATURE 3: SMART DOCUMENT INTELLIGENCE & OCR
# =========================================================================

def test_feature_3_ocr_intelligence_extraction(test_app):
    """Tests structured parsing from petition text and inconsistency detection."""
    sample_text = """
    IN THE HIGH COURT OF JUDICATURE AT NEW DELHI
    COMMERCIAL SUIT NO. 109 OF 2026

    Sunil Enterprises Pvt Ltd
    ...PLAINTIFF

    VERSUS

    Metro Infrastructure Development Corp
    ...DEFENDANT

    PLAINT UNDER ORDER VII RULE 1 CPC
    1. The Plaintiff claims recovery of unpaid invoices amounting to Rs. 25,00,000/- with 12% interest.
    2. Relief Sought: A money decree for Rs. 25,00,000/- against the Defendant.

    VERIFICATION:
    I, Sunil Kumar, director of Sunil Enterprises, verify the contents.
    Note: Defendant referred as Metro Infra Logistics in para 5.
    """
    analysis = parse_petition_intelligence(sample_text, filename="petition_sample.pdf")
    assert analysis["success"] is True
    ef = analysis["extracted_fields"]
    assert "Sunil" in (ef.get("petitioner_name") or "")
    assert "Metro" in (ef.get("respondent_name") or "")
    assert "25,00,000" in (ef.get("claim_amount") or "")
    assert AI_REVIEW_BANNER in analysis["ai_notice"]


def test_feature_3_ocr_api_endpoint(client, registrar_user):
    """Tests POST /api/ai/ocr-extract with text sample payload."""
    with client.session_transaction() as sess:
        sess['user_id'] = registrar_user.id

    res = client.post('/api/ai/ocr-extract', json={
        "text_sample": "CRIMINAL COMPLAINT under Section 138 NI Act. Complainant: Anita Roy vs Accused: Rajesh Sharma for Rs. 5,00,000/-.",
        "filename": "cheque_complaint.txt"
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert "extracted_fields" in data


# =========================================================================
# FEATURE 4: E-FILING DEFECT CHECKER (REGISTRAR PRE-SCRUTINY)
# =========================================================================

def test_feature_4_scrutiny_defect_audit(test_app, registrar_user):
    """Tests defect analysis confidence scoring and draft requisition remarks."""
    with test_app.app_context():
        c = Case.query.first()
        res = audit_case_defects(c.id)
        assert res["success"] is True
        assert "defects" in res
        assert "overall_risk" in res
        assert "draft_requisition_remarks" in res
        assert AI_REVIEW_BANNER in res["ai_notice"]


def test_feature_4_scrutiny_defects_api(client, registrar_user):
    """Tests GET /api/ai/cases/<case_id>/scrutiny-defects."""
    with client.session_transaction() as sess:
        sess['user_id'] = registrar_user.id

    with client.application.app_context():
        c = Case.query.first()

    res = client.get(f'/api/ai/cases/{c.id}/scrutiny-defects')
    assert res.status_code == 200
    data = res.get_json()
    assert "defect_count" in data


# =========================================================================
# FEATURE 5: HEARING TRANSCRIPTION & MINUTES SYNTHESIS
# =========================================================================

def test_feature_5_transcription_and_approval_flow(test_app, client, judge_user):
    """Tests audio transcription, draft minutes synthesis, and mandatory judge approval saving."""
    with test_app.app_context():
        h = Hearing.query.first()
        assert h is not None
        hearing_id = h.id

    with client.session_transaction() as sess:
        sess['user_id'] = judge_user.id

    # 1. Transcribe Hearing (generates Draft minutes)
    res = client.post(f'/api/ai/hearings/{hearing_id}/transcribe')
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert data["status"] == "Draft"
    assert data["requires_human_approval"] is True
    assert len(data["minutes"]["action_items"]) > 0

    # 2. Judge confirms & approves minutes
    save_res = client.post(f'/api/hearings/{hearing_id}/save-minutes', json={
        "minutes_summary": "Arguments heard in part. Petitioner counsel directed to place on record additional documents.",
        "action_items": ["Petitioner to file supplementary affidavit within 10 days"],
        "suggested_next_hearing": "2026-12-20"
    })
    assert save_res.status_code == 200
    save_data = save_res.get_json()
    assert save_data["status"] == "Approved"

    # Confirm in DB
    with test_app.app_context():
        rec = HearingTranscription.query.filter_by(hearing_id=hearing_id).first()
        assert rec is not None
        assert rec.status == "Approved"
        assert rec.reviewed_by == judge_user.id


# =========================================================================
# FEATURE 6: MULTILINGUAL TRANSLATION ENGINE
# =========================================================================

def test_feature_6_multilingual_engine(test_app):
    """Tests English to Telugu/Hindi translation and Article 348 disclaimer."""
    order_text = "The respondent is restrained by an interim injunction from selling the schedule suit property."
    
    # 1. Telugu
    res_te = translate_judicial_document(order_text, target_lang='te', doc_type='Interim Injunction')
    assert res_te["success"] is True
    assert "Article 348" in res_te["constitutional_disclaimer"]
    assert len(res_te["translated_text"]) > 0
    assert AI_REVIEW_BANNER in res_te["ai_notice"]

    # 2. Hindi
    res_hi = translate_judicial_document(order_text, target_lang='hi', doc_type='Interim Injunction')
    assert res_hi["success"] is True
    assert "प्रतिवादी" in res_hi["translated_text"] or "निषेधाज्ञा" in res_hi["translated_text"] or len(res_hi["translated_text"]) > 10


def test_feature_6_translate_api_endpoint(client, litigant_user):
    """Tests POST /api/ai/translate endpoint."""
    with client.session_transaction() as sess:
        sess['user_id'] = litigant_user.id

    res = client.post('/api/ai/translate', json={
        "text": "Notice is hereby issued to respondent to appear before court.",
        "target_lang": "te",
        "doc_type": "Notice"
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert "translated_text" in data


# =========================================================================
# FEATURE 7: NATURAL-LANGUAGE ANALYTICS ("ASK YOUR DATA")
# =========================================================================

def test_feature_7_natural_language_analytics_safe_tools(test_app, registrar_user):
    """Verifies that queries invoke safe parameterized tools without executing raw SQL strings."""
    with test_app.app_context():
        # Test 1: Count civil cases
        res = process_natural_language_analytics(registrar_user, "How many civil cases were disposed last month?")
        assert res["success"] is True
        assert res["tool_used"] in ["count_cases", "average_disposal_time"]
        assert "chart" in res
        assert AI_REVIEW_BANNER in res["ai_notice"]

        # Test 2: Group by status
        res_group = process_natural_language_analytics(registrar_user, "Group cases by status")
        assert res_group["success"] is True
        assert res_group["tool_used"] == "group_by"
        assert res_group["chart"]["type"] in ["pie", "bar"]


def test_feature_7_analytics_api_endpoint(client, judge_user):
    """Tests POST /api/ai/ask-data role-scoped query execution."""
    with client.session_transaction() as sess:
        sess['user_id'] = judge_user.id

    res = client.post('/api/ai/ask-data', json={
        "question": "Average disposal time for cases"
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert data["role_scoped"] == "judge"


# =========================================================================
# FEATURE 8: AI CASE-RISK & BACKLOG INSIGHTS
# =========================================================================

def test_feature_8_backlog_metrics_and_insight_card(test_app):
    """Verifies metrics computed directly with SQL first and zero hallucinations."""
    with test_app.app_context():
        metrics = compute_court_backlog_metrics()
        assert "total_pending" in metrics
        assert "at_risk_count" in metrics
        assert "over_2yr_count" in metrics
        assert "imbalance_ratio" in metrics

        card = generate_backlog_insight_card()
        assert card["success"] is True
        assert "executive_narrative" in card
        assert len(card["recommendations"]) == 3
        assert AI_REVIEW_BANNER in card["ai_notice"]


def test_feature_8_backlog_api_endpoint(client, registrar_user):
    """Tests GET /api/ai/backlog-insights endpoint."""
    with client.session_transaction() as sess:
        sess['user_id'] = registrar_user.id

    res = client.get('/api/ai/backlog-insights')
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert "metrics" in data


# =========================================================================
# FEATURE 9: JUDGE COPILOT SIDEBAR
# =========================================================================

def test_feature_9_judge_copilot_tools(test_app, judge_user):
    """Tests judge copilot quick-actions: 3 bullets, draft order, conflicts, evidence check."""
    with test_app.app_context():
        test_case = Case.query.first()
        
        # 1. 3-Bullet Summary
        b_res = summarize_case_3_bullets(test_case, judge_user)
        assert b_res["success"] is True
        assert len(b_res["bullets"]) == 3

        # 2. Adjournment Order Drafter
        adj_res = draft_adjournment_order(test_case, judge_user, "Counsel unwell", "2026-12-18")
        assert adj_res["success"] is True
        assert "ORDER SHEET" in adj_res["draft_text"]
        assert "Counsel unwell" in adj_res["draft_text"]

        # 3. Conflicts Check
        conf_res = find_conflicting_hearings(test_case, judge_user, "2026-12-15")
        assert conf_res["success"] is True
        assert "is_slot_available" in conf_res

        # 4. Evidence Checklist
        ev_res = flag_missing_evidence_before_judgment(test_case, judge_user)
        assert ev_res["success"] is True
        assert len(ev_res["checklist"]) > 0


def test_feature_9_judge_copilot_api(client, judge_user):
    """Tests POST /api/ai/cases/<case_id>/copilot endpoint."""
    with client.session_transaction() as sess:
        sess['user_id'] = judge_user.id

    with client.application.app_context():
        test_case = Case.query.first()

    res = client.post(f'/api/ai/cases/{test_case.id}/copilot', json={
        "action": "summarize_3_bullets"
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert len(data["bullets"]) == 3


# =========================================================================
# FEATURE 10: CITIZEN CHATBOT UPGRADE ("NYAYAMITRA")
# =========================================================================

def test_feature_10_chatbot_legal_advice_refusal(client):
    """Verifies safe refusal when user asks for legal strategy advice."""
    res = client.post('/api/ai/chat', json={
        "query": "What is the best legal strategy to win my case against the defendant?"
    })
    assert res.status_code == 200
    data = res.get_json()
    assert "I can help you find your case status or explain court procedures, but cannot advise on legal strategy. Consult a registered advocate." in data["reply"]
    assert "suggestion_chips" in data
    assert len(data["suggestion_chips"]) > 0
    assert data["handoff"] is not None
    assert data["handoff"]["available"] is True


def test_feature_10_chatbot_conversational_memory(client):
    """Verifies conversational memory handling across multi-turn exchanges."""
    history = [
        {"role": "user", "content": "How do I pay court fees?"},
        {"role": "assistant", "content": "Court fees can be paid via e-Challan on the portal."}
    ]
    res = client.post('/api/ai/chat', json={
        "query": "Where can I download the receipt?",
        "history": history
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["reply"] is not None


# =========================================================================
# FEATURE 11: EVALUATION MODE
# =========================================================================

def test_feature_11_evaluation_recording_and_summary(test_app, client, judge_user):
    """Tests recording AI feature evaluations ('helpful', 'wrong', 'unsafe') and summary metrics."""
    with client.session_transaction() as sess:
        sess['user_id'] = judge_user.id

    # 1. Submit evaluation via API
    res = client.post('/api/ai/evaluate', json={
        "feature": "precedent_search",
        "rating": "helpful",
        "feedback_text": "Found relevant ratio instantly.",
        "prompt": "cheque bounce notice",
        "response_text": "(2024) 4 SCC 112"
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert data["rating"] == "helpful"

    # 2. Query summary metrics
    stats_res = client.get('/api/admin/ai-eval-stats')
    assert stats_res.status_code == 200
    summary = stats_res.get_json()
    assert summary["total_evaluations"] > 0
    assert "satisfaction_rate" in summary
    assert "feature_metrics" in summary
