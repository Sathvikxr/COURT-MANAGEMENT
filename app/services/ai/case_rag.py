"""
NyayaDesk Grounded Retrieval-Augmented Generation (RAG) - "Ask the Case File"
Permits Judges, Clerks, and Case Advocates to query the judicial record.
Answers strictly from verified pleadings, documents, orders, and hearings
with exact citations, responding "not found in the case file" rather than guessing.
"""

import re
import time
from typing import Any, Dict, List, Optional
from flask import request

from app.models import db, Case, Document, Order, Hearing, AuditLog, AILog
from app.services.ai.guardrails import apply_review_label, wrap_untrusted_data, redact_pii, restore_pii, AI_REVIEW_BANNER
from app.services.ai.gemini_provider import GeminiProvider

NOT_FOUND_MESSAGE = "The requested information was not found in the case file records on record."

def ask_case_file(case_id: int, user: Any = None, query: str = None, question: str = None, **kwargs) -> Dict[str, Any]:
    """
    Grounded RAG query engine for a specific case docket.
    Strictly answers from case pleadings, orders, and hearings with citations.
    """
    start_time = time.time()

    # Handle parameter order interchangeability (case_id, user, query) vs (case_id, query, user)
    if isinstance(user, str) and (query is None or hasattr(query, 'role') or hasattr(query, 'is_authenticated')):
        user, query = query, user

    actual_query = (query or question or kwargs.get('q') or '').strip()
    if not actual_query:
        return {"success": False, "error": "Query cannot be empty", "answer": ""}

    case = db.session.get(Case, case_id)
    if not case:
        return {"success": False, "error": "Case not found", "answer": ""}

    # Strict RBAC verification
    if user and hasattr(user, 'role') and user.role in ['litigant', 'lawyer']:
        is_party = False
        if case.filed_by == user.id:
            is_party = True
        else:
            for p in case.parties:
                if p.user_id == user.id or p.advocate_id == user.id or (p.email and p.email.lower() == (user.email or '').lower()):
                    is_party = True
                    break
        if not is_party:
            return {
                "success": False,
                "error": "Access restricted: You are not an enrolled party or advocate on this docket.",
                "answer": "Not found in your authorized case file.",
                "citations": []
            }

    # 1. Assemble verified docket corpus
    records: List[Dict[str, str]] = []

    # Case Summary metadata
    records.append({
        "source": "Case Master Record",
        "title": f"Docket Metadata for {case.case_number}",
        "content": f"Case Number: {case.case_number}\nTitle: {case.title}\nType: {case.case_type}\nStatus: {case.status}\nFiling Date: {case.filed_on}\nDescription: {case.description or 'No formal description'}\nCourt: {case.court.name if case.court else 'Court'}"
    })

    # Parties
    party_lines = []
    for p in case.parties:
        party_lines.append(f"{p.party_type}: {p.name} (Phone: {p.phone or 'N/A'}, Email: {p.email or 'N/A'})")
    if party_lines:
        records.append({
            "source": "Pleadings - Memo of Parties",
            "title": "Parties and Advocates of Record",
            "content": "\n".join(party_lines)
        })

    # Documents
    for d in case.documents:
        fname = getattr(d, 'filename', 'Document')
        doctype = getattr(d, 'doc_type', 'General')
        up_date = d.uploaded_at.strftime('%d-%m-%Y') if d.uploaded_at else ''
        records.append({
            "source": f"Document: {fname} ({doctype})",
            "title": f"{fname} v{getattr(d, 'version', 1)}",
            "content": f"Document Name: {fname}\nDocument Type: {doctype}\nUploaded on: {up_date}"
        })

    # Orders
    for o in case.orders:
        otype = getattr(o, 'order_type', 'Judicial Order')
        otitle = getattr(o, 'title', 'Court Order')
        ocontent = getattr(o, 'content', '')
        iss_date = o.issued_at.strftime('%d-%m-%Y') if o.issued_at else ''
        records.append({
            "source": f"Judicial Order: {otype} dated {iss_date}",
            "title": otitle,
            "content": f"Order Title: {otitle}\nIssued Date: {iss_date}\nType: {otype}\nOperative Directives:\n{ocontent}\nVerification Code: {getattr(o, 'verification_code', 'N/A')}"
        })

    # Hearings
    for h in case.hearings:
        purp = getattr(h, 'purpose', 'Hearing')
        sched = h.scheduled_at.strftime('%d-%m-%Y') if h.scheduled_at else ''
        notes = getattr(h, 'notes', '') or getattr(h, 'adjournment_reason', '') or 'Proceeding ongoing'
        records.append({
            "source": f"Hearing Proceeding: {purp} ({sched})",
            "title": f"Status: {h.status}",
            "content": f"Scheduled: {sched}\nCourtroom: {h.courtroom.name if h.courtroom else 'Courtroom 1'}\nStatus: {h.status}\nOutcome / Notes: {notes}"
        })

    # 2. Query Grounding
    clean_q = actual_query.lower()
    from app.services.ai.service import get_ai_service
    ai_service = get_ai_service()
    provider = ai_service.get_active_provider()

    answer_text = ""
    citations: List[str] = []
    mode = 'demo'
    model_name = 'NyayaDesk Grounded Docket Search'

    if isinstance(provider, GeminiProvider):
        # Build prompt for live Gemini
        corpus_text = ""
        for r in records:
            corpus_text += f"\n--- START RECORD: {r['source']} ---\n{r['content']}\n--- END RECORD ---\n"

        system_instruction = (
            "You are a strict Court Record RAG assistant. You must answer questions solely and strictly "
            "from the provided verified case records. Under no circumstances may you extrapolate, infer, "
            "or invent facts not explicitly written in the records. If the answer is not stated in the record, "
            f"you must say exactly: '{NOT_FOUND_MESSAGE}'. "
            "Always cite the exact record source in brackets at the end of each statement e.g. [Citation: Document Name]."
        )
        safe_query = wrap_untrusted_data(actual_query, "CASE_INQUIRY")
        user_prompt = f"CASE RECORD DOCKET:\n{corpus_text}\n\nUSER QUESTION:\n{safe_query}\n\nProvide an objective, cited response."
        redacted_prompt, redaction_map = redact_pii(user_prompt)

        try:
            raw_answer = provider.generate_text(redacted_prompt, system_instruction=system_instruction)
            answer_text = restore_pii(raw_answer, redaction_map)
            mode = 'live'
            model_name = provider.model_name
        except Exception:
            answer_text = ""

    # Offline / Fallback Matcher
    if not answer_text:
        # Match keywords against records
        stop_words = {
            'what', 'when', 'where', 'which', 'who', 'how', 'the', 'and', 'case', 'file',
            'details', 'tell', 'show', 'status', 'defendant', 'defendants', 'plaintiff',
            'plaintiffs', 'petitioner', 'respondent', 'number', 'please', 'this', 'that', 'with'
        }
        q_words = set(re.findall(r'\b\w{3,}\b', clean_q)) - stop_words
        matched_passages = []

        if q_words:
            for r in records:
                c_lower = r['content'].lower()
                score = sum(1 for w in q_words if w in c_lower)
                if score > 0:
                    matched_passages.append((score, r))

            matched_passages.sort(key=lambda x: x[0], reverse=True)

        min_score = 1 if len(q_words) <= 1 else 2
        if matched_passages and matched_passages[0][0] >= min_score:
            top_record = matched_passages[0][1]
            citation = top_record['source']
            citations.append(citation)
            answer_text = f"According to the official docket records on file:\n\n{top_record['content']}\n\n[Citation: {citation}]"
            # Add secondary citation if relevant
            if len(matched_passages) > 1 and matched_passages[1][0] >= min_score:
                sec = matched_passages[1][1]
                citations.append(sec['source'])
                answer_text += f"\n\nAdditional finding:\n{sec['content'][:250]}...\n[Citation: {sec['source']}]"
        else:
            answer_text = NOT_FOUND_MESSAGE

    final_answer = apply_review_label(answer_text)

    # Observability Logging
    latency_ms = (time.time() - start_time) * 1000.0
    uid = user.id if user and hasattr(user, 'id') else None
    ai_service._log_observability(uid, "ask_case_file", provider.name, model_name, "1.0", latency_ms, "success")

    return {
        "success": True,
        "query": actual_query,
        "answer": final_answer,
        "citations": citations,
        "mode": mode,
        "model": model_name,
        "case_number": case.case_number,
        "disclaimer": AI_REVIEW_BANNER,
        "ai_notice": AI_REVIEW_BANNER
    }
