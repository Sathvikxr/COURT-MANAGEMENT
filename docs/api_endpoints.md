# NyayaDesk API Endpoints Reference

This document provides the exhaustive specification for all REST API endpoints implemented in **NyayaDesk**, organized by functional domain and role permissions.

All API routes return JSON responses with standard status codes (`200 OK`, `201 Created`, `400 Bad Request`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found`, `500 Internal Server Error`).

---

## Authentication & Session Management

Session authentication uses secure HTTP-only cookies (`HttpOnly=True`, `SameSite='Lax'`). API requests require an active authenticated user session with `status == 'active'`.

### `POST /auth/login`
- **Description:** Authenticates a user and initiates a session.
- **Payload (form-data or JSON):**
  ```json
  {
    "email": "judge1@nyaya.in",
    "password": "Judge@12345"
  }
  ```
- **Response:** Redirects to role dashboard or returns JSON error on invalid credentials.

### `GET /auth/logout`
- **Description:** Clears session and redirects to login.

### `POST /auth/register`
- **Description:** Submits a multi-role registration. Judges and Registrars are placed into `pending_gov` status; Clerks into `pending_registrar`.
- **Payload (multipart/form-data):** `full_name`, `email`, `phone`, `password`, `role`, `court_id`, `id_proof_no`, `designation`, `language_pref`, `id_proof_file`.

### `POST /auth/forgot-password`
- **Description:** Generates a simulated 6-digit OTP sent to the user's phone/email.

### `POST /auth/verify-otp`
- **Description:** Verifies the OTP code for password reset.

### `POST /auth/reset-password`
- **Description:** Updates password hash upon verified OTP.

---

## Public & General Endpoints

No login required.

### `GET /api/public/case-status`
- **Query Params:** `query` (Case Number e.g. `CIV/2026/00001` or CNR number)
- **Response `200`:**
  ```json
  {
    "success": true,
    "case": {
      "id": 1,
      "case_number": "CIV/2026/00001",
      "title": "State Bank of India vs Sharma Enterprises",
      "case_type": "Civil",
      "status": "Hearing",
      "court_name": "High Court of Judicature",
      "judge_name": "Hon'ble Justice Rajesh Sharma",
      "filed_on": "2026-01-15",
      "next_hearing": "2026-11-20 10:30:00"
    }
  }
  ```

### `GET /api/public/cause-list`
- **Query Params:** `court_id` (optional), `date` (YYYY-MM-DD, default today)
- **Response `200`:** Array of scheduled hearings with courtroom, judge, case number, and purpose.

### `GET /api/courts`
- **Response `200`:** List of all registered courts with city, state, code, and type.

### `GET /api/courtrooms`
- **Query Params:** `court_id`
- **Response `200`:** List of courtrooms and capacities for the court.

### `GET /api/judges`
- **Query Params:** `court_id` (optional)
- **Response `200`:** List of active judges with names and designations.

### `GET /orders/verify/<verification_code>`
- **Description:** Cryptographic verification endpoint validating digital order authenticity and SHA-256 integrity hash.

---

## Government Administration API (`role: government`)

### `GET /api/gov/analytics`
- **Description:** Real-time nationwide metrics, judicial disposal rates, court infrastructure, and pending cases.
- **Response `200`:**
  ```json
  {
    "success": true,
    "data": {
      "total_courts": 5,
      "total_courtrooms": 22,
      "total_judges": 8,
      "total_cases": 26,
      "pending_cases": 18,
      "disposed_cases": 6,
      "disposal_rate": 23.1,
      "pending_approvals": 2,
      "case_types": {"Civil": 8, "Criminal": 6, "Bail": 4, "Cheque Bounce": 3},
      "case_statuses": {"Hearing": 7, "Registered": 5, "Disposed": 6, "Reserved": 2}
    }
  }
  ```

### `GET /api/gov/approvals`
- **Description:** Lists all pending judicial approval requests.

### `POST /api/gov/approvals/<int:request_id>/action`
- **Payload:**
  ```json
  {
    "action": "approve",
    "remarks": "Verified credentials against Bar Council register."
  }
  ```
  *(or `"action": "reject"` with required remarks)*

### `POST /api/gov/approvals/bulk-approve`
- **Description:** Approves all pending judicial requests in a single transaction.

---

## Registrar General API (`role: registrar`)

### `GET /api/registrar/scrutiny`
- **Description:** Fetches all petitions in `Filed` or `Scrutiny` status awaiting procedural review.

### `POST /api/registrar/scrutiny/<int:case_id>/action`
- **Payload:**
  ```json
  {
    "action": "approve",
    "judge_id": 3,
    "remarks": "Defects cleared. Allocated to Courtroom 3."
  }
  ```
  *(or `"action": "defect"` with defect notice reasons)*

### `GET /api/registrar/analytics`
- **Description:** Pipeline status counts (Filed, Scrutiny, Registered, Hearing, Disposed), bench caseload distribution per judge, and unassigned count.

### `POST /api/registrar/cases/<int:case_id>/assign`
- **Payload:**
  ```json
  {
    "judge_id": 4,
    "courtroom_id": 2
  }
  ```

---

## Judicial Bench API (`role: judge`)

### `GET /api/judge/cause-list`
- **Description:** Returns today's active cause list for the presiding judge's bench.

### `GET /api/judge/analytics`
- **Description:** Bench caseload by case type, hearing outcomes distribution (Completed, Adjourned, Reserved), and total assigned vs disposed.

### `POST /api/judge/hearings/<int:hearing_id>/action`
- **Payload (Adjourn):**
  ```json
  {
    "action": "adjourn",
    "reason": "Counsel for respondent unwell",
    "next_date": "2026-11-28 11:00"
  }
  ```
- **Payload (Conclude / Reserve):**
  ```json
  {
    "action": "conclude",
    "notes": "Arguments concluded. Judgment reserved."
  }
  ```

### `POST /api/judge/orders/issue`
- **Payload:**
  ```json
  {
    "case_id": 1,
    "title": "Interim Injunction Order",
    "order_type": "Interim",
    "content": "Upon hearing counsel, the respondent is restrained..."
  }
  ```
- **Response `200`:** Returns order ID, SHA-256 signature hash, and verification code (`NYA-ORD-XXXX`).

### `POST /api/judge/orders/draft-ai`
- **Description:** AI-assisted order drafting from hearing notes and case facts.

---

## Court Master / Clerk API (`role: clerk`)

### `GET /api/clerk/cases`
- **Description:** Lists all cases registered or managed in the court.

### `POST /api/clerk/cases/register`
- **Payload:** Full case metadata, parties, priority, case type, and relief sought.

### `GET /api/clerk/scheduling-suggestions`
- **Query Params:** `judge_id`, `courtroom_id`
- **Description:** AI-powered 3 best conflict-free slots checking judge workload, courtroom bookings, and holidays.

### `POST /api/clerk/hearings/schedule`
- **Payload:**
  ```json
  {
    "case_id": 2,
    "judge_id": 3,
    "courtroom_id": 1,
    "scheduled_at": "2026-11-25 10:30",
    "purpose": "Final Arguments"
  }
  ```
- **Note:** Enforces 30-minute collision detection on both judge and courtroom before inserting.

### `POST /api/clerk/documents/upload`
- **Description:** Uploads case documents. Validates against allowed file extensions (`pdf`, `png`, `jpg`, `jpeg`, `docx`, `txt`), MIME types, and 16MB file limit. Double extensions (e.g. `.pdf.exe`) and directory traversal sequences are rejected.
- **Payload (multipart/form-data):** `file`, `case_id`, `document_type`, `title`.

### `POST /api/cases/<int:case_id>/documents`
- **Description:** Direct case document upload alias. Automatically increments document versioning (`v1`, `v2`, etc.).
- **Response `201`:** Document metadata including secure ID, SHA-256 hash, and version number.

### `GET /api/documents/<int:doc_id>/download`
- **Description:** Secure document download endpoint with IDOR authorization. Restricts access to authorized judicial personnel and designated case parties/advocates. Direct browsing of static upload directories is blocked with HTTP 403.

### `POST /api/clerk/notices/generate`
- **Description:** Produces formal court summons and notices with automatic print styling.

---

## Advocate / Legal Counsel API (`role: lawyer`)

### `GET /api/lawyer/cases`
- **Description:** Lists active client cases where the lawyer is designated counsel.

### `POST /api/lawyer/efiling`
- **Description:** Submits new petition online into the Registrar scrutiny queue.

---

## Litigant / Citizen API (`role: litigant`)

### `GET /api/litigant/cases`
- **Description:** Case portfolio for citizen petitioner or respondent, including progress stepper and countdown to hearing.

### `POST /api/litigant/pay-fee`
- **Payload:**
  ```json
  {
    "case_id": 1,
    "amount": 500.0,
    "purpose": "Court Fee"
  }
  ```
- **Response `200`:** Generates verified transaction reference (`TXN-NYA-XXXX`) and receipt record.

### `POST /api/payments/create`
- **Description:** Payment initiation alias accepting `case_id`, `amount`, and `purpose`.
- **Response `201`:** Transaction confirmation and payment ID.

### `GET /api/payments/<int:payment_id>/receipt`
- **Description:** Secure payment receipt download. Litigants and lawyers can only download receipts for cases they are party to (enforced via IDOR guard).

---

## Police & Investigating Agency API (`role: police`)

### `GET /api/police/dockets`
- **Description:** Criminal court dockets, FIR charge-sheet records, remand hearings, and witness summons.

### `POST /api/police/charge-sheet`
- **Payload:** Accused name, FIR number, police station, charges, case details.

---

## AI Judicial Intelligence Services

All AI endpoints feature graceful degradation (LIVE mode when `GEMINI_API_KEY` is present, DEMO offline heuristic engine by default). Every AI response contains the mandatory `ai_disclaimer: "⚖️ AI-generated, review before use"` notice and enforces RBAC isolation.

### `GET /api/cases/<int:case_id>/ai-summary`
- **Description:** Generates structured legal brief (Facts, Parties, Procedural Timeline, Issues, Next Steps).
- **Access:** Judge, Registrar, Clerk, Court Staff, and verified counsel/parties of the case.

### `GET /api/cases/<int:case_id>/similar`
- **Description:** Returns top similar precedent cases using TF-IDF cosine similarity.

### `GET /api/cases/<int:case_id>/delay-risk`
- **Description:** Computes adjournment probability score and explanatory risk factors.

### `POST /api/ai/chat` (Feature 10: "NyayaMitra" Citizen Legal Chatbot)
- **Description:** Multilingual conversational court assistant for citizens with session memory, suggestions chips, voice TTS/STT integration, safe legal advice refusal, and court helpdesk handoff.
- **Payload:**
  ```json
  {
    "message": "What documents do I need to file an eviction petition?",
    "lang": "en",
    "session_id": "session_abc123"
  }
  ```
- **Response `200`:**
  ```json
  {
    "reply": "To file an eviction petition, submit the original rental agreement, notice of termination...",
    "disclaimer": "⚖️ AI-generated, review before use",
    "chips": ["Case Status Search", "Court Fee Structure", "Download Vakalatnama"],
    "handoff_recommended": false
  }
  ```

### `POST /api/ai/precedent-search` (Feature 1: Semantic Case-Law Search)
- **Description:** Semantic vector search over 30 synthetic test precedents in the judicial legal library with TF-IDF cosine similarity matching, passage highlighting, and relevance scoring.
- **Payload:**
  ```json
  {
    "query": "dishonour of cheque statutory notice section 138 NI act",
    "limit": 5
  }
  ```
- **Response `200`:**
  ```json
  {
    "success": true,
    "count": 3,
    "results": [
      {
        "id": 12,
        "title": "K. Venkatesh vs Lakshmi Enterprises",
        "citation": "(2024) 2 DCR 450 (HC)",
        "court": "High Court of Telangana",
        "key_sections": "Section 138, Section 142 Negotiable Instruments Act",
        "similarity_score": 0.88,
        "summary": "Held that statutory notice sent by registered post...",
        "matching_passage": "Notice under section 138 delivered to registered address...",
        "is_synthetic": true
      }
    ],
    "disclaimer": "⚖️ AI-generated, review before use"
  }
  ```

### `POST /api/ai/cases/<int:case_id>/ask` (Feature 2: Grounded Case File RAG)
- **Description:** Grounded Retrieval-Augmented Generation assistant answering strictly from the verified case file (orders, hearings, pleadings, documents) with strict citations. Refuses to guess if data is absent.
- **Access:** Presiding Judges, Clerks, and verified advocates/litigants of the case only.
- **Payload:**
  ```json
  {
    "question": "What interim relief was granted on 15 March?"
  }
  ```
- **Response `200`:**
  ```json
  {
    "success": true,
    "answer": "Interim injunction restraining construction was granted on 15 March.",
    "citations": [
      {
        "source": "Order dated 15-03-2026",
        "reference": "Document #4 (Interim Order)",
        "snippet": "Parties directed to maintain status quo until next date..."
      }
    ],
    "disclaimer": "⚖️ AI-generated, review before use"
  }
  ```

### `POST /api/ai/ocr-extract` (Feature 3: Smart Document Intelligence & OCR Auto-Fill)
- **Description:** Scans petition PDFs/images (`pytesseract` with graceful fallback) to extract structured legal metadata (parties, sections, claim amount, relief sought) and detect discrepancies for clerk intake.
- **Payload (multipart/form-data):** `file` (PDF/PNG/JPG) or JSON: `{"text": "..."}`.
- **Response `200`:**
  ```json
  {
    "success": true,
    "extracted_fields": {
      "petitioner_name": "Ramesh Kumar",
      "respondent_name": "Suresh Rao",
      "case_type": "Civil",
      "acts_sections": "Section 138 NI Act",
      "claim_amount": 250000.0,
      "relief_sought": "Recovery of dishonoured cheque sum with 18% interest"
    },
    "discrepancies": [],
    "confidence_score": 0.94,
    "disclaimer": "⚖️ AI-generated, review before use"
  }
  ```

### `GET /api/ai/cases/<int:case_id>/scrutiny-defects` (Feature 4: E-Filing Defect Pre-Scrutiny Checker)
- **Description:** AI pre-scrutiny auditor for the Registrar queue. Analyzes case petitions against statutory compliance (court fee proof, signed Vakalatnama, numbered annexures, KYC documents, clear prayer).
- **Access:** Registrar, Government, Presiding Judge.
- **Response `200`:**
  ```json
  {
    "success": true,
    "overall_risk": "Medium",
    "defect_count": 1,
    "defects": [
      {
        "category": "Court Fee",
        "defect": "Proof of paid court fee receipt is missing from docket.",
        "confidence": "High",
        "statutory_rule": "Court Fees Act Section 4"
      }
    ],
    "suggested_remarks": "Defect 1: Produce valid e-challan or court fee stamp receipt within 7 days.",
    "disclaimer": "⚖️ AI-generated, review before use"
  }
  ```

### `POST /api/ai/hearings/<int:hearing_id>/transcribe` (Feature 5: Hearing Audio Transcription & Minutes)
- **Description:** Transcribes audio recordings (upload or browser microphone stream) using Whisper/Gemini/Offline engine, generating summarized minutes, actionable orders, and proposed next dates.
- **Access:** Judge, Registrar, Clerk.
- **Payload (multipart/form-data):** `audio` (WAV/MP3/WebM/OGG) or JSON: `{"simulated_audio": true}`.
- **Response `200`:**
  ```json
  {
    "success": true,
    "transcription_id": 14,
    "status": "Draft",
    "transcript": "Counsel for plaintiff submitted bank statement exhibits...",
    "minutes_summary": "Arguments heard on interim injunction application.",
    "action_items": [
      "Defendant to file reply to IA-2 within 2 weeks",
      "Registry to issue notice to Respondent 3"
    ],
    "suggested_next_hearing": "2026-12-10 10:30:00",
    "requires_judicial_approval": true,
    "disclaimer": "⚖️ AI-generated, review before use"
  }
  ```

### `POST /api/hearings/<int:hearing_id>/save-minutes` (Feature 5: Judicial Minutes Approval)
- **Description:** Human-in-the-loop review and approval endpoint. Commits reviewed minutes and action items to the permanent hearing record.
- **Access:** Presiding Judge or assigned Clerk.
- **Payload:**
  ```json
  {
    "transcription_id": 14,
    "minutes_summary": "Reviewed and finalized court minutes...",
    "action_items": ["Defendant to file reply within 14 days"],
    "action": "approve"
  }
  ```
- **Response `200`:** Updates `HearingTranscription.review_status` to `'Approved'`.

### `POST /api/ai/translate` (Feature 6: Multilingual Judicial Translation Engine)
- **Description:** Translates notices, orders, and reminders between English, Telugu, and Hindi with specialized legal lexicon. Preserves English as authoritative text under Article 348.
- **Payload:**
  ```json
  {
    "text": "Notice is hereby given that the hearing is listed on 20th November 2026 before Court Hall 2.",
    "source_lang": "en",
    "target_lang": "te",
    "doc_type": "Notice"
  }
  ```
- **Response `200`:**
  ```json
  {
    "success": true,
    "source_lang": "en",
    "target_lang": "te",
    "original_text": "Notice is hereby given...",
    "translated_text": "ఈ ద్వారా తెలియజేయడమైనది...",
    "is_machine_translation": true,
    "authoritative_text": "en",
    "article_348_notice": "Under Article 348 of the Constitution of India, the English text is the sole authoritative legal record.",
    "disclaimer": "⚖️ AI-generated, review before use"
  }
  ```

### `POST /api/ai/ask-data` (Feature 7: Natural-Language Analytics "Ask Your Data")
- **Description:** Converts administrative questions into safe parameterized database queries (no raw SQL execution) and returns Chart.js visual data.
- **Access:** Government administrators, Registrars, and Judges.
- **Payload:**
  ```json
  {
    "query": "How many civil cases are currently pending?"
  }
  ```
- **Response `200`:**
  ```json
  {
    "success": true,
    "tool_used": "count_cases",
    "summary": "There are currently 18 civil cases pending before the court.",
    "metric": 18,
    "chart_config": {
      "type": "bar",
      "data": { ... }
    },
    "disclaimer": "⚖️ AI-generated, review before use"
  }
  ```

### `GET /api/ai/backlog-insights` (Feature 8: Court Backlog & Pendency Insights)
- **Description:** Generates automated weekly intelligence cards highlighting 2-year pendency rates, dominant adjournment causes, and courtroom caseload balances computed from verified SQL metrics.
- **Access:** Government, Registrar, Judge.
- **Response `200`:**
  ```json
  {
    "success": true,
    "period": "Current Week",
    "metrics": {
      "total_pending": 18,
      "older_than_2_years": 4,
      "disposal_rate_pct": 25.0,
      "top_adjournment_cause": "Absence of Counsel / Counter Not Filed"
    },
    "insight_card": {
      "headline": "Civil Backlog Elevated in Commercial Docket",
      "summary": "4 out of 18 pending cases exceed 2 years pendency...",
      "recommendations": [
        "Prioritize fast-track scheduling for cases pending > 2 years",
        "Enforce strict 3-adjournment rule on written statements"
      ]
    },
    "disclaimer": "⚖️ AI-generated, review before use"
  }
  ```

### `POST /api/ai/cases/<int:case_id>/copilot` (Feature 9: Judge Copilot Sidebar)
- **Description:** Presiding judge co-pilot performing on-demand judicial tasks: 3-bullet brief, drafting adjournment orders, detecting calendar conflicts, and flagging missing evidence before judgment.
- **Access:** Presiding Judge and authorized court staff.
- **Payload:**
  ```json
  {
    "action": "summary_3_bullets"
  }
  ```
  *(Other actions: `draft_adjournment`, `check_conflicts`, `missing_evidence`)*
- **Response `200`:**
  ```json
  {
    "success": true,
    "action": "summary_3_bullets",
    "result": "• Suit for specific performance of contract valued at ₹25,00,000.\n• Plaintiff claims total consideration was paid; Defendant denies receipt.\n• Currently listed for cross-examination of PW-1.",
    "disclaimer": "⚖️ AI-generated, review before use"
  }
  ```

### `POST /api/ai/evaluate` (Feature 11: AI Feedback & Evaluation Mode)
- **Description:** Captures human reviewer ratings (`helpful`, `wrong`, `unsafe`) and feedback for AI outputs.
- **Payload:**
  ```json
  {
    "feature": "precedent_search",
    "rating": "helpful",
    "feedback": "Found exact citation for section 138 notice rule.",
    "prompt_text": "dishonour of cheque statutory notice",
    "response_text": "K. Venkatesh vs Lakshmi Enterprises"
  }
  ```
- **Response `200`:**
  ```json
  {
    "success": true,
    "evaluation_id": 42
  }
  ```

### `GET /api/admin/ai-eval-stats` (Feature 11: Evaluation Telemetry & KPI Analytics)
- **Description:** Returns aggregate satisfaction metrics, thumbs up/down breakdown, and satisfaction rates per AI feature.
- **Access:** Government, Registrar.
- **Response `200`:**
  ```json
  {
    "success": true,
    "total_evaluations": 128,
    "helpful_count": 115,
    "wrong_count": 10,
    "unsafe_count": 3,
    "overall_satisfaction_pct": 89.8,
    "feature_breakdown": {
      "case_summary": { "helpful": 32, "wrong": 2, "satisfaction": 94.1 },
      "precedent_search": { "helpful": 28, "wrong": 3, "satisfaction": 90.3 }
    }
  }
  ```

### `GET /api/admin/ai-status`
- **Description:** Real-time health, latency, provider selection (`live` vs `demo`), daily request count, and remaining quota.
- **Access:** Government, Registrar.

---

## Communication & Reminders API

### `GET /api/notifications`
- **Query Params:** `channel` (SMS, WhatsApp, Email, In-App), `status` (Queued, Sent, Delivered, Failed)

### `POST /api/notifications/preferences`
- **Description:** Updates recipient's language preferences (`en`, `te`, `hi`), opt-out flags per channel, and quiet hours schedule (`quiet_start`, `quiet_end`).
- **Payload:**
  ```json
  {
    "language": "te",
    "opt_out_sms": false,
    "opt_out_whatsapp": false,
    "quiet_hours_enabled": true,
    "quiet_start": "22:00",
    "quiet_end": "07:00"
  }
  ```

### `POST /api/notifications/mark-read`
- **Description:** Marks all unread user notifications as read.

### `POST /api/reminders/trigger`
- **Description:** Manually triggers the APScheduler reminder dispatcher (scans 7d / 1d / 2h hearing milestones).

### `POST /api/reminders/simulate-reply`
- **Payload:**
  ```json
  {
    "phone": "+919876543210",
    "message": "CONFIRM"
  }
  ```
- **Description:** Acknowledges hearing attendance and updates hearing record.

---

## Administrative Demo Utility

### `POST /api/admin/reset-demo`
- **Description:** Drops all existing tables, recreates schema, and seeds clean initial demo data. Available for quick demo repeatability.
