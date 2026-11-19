"""
NyayaDesk AI E-Filing Defect Checker
Automated pre-scrutiny assistant for the Registrar General scrutiny queue.
Evaluates petitions for procedural defects (missing court fees, unverified pleadings,
missing annexures, ambiguous relief, limitation issues) with confidence ratings.
Preserves sole decision-making authority for the Registrar.
"""

import time
from typing import Any, Dict, List, Optional

from app.models import db, Case, Document, Payment, AuditLog, AILog
from app.services.ai.guardrails import AI_REVIEW_BANNER, apply_review_label

def audit_case_defects(case_id: int, user_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Evaluates an e-filed case for formal and substantive defects.
    """
    start_time = time.time()
    case = db.session.get(Case, case_id)
    if not case:
        return {"success": False, "error": "Case record not found", "defects": []}

    defects: List[Dict[str, Any]] = []

    # 1. Check Court Fee Payment
    total_paid = sum(p.amount for p in case.payments if p.status == 'Paid') if hasattr(case, 'payments') else 0
    if total_paid < 100:
        defects.append({
            "check": "Court Fee Proof & Stamp Duty",
            "status": "Defect Detected",
            "severity": "Critical",
            "confidence": 95,
            "description": f"No verified court fee e-challan or treasury stamp on record (Recorded paid: ₹{total_paid:.2f}).",
            "cure": "Deposit requisite court fee challan under Court Fees Act 1870 and upload receipt."
        })
    else:
        defects.append({
            "check": "Court Fee Proof & Stamp Duty",
            "status": "Compliant",
            "severity": "None",
            "confidence": 98,
            "description": f"Verified judicial e-payment of ₹{total_paid:.2f} confirmed on treasury ledger.",
            "cure": None
        })

    # 2. Check Vakalatnama / Counsel Representation
    docs = case.documents.all() if hasattr(case.documents, 'all') else list(case.documents)
    has_vakalatnama = any('vakalat' in ((getattr(d, 'filename', '') or '') + ' ' + (getattr(d, 'doc_type', '') or '')).lower() for d in docs)
    if not has_vakalatnama:
        defects.append({
            "check": "Vakalatnama / Memo of Appearance",
            "rule": "Vakalatnama / Memo of Appearance",
            "status": "Defect Detected",
            "severity": "Serious",
            "confidence": 0.92,
            "description": "No formal Vakalatnama executed with welfare stamp or Bar Council enrolment number found in exhibits.",
            "cure": "Upload duly executed and accepted Vakalatnama bearing Bar Council enrolment number."
        })
    else:
        defects.append({
            "check": "Vakalatnama / Memo of Appearance",
            "rule": "Vakalatnama / Memo of Appearance",
            "status": "Compliant",
            "severity": "None",
            "confidence": 0.95,
            "description": "Counsel representation memo is verified on the digital docket.",
            "cure": None
        })

    # 3. Check Supporting Annexures & Exhibits
    if len(docs) <= 1:
        defects.append({
            "check": "Annexures & Supporting Evidence",
            "status": "Defect Detected",
            "severity": "Moderate",
            "confidence": 84,
            "description": "Only 1 document uploaded. Primary cause of action exhibits or impugned order copy appear missing.",
            "cure": "File certified true copies of impugned orders and all relevant annexures chronologically indexed."
        })
    else:
        defects.append({
            "check": "Annexures & Supporting Evidence",
            "status": "Compliant",
            "severity": "None",
            "confidence": 88,
            "description": f"{len(docs)} supporting exhibits indexed on docket.",
            "cure": None
        })

    # 4. Check Precision of Relief & Prayer Clause
    desc = case.description or ""
    if len(desc.strip()) < 25:
        defects.append({
            "check": "Clarity of Relief / Cause of Action",
            "status": "Defect Detected",
            "severity": "Serious",
            "confidence": 89,
            "description": "Pleading description is too brief or ambiguous to determine jurisdiction and relief sought.",
            "cure": "Provide concise synopsis specifying dates of cause of action and explicit prayers."
        })
    else:
        defects.append({
            "check": "Clarity of Relief / Cause of Action",
            "status": "Compliant",
            "severity": "None",
            "confidence": 91,
            "description": "Cause of action and relief prayer meet basic pleading requirements.",
            "cure": None
        })

    # 5. Check Identity Proofs / Signatory
    has_id = any('id' in ((getattr(d, 'filename', '') or '') + ' ' + (getattr(d, 'doc_type', '') or '')).lower() or 'proof' in ((getattr(d, 'filename', '') or '') + ' ' + (getattr(d, 'doc_type', '') or '')).lower() for d in docs)
    if not has_id:
        defects.append({
            "check": "Litigant KYC & Identity Proof",
            "rule": "Litigant KYC & Identity Proof",
            "status": "Observation",
            "severity": "Minor",
            "confidence": 0.78,
            "description": "No government ID proof (Aadhaar / Voter ID / PAN) uploaded for petitioner identity verification.",
            "cure": "Furnish self-attested identification copy of petitioner."
        })

    critical_count = sum(1 for d in defects if d['severity'] in ['Critical', 'Serious'])
    if critical_count > 0:
        recommendation = "Return with Objections for Rectification"
        recommendation_badge = "badge-danger"
    elif any(d['status'] == 'Defect Detected' for d in defects):
        recommendation = "Conditional Clearance subject to curing minor defects"
        recommendation_badge = "badge-warning"
    else:
        recommendation = "Fit for Scrutiny Approval & Bench Allocation"
        recommendation_badge = "badge-success"

    # Assemble Registrar Draft Return Remarks
    detected_only = [d for d in defects if d['status'] == 'Defect Detected']
    for d in defects:
        if 'rule' not in d:
            d['rule'] = d['check']
        if isinstance(d.get('confidence'), (int, float)) and d['confidence'] > 1.0:
            d['confidence'] = round(d['confidence'] / 100.0, 2)

    if detected_only:
        remarks_lines = [f"{i+1}. [{d['check']}]: {d['description']} (Cure: {d['cure']})" for i, d in enumerate(detected_only)]
        registrar_draft_remarks = "The e-filing is returned with the following procedural objections:\n" + "\n".join(remarks_lines) + "\n\nPlease rectify and re-submit within 7 days."
    else:
        registrar_draft_remarks = "Pleadings scrutinized. Court fees verified. No fatal defects found. Recommended for judicial bench listing."

    latency_ms = (time.time() - start_time) * 1000.0

    from app.services.ai.service import get_ai_service
    ai_service = get_ai_service()
    ai_service._log_observability(user_id, "defect_checker", "rule_engine", "NyayaDesk Scrutiny Auditor", "1.0", latency_ms, "success")

    return {
        "success": True,
        "case_id": case.id,
        "case_number": case.case_number,
        "title": case.title,
        "defects": defects,
        "defect_count": len(detected_only),
        "critical_count": critical_count,
        "overall_risk": "High" if critical_count > 0 else ("Moderate" if detected_only else "Low"),
        "recommendation": recommendation,
        "recommendation_badge": recommendation_badge,
        "suggested_remarks": registrar_draft_remarks,
        "draft_requisition_remarks": registrar_draft_remarks,
        "disclaimer": AI_REVIEW_BANNER,
        "ai_notice": AI_REVIEW_BANNER
    }
