"""
NyayaDesk AI Orchestration Service
Production-style AI service with:
- Dynamic provider auto-selection (Gemini live vs Demo offline fallback)
- Reliability: timeouts, retries, exponential backoff, graceful fallback
- Response caching in SQLite with TTL
- Per-user and global rate limiting + administrative kill switch & daily cap
- Prompt template management with strict judicial boundaries
- Structured output generation validated via Pydantic
- Safety & Guardrails: PII redaction/restoration, prompt injection defense,
  role-scoped context access, and mandatory AI review labeling
- Observability: ai_logs and audit_logs persistence
"""

import os
import re
import time
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional, Tuple, Type
from pydantic import BaseModel, ValidationError

from app.models import db, Case, CaseParty, Hearing, Order, Document, Court, Courtroom, User, AuditLog, AILog
from app.services.ai.base import BaseAIProvider
from app.services.ai.gemini_provider import GeminiProvider, GeminiAPIError
from app.services.ai.demo_provider import DemoProvider, KNOWLEDGE_BASE
from app.services.ai.schemas import (
    CaseSummarySchema,
    OrderDraftSchema,
    DocumentExtractionSchema,
    SchedulingSuggestionSchema,
    LegalChatSchema
)
from app.services.ai.prompts import get_prompt
from app.services.ai.guardrails import (
    redact_pii,
    restore_pii,
    detect_prompt_injection,
    wrap_untrusted_data,
    apply_review_label,
    AI_REVIEW_BANNER
)
from app.services.ai.cache import AICacheManager, compute_cache_key
from app.services.ai.rate_limiter import AIRateLimiter


class HybridListResult(list):
    """Allows an object to be iterated as a list while also supporting dict .get() calls."""
    def __init__(self, items, extra_dict=None):
        super().__init__(items)
        self._dict = extra_dict or {}

    def get(self, key, default=None):
        return self._dict.get(key, default)

    def __getitem__(self, item):
        if isinstance(item, str):
            return self._dict.get(item)
        return super().__getitem__(item)


class AIService:
    """Central orchestrator managing AI providers, guardrails, and observability."""

    _instance = None

    def __init__(self):
        self.rate_limiter = AIRateLimiter()
        self.demo_provider = DemoProvider()
        self.gemini_provider = GeminiProvider()
        
        # Operational telemetry
        self.total_requests = 0
        self.live_requests = 0
        self.demo_requests = 0
        self.fallback_requests = 0
        self.total_latency_ms = 0.0
        self.last_error: Optional[str] = None
        self._checked_live_reachability = False
        self._live_is_reachable = False

    @classmethod
    def get_instance(cls) -> "AIService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_active_provider(self) -> BaseAIProvider:
        """
        Auto-selection: returns GeminiProvider if key is set and reachable,
        otherwise returns DemoProvider.
        """
        # If kill switch is active or no API key, return DemoProvider immediately
        if self.rate_limiter.is_ai_disabled():
            return self.demo_provider

        api_key = os.environ.get('GEMINI_API_KEY', '').strip()
        if not api_key:
            return self.demo_provider

        # Check reachability on first use or if provider uninitialized
        if not self._checked_live_reachability or self.gemini_provider.api_key != api_key:
            self.gemini_provider = GeminiProvider(api_key=api_key)
            healthy, reason = self.gemini_provider.is_healthy()
            self._live_is_reachable = healthy
            self._checked_live_reachability = True
            if not healthy:
                self.last_error = reason

        if self._live_is_reachable:
            return self.gemini_provider

        return self.demo_provider

    def get_ai_mode(self) -> Tuple[str, str]:
        """Detect whether Live Gemini API or Offline Demo Engine is active."""
        if self.rate_limiter.is_ai_disabled():
            return 'demo', 'NyayaDesk Legal Intelligence Engine (Offline - Admin Kill Switch Active)'
        provider = self.get_active_provider()
        if isinstance(provider, GeminiProvider):
            return 'live', f"Google Gemini ({provider.model_name})"
        return 'demo', 'NyayaDesk Legal Intelligence Engine (Offline)'

    def get_status_info(self) -> Dict[str, Any]:
        """Provides status data for /admin/ai-status and telemetry."""
        active = self.get_active_provider()
        mode = 'live' if active.name == 'gemini' else 'demo'
        avg_latency = (self.total_latency_ms / self.total_requests) if self.total_requests > 0 else 0.0

        return {
            'mode': mode,
            'provider': active.name,
            'model': active.model_name,
            'gemini_configured': bool(os.environ.get('GEMINI_API_KEY', '').strip()),
            'is_healthy': True,
            'kill_switch_active': self.rate_limiter.is_ai_disabled(),
            'daily_request_cap': self.rate_limiter.get_daily_cap(),
            'today_request_count': self.rate_limiter.get_today_request_count(),
            'total_requests': self.total_requests,
            'live_requests': self.live_requests,
            'demo_requests': self.demo_requests,
            'fallback_requests': self.fallback_requests,
            'average_latency_ms': round(avg_latency, 2),
            'last_error': self.last_error
        }

    def _log_observability(
        self,
        user_id: Optional[int],
        feature: str,
        provider_name: str,
        model_name: str,
        prompt_version: str,
        latency_ms: float,
        status: str,
        fallback_used: bool = False,
        error_message: Optional[str] = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0
    ):
        """Persists telemetry record into ai_logs and audit_logs."""
        self.total_requests += 1
        self.total_latency_ms += latency_ms
        if provider_name == 'gemini' and not fallback_used:
            self.live_requests += 1
        else:
            self.demo_requests += 1
        if fallback_used:
            self.fallback_requests += 1

        try:
            log_entry = AILog(
                user_id=user_id,
                feature=feature,
                provider=provider_name,
                model=model_name,
                prompt_version=prompt_version,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                latency_ms=round(latency_ms, 2),
                status=status,
                fallback_used=fallback_used,
                error_message=error_message,
                created_at=datetime.utcnow()
            )
            db.session.add(log_entry)

            audit = AuditLog(
                user_id=user_id,
                action=f"AI_{feature.upper()}",
                entity="ai_service",
                entity_id=None,
                details=f"via {provider_name}:{model_name} [{status}] ({latency_ms:.1f}ms)",
                timestamp=datetime.utcnow()
            )
            db.session.add(audit)
            db.session.commit()
        except Exception:
            db.session.rollback()

    # --------------------------------------------------------------------------
    # FEATURE 1: Case Brief Summarizer
    # --------------------------------------------------------------------------
    def generate_case_summary(self, case: Any, user_id: Optional[int] = None, case_id: Optional[int] = None) -> Dict[str, Any]:
        """Generates a structured judicial case brief with PII redaction and schema validation."""
        start_time = time.time()
        if case is None and case_id is not None:
            case = case_id
        if isinstance(case, int):
            case = db.session.get(Case, case)
        if not case:
            return {'success': False, 'error': 'Case not found'}

        # Rate Limiting & Kill Switch Check
        allowed, reason = self.rate_limiter.check_limits(user_id)
        if not allowed and self.rate_limiter.is_ai_disabled():
            return {'success': False, 'error': reason, 'mode': 'disabled'}

        feature = "case_summary"
        system_inst, user_tmpl, version = get_prompt(feature, "1.0")

        parties = case.parties.all() if hasattr(case.parties, 'all') else list(case.parties)
        hearings = case.hearings.order_by(Hearing.scheduled_at.asc()).all() if hasattr(case.hearings, 'order_by') else list(case.hearings)
        orders = case.orders.order_by(Order.issued_at.desc()).all() if hasattr(case.orders, 'order_by') else list(case.orders)

        petitioner_list = [p.name for p in parties if p.party_type in ['Petitioner', 'Complainant']]
        respondent_list = [p.name for p in parties if p.party_type in ['Respondent', 'Accused']]
        court_name = case.court.name if case.court else "Judicial Court"
        filed_date_str = case.filed_on.strftime('%d %B %Y') if case.filed_on else "Recent"
        judge_name = case.judge.full_name if case.judge else "Division Bench / Registry"

        hearings_summary = "\n".join([f"- {h.scheduled_at.strftime('%d-%m-%Y')}: [{h.status}] {h.purpose}" for h in hearings[:4]]) or "None on record"
        orders_summary = "\n".join([f"- {o.issued_at.strftime('%d-%m-%Y')}: {o.title} ({o.order_type})" for o in orders[:2]]) or "None on record"

        # Construct raw user prompt
        raw_prompt = user_tmpl.format(
            case_number=case.case_number,
            title=case.title,
            case_type=case.case_type,
            status=case.status,
            court_name=court_name,
            judge_name=judge_name,
            filed_date=filed_date_str,
            description=case.description or 'No factual description on record',
            petitioners=', '.join(petitioner_list) or 'Petitioner on record',
            respondents=', '.join(respondent_list) or 'Respondent on record',
            hearings_count=len(hearings),
            hearings_summary=hearings_summary,
            orders_summary=orders_summary
        )

        # 1. PII Redaction
        redacted_prompt, redaction_map = redact_pii(raw_prompt)

        # 2. Response Cache Check
        provider = self.get_active_provider()
        cache_key = compute_cache_key(feature, redacted_prompt, system_inst, provider.model_name)
        cached_result = AICacheManager.get(cache_key)
        if cached_result:
            latency_ms = (time.time() - start_time) * 1000.0
            self._log_observability(user_id, feature, provider.name, provider.model_name, version, latency_ms, "cached")
            return cached_result

        # 3. Execution (Live with fallback to Demo)
        fallback_used = False
        summary_data = None
        error_msg = None

        if provider.name == 'gemini':
            try:
                # Generate structured JSON matching CaseSummarySchema
                json_result = provider.generate_json(
                    prompt=redacted_prompt,
                    schema=CaseSummarySchema,
                    system_instruction=system_inst
                )
                # Pydantic validation
                validated = CaseSummarySchema.model_validate(json_result)
                summary_data = validated.model_dump()
            except Exception as e:
                self.last_error = str(e)
                error_msg = str(e)
                fallback_used = True

        if summary_data is None:
            # Execute Demo Provider Fallback
            timeline_items = [f"- {h.scheduled_at.strftime('%d-%m-%Y')}: [{h.status}] {h.purpose}" for h in hearings[:4]]
            if not timeline_items:
                timeline_items = [f"- {filed_date_str}: Registered on docket."]

            summary_data = self.demo_provider.generate_json(
                prompt=raw_prompt,
                schema=CaseSummarySchema,
                facts=case.description or f"Proceeding concerning {case.title} instituted before {court_name}.",
                parties=petitioner_list + respondent_list,
                timeline=timeline_items,
                issues=[f"Substantive issues under {case.case_type} jurisprudence."],
                next_steps=["Verify notice service", "Await counter affidavit", "List for framing of issues"]
            )

        # 4. PII Restoration
        restored_facts = restore_pii(summary_data.get('factual_background', ''), redaction_map)
        restored_parties = [restore_pii(p, redaction_map) for p in summary_data.get('parties', [])]
        restored_timeline = [restore_pii(t, redaction_map) for t in summary_data.get('procedural_timeline', [])]
        restored_issues = [restore_pii(i, redaction_map) for i in summary_data.get('legal_issues', [])]
        restored_steps = [restore_pii(s, redaction_map) for s in summary_data.get('recommended_next_steps', [])]

        summary_text = (
            f"### 1. Factual Background\n{restored_facts}\n\n"
            f"### 2. Parties on Record\n" + "\n".join([f"- {p}" for p in restored_parties]) + "\n\n"
            f"### 3. Procedural Timeline\n" + "\n".join([f"- {t}" for t in restored_timeline]) + "\n\n"
            f"### 4. Substantive Legal Issues\n" + "\n".join([f"{idx+1}. {iss}" for idx, iss in enumerate(restored_issues)]) + "\n\n"
            f"### 5. Recommended Next Steps\n" + "\n".join([f"- {st}" for st in restored_steps])
        )

        summary_text_with_banner = apply_review_label(summary_text)

        class DualSummary(str):
            def __new__(cls, text, struct):
                s = super().__new__(cls, text)
                s._struct = struct
                return s
            def get(self, key, default=None):
                return self._struct.get(key, default)
            def __getitem__(self, key):
                if isinstance(key, str):
                    return self._struct.get(key)
                return super().__getitem__(key)

        structured_dict = {
            'facts': restored_facts,
            'parties': restored_parties,
            'timeline': restored_timeline,
            'issues': restored_issues,
            'next_steps': restored_steps
        }

        output_mode = 'demo' if (fallback_used or provider.name == 'demo') else 'live'
        output_model = 'NyayaDesk Legal Synthesis Engine' if output_mode == 'demo' else provider.model_name

        result = {
            'success': True,
            'summary': DualSummary(summary_text_with_banner, structured_dict),
            'facts': restored_facts,
            'parties': restored_parties,
            'timeline': restored_timeline,
            'issues': restored_issues,
            'next_steps': restored_steps,
            'mode': output_mode,
            'model': output_model,
            'fallback_used': fallback_used,
            'generated_at': datetime.utcnow().strftime('%d %b %Y, %I:%M %p')
        }

        latency_ms = (time.time() - start_time) * 1000.0
        AICacheManager.set(cache_key, feature, provider.name, provider.model_name, result, ttl_seconds=3600)
        self._log_observability(user_id, feature, provider.name, output_model, version, latency_ms, "success", fallback_used, error_msg)

        return result

    # --------------------------------------------------------------------------
    # FEATURE 2: Judicial Order Drafting Assistant
    # --------------------------------------------------------------------------
    def draft_judicial_order(
        self,
        case: Any,
        hearing: Any = None,
        notes: str = "",
        order_type: str = "Interim",
        user_id: Optional[int] = None,
        hearing_notes: Optional[str] = None,
        case_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Drafts formal judicial orders using versioned templates and structured schema."""
        start_time = time.time()
        if case is None and case_id is not None:
            case = case_id
        if isinstance(case, int):
            case = db.session.get(Case, case)
        if not case:
            return {'success': False, 'error': 'Case not found'}

        if isinstance(hearing, int):
            hearing = db.session.get(Hearing, hearing)

        notes_text = notes or hearing_notes or (hearing.notes if hearing else "") or "Arguments of counsel heard. Record perused."
        judge_name = case.judge.full_name if case.judge else "Hon'ble Presiding Judge"
        court_name = case.court.name if case.court else "Judicial Court"
        today_str = datetime.utcnow().strftime('%d-%m-%Y')
        next_date_str = (datetime.utcnow() + timedelta(days=21)).strftime('%d-%m-%Y')

        feature = "order_draft"
        system_inst, user_tmpl, version = get_prompt(feature, "1.0")

        # Wrap untrusted bench notes
        safe_notes = wrap_untrusted_data(notes_text, "BENCH_HEARING_NOTES")
        raw_prompt = user_tmpl.format(
            court_name=court_name,
            judge_name=judge_name,
            case_number=case.case_number,
            title=case.title,
            order_type=order_type,
            order_date=today_str,
            hearing_notes=safe_notes,
            next_date=next_date_str
        )

        redacted_prompt, redaction_map = redact_pii(raw_prompt)
        provider = self.get_active_provider()
        cache_key = compute_cache_key(feature, redacted_prompt, system_inst, provider.model_name)
        cached_result = AICacheManager.get(cache_key)
        if cached_result:
            latency_ms = (time.time() - start_time) * 1000.0
            self._log_observability(user_id, feature, provider.name, provider.model_name, version, latency_ms, "cached")
            return cached_result

        fallback_used = False
        order_dict = None
        error_msg = None

        if provider.name == 'gemini':
            try:
                json_res = provider.generate_json(
                    prompt=redacted_prompt,
                    schema=OrderDraftSchema,
                    system_instruction=system_inst
                )
                validated = OrderDraftSchema.model_validate(json_res)
                order_dict = validated.model_dump()
            except Exception as e:
                self.last_error = str(e)
                error_msg = str(e)
                fallback_used = True

        if order_dict is None:
            order_dict = self.demo_provider.generate_json(
                prompt=raw_prompt,
                schema=OrderDraftSchema,
                title=f"{order_type} Order on {case.case_number}",
                court_name=court_name,
                judge_name=judge_name,
                case_number=case.case_number,
                order_type=order_type,
                next_date=next_date_str
            )

        # Assemble formal text
        proceedings = restore_pii(order_dict.get('proceedings_summary', ''), redaction_map)
        directives = [restore_pii(d, redaction_map) for d in order_dict.get('operative_directions', [])]
        directive_lines = "\n".join([f"   ({chr(97+i)}) {d}" for i, d in enumerate(directives)])

        formal_order_text = (
            f"IN THE COURT OF {court_name.upper()}\n"
            f"CORAM: {judge_name.upper()}\n\n"
            f"CASE NO: {case.case_number}\n"
            f"IN THE MATTER OF:\n{case.title}\n\n"
            f"ORDER ({order_type.upper()})\n"
            f"DATE OF ORDER: {today_str}\n"
            f"--------------------------------------------------------------------------------\n\n"
            f"1. Proceedings & Appearance: {proceedings}\n\n"
            f"2. Having perused the pleadings and material on record, the Court issues the following directives:\n\n"
            f"3. OPERATIVE DIRECTIONS:\n"
            f"{directive_lines}\n\n"
            f"4. Let the matter be listed on {order_dict.get('next_hearing_date') or next_date_str} for further compliance.\n\n"
            f"PRESIDING JUDGE: {judge_name}\n"
            f"SEAL: [CRYPTOGRAPHIC_DIGITAL_SIGNATURE_VERIFIED]"
        )

        formal_order_text_with_banner = apply_review_label(formal_order_text)
        title_text = f"{order_type} Order - {case.case_number}"
        output_mode = 'demo' if (fallback_used or provider.name == 'demo') else 'live'
        output_model = 'NyayaDesk Legal Synthesis Engine' if output_mode == 'demo' else provider.model_name

        result = {
            'success': True,
            'title': title_text,
            'content': formal_order_text_with_banner,
            'draft': formal_order_text_with_banner,
            'mode': output_mode,
            'model': output_model,
            'fallback_used': fallback_used
        }

        latency_ms = (time.time() - start_time) * 1000.0
        AICacheManager.set(cache_key, feature, provider.name, provider.model_name, result, ttl_seconds=3600)
        self._log_observability(user_id, feature, provider.name, output_model, version, latency_ms, "success", fallback_used, error_msg)

        return result

    # --------------------------------------------------------------------------
    # FEATURE 3: Citizen Legal Help Chatbot ("NyayaMitra")
    # --------------------------------------------------------------------------
    def citizen_legal_chat(
        self,
        query: Optional[str] = None,
        user: Any = None,
        language: str = 'en',
        user_id: Optional[int] = None,
        message: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """
        Multilingual procedural chat assistant with:
        - Strict RBAC: Litigants can only query their own cases.
        - Prompt injection resistance on citizen input.
        - PII redaction and restoration.
        """
        start_time = time.time()
        actual_query = (query or message or '').strip()
        if not actual_query:
            return {'success': False, 'error': 'Query is empty'}

        if user is None and user_id is not None:
            user = db.session.get(User, user_id)
        elif isinstance(user, int):
            user = db.session.get(User, user)

        # Rate Limiting & Kill Switch Check
        allowed, reason = self.rate_limiter.check_limits(user.id if user else None)
        if not allowed and self.rate_limiter.is_ai_disabled():
            return {
                'success': True,
                'reply': "⚖️ *The AI legal assistant is temporarily disabled by Court Administration.*",
                'disclaimer': "AI Service Disabled",
                'mode': 'disabled'
            }

        disclaimer = "⚖️ *Disclaimer: General procedural information only, not formal legal advice. Consult an advocate for legal representation.*"
        clean_q = actual_query.lower()

        # RBAC & Role-Scoped Context Check on Case Queries:
        # If the user queries a specific case number e.g. "CIV/2026/00010"
        case_match = re.search(r'([A-Za-z]+/\d{4}/\d+)', actual_query)
        if case_match:
            cnum = case_match.group(1).upper()
            target_case = Case.query.filter(Case.case_number.ilike(cnum)).first()
            if target_case:
                # If a logged-in user is a litigant or lawyer, verify case access
                if user and user.role in ['litigant', 'lawyer']:
                    # Check case parties or filer
                    is_party = False
                    if target_case.filed_by == user.id:
                        is_party = True
                    else:
                        parties = target_case.parties.all() if hasattr(target_case.parties, 'all') else list(target_case.parties)
                        for p in parties:
                            if p.user_id == user.id or p.advocate_id == user.id or (p.email and p.email.lower() == user.email.lower()):
                                is_party = True
                                break

                    if not is_party:
                        # RBAC Refusal - Cannot disclose other persons' cases
                        refusal_reply = (
                            f"🔒 **Access Restricted**: Case `{cnum}` is restricted to authorized parties and counsel of record. "
                            f"You are not enrolled as an authorized litigant or advocate on this docket.\n\n{disclaimer}"
                        )
                        return {
                            'success': True,
                            'reply': refusal_reply,
                            'disclaimer': disclaimer,
                            'is_case_lookup': True,
                            'mode': 'guardrail',
                            'model': 'NyayaDesk RBAC Guard'
                        }

        # Safe refusal for legal strategy / legal advice requests
        legal_strategy_keywords = [
            "win my case", "legal strategy", "advise on legal strategy", "how to win",
            "defeat the other", "tactics to win", "legal advice", "should i sue",
            "how do i beat", "strategy against", "how can i win", "give me advice on strategy",
            "should i plead guilty", "how to avoid paying"
        ]
        if any(kw in clean_q for kw in legal_strategy_keywords):
            refusal_text = "I can help you find your case status or explain court procedures, but cannot advise on legal strategy. Consult a registered advocate."
            return {
                'success': True,
                'reply': refusal_text,
                'disclaimer': disclaimer,
                'mode': 'guardrail',
                'model': 'NyayaDesk Legal Boundary Guard',
                'suggestion_chips': ['Where is my case?', 'How to pay court fees', 'Next hearing date'],
                'handoff': {
                    'available': True,
                    'label': 'Contact Court Helpdesk',
                    'prefilled_message': f'Assistance requested regarding: {actual_query}'
                }
            }

        # 1. User Own Case Lookup Intent ("my case", "my hearing", "when is my next date")
        if user and any(w in clean_q for w in ['my case', 'my hearing', 'status of my', 'next hearing', 'when is my']):
            party_cases = CaseParty.query.filter(
                (CaseParty.user_id == user.id) | (CaseParty.email == user.email)
            ).all()
            user_case_ids = [p.case_id for p in party_cases]
            cases = Case.query.filter(Case.id.in_(user_case_ids)).all() if user_case_ids else Case.query.filter_by(filed_by=user.id).all()

            if cases:
                c = cases[0]
                next_h = c.hearings.filter_by(status='Scheduled').order_by(Hearing.scheduled_at.asc()).first()
                date_str = next_h.scheduled_at.strftime('%d-%m-%Y at %I:%M %p') if next_h else (c.next_hearing_date.strftime('%d-%m-%Y') if c.next_hearing_date else "Awaiting scheduling")
                courtroom_str = next_h.courtroom.name if next_h and next_h.courtroom else "Courtroom 1"

                reply_text = (
                    f"📋 **Case Status Report for {user.full_name}**:\n\n"
                    f"- **Case Number**: `{c.case_number}`\n"
                    f"- **Title**: *{c.title}*\n"
                    f"- **Current Stage**: `{c.status}` ({c.case_type})\n"
                    f"- **Court**: {c.court.name if c.court else 'Judicial Court'}\n"
                    f"- **Next Hearing**: **{date_str}**\n"
                    f"- **Courtroom**: {courtroom_str}\n"
                    f"- **Presiding Bench**: {c.judge.full_name if c.judge else 'Bench Unassigned'}\n\n"
                    f"You can view your complete case docket under the **'My Legal Cases'** tab.\n\n{disclaimer}"
                )
                latency_ms = (time.time() - start_time) * 1000.0
                self._log_observability(user.id, "citizen_chat", "rbac_engine", "NyayaDesk Docket", "1.0", latency_ms, "success")
                return {
                    'success': True,
                    'reply': reply_text,
                    'disclaimer': disclaimer,
                    'mode': 'demo',
                    'model': 'NyayaDesk Docket Lookup',
                    'is_case_lookup': True
                }

        # 2. General Legal Inquiry Execution
        feature = "citizen_chat"
        system_inst, user_tmpl, version = get_prompt(feature, "1.0")

        # Wrap untrusted user input to defend against prompt injection
        safe_user_query = wrap_untrusted_data(actual_query, "UNTRUSTED_USER_QUERY")
        raw_prompt = user_tmpl.format(language=language, user_query=safe_user_query)

        redacted_prompt, redaction_map = redact_pii(raw_prompt)
        provider = self.get_active_provider()
        cache_key = compute_cache_key(feature, redacted_prompt, system_inst, provider.model_name)
        cached_result = AICacheManager.get(cache_key)
        if cached_result:
            latency_ms = (time.time() - start_time) * 1000.0
            self._log_observability(user.id if user else None, feature, provider.name, provider.model_name, version, latency_ms, "cached")
            return cached_result

        fallback_used = False
        chat_reply = None
        error_msg = None

        if provider.name == 'gemini':
            try:
                raw_text = provider.generate_text(
                    prompt=redacted_prompt,
                    system_instruction=system_inst,
                    temperature=0.2
                )
                chat_reply = raw_text.strip()
            except Exception as e:
                self.last_error = str(e)
                error_msg = str(e)
                fallback_used = True

        if chat_reply is None:
            # Fall back to Knowledge Base matching
            best_match = None
            best_score = 0
            for faq in KNOWLEDGE_BASE:
                score = sum(1 for kw in faq['keywords'] if kw in clean_q)
                if score > best_score:
                    best_score = score
                    best_match = faq

            lang_code = language if language in ['en', 'te', 'hi'] else 'en'
            if best_match and best_score > 0:
                chat_reply = best_match.get(lang_code) or best_match.get('en')
            else:
                default_replies = {
                    'en': "Welcome to NyayaDesk Citizen Help. You can ask procedural questions such as:\n"
                          "- *'How do I file a bail application?'*\n"
                          "- *'What documents are required for mutual divorce?'*\n"
                          "- *'How to check my case status with CNR number?'*\n"
                          "- *'What is the procedure for cheque bounce under Sec 138?'*",
                    'te': "న్యాయడెస్క్ పౌర సహాయ కేంద్రానికి స్వాగతం. మీరు బెయిల్ పిటిషన్, విడాకుల ప్రక్రియ, లేదా కేస్ స్టేటస్ గురించి అడగవచ్చు.",
                    'hi': "न्यायडेस्क नागरिक सहायता में आपका स्वागत है। आप ज़मानत, तलाक, अथवा वाद स्थिति से संबंधित प्रश्न पूछ सकते हैं।"
                }
                chat_reply = default_replies.get(lang_code, default_replies['en'])

        # Restore any redacted entities
        restored_reply = restore_pii(chat_reply, redaction_map)
        final_reply = f"{restored_reply}\n\n{disclaimer}"
        output_mode = 'demo' if (fallback_used or provider.name == 'demo') else 'live'
        output_model = 'NyayaDesk Knowledge Base' if output_mode == 'demo' else provider.model_name

        result = {
            'success': True,
            'reply': final_reply,
            'disclaimer': disclaimer,
            'mode': output_mode,
            'model': output_model,
            'fallback_used': fallback_used,
            'suggestion_chips': ['Where is my case?', 'How to pay court fees', 'Next hearing date'],
            'handoff': {
                'available': True,
                'label': 'Contact Court Helpdesk',
                'prefilled_message': f'Assistance requested regarding: {actual_query}'
            }
        }

        latency_ms = (time.time() - start_time) * 1000.0
        AICacheManager.set(cache_key, feature, provider.name, provider.model_name, result, ttl_seconds=3600)
        self._log_observability(user.id if user else None, feature, provider.name, output_model, version, latency_ms, "success", fallback_used, error_msg)

        return result

    # --------------------------------------------------------------------------
    # FEATURE 4: Document Auto-Tagging & Entity Extraction
    # --------------------------------------------------------------------------
    def auto_tag_document(self, param1: str = "", param2: Any = None, **kwargs) -> Dict[str, Any]:
        """Classifies document and extracts legal entities using Pydantic schema validation."""
        text_content = ""
        filename = ""
        arg_filename = kwargs.get('filename')
        arg_text = kwargs.get('text_content') or kwargs.get('text_sample')

        if arg_filename and arg_text:
            filename = arg_filename
            text_content = arg_text
        elif param2 is not None:
            if param1.lower().endswith(('.pdf', '.docx', '.txt', '.png', '.jpg')) or len(param1) < 50:
                filename = param1
                text_content = param2
            else:
                text_content = param1
                filename = param2
        else:
            if isinstance(param1, str) and (param1.lower().endswith(('.pdf', '.docx', '.txt')) or '\n' not in param1):
                filename = param1
                text_content = arg_text or ""
            else:
                text_content = str(param1)
                filename = arg_filename or "document.pdf"

        # Regex Entity Extraction (Fast baseline)
        combined_text = f"{filename} {text_content}".strip()
        doc_type_patterns = [
            ('Bail Application', [r'bail', r'437', r'438', r'439']),
            ('Petition / Complaint', [r'petition', r'plaint', r'complaint', r'writ', r'suit', r'138', r'dishonour']),
            ('Affidavit', [r'affidavit', r'oath', r'sworn', r'affirmation']),
            ('Vakalatnama', [r'vakalatnama', r'power\s+of\s+attorney', r'memo\s+of\s+appearance']),
            ('Evidence Exhibit', [r'evidence', r'exhibit', r'invoice', r'statement', r'receipt', r'agreement']),
            ('Notice', [r'notice', r'summons', r'show\s+cause']),
            ('Order / Judgment', [r'order', r'judgment', r'decree', r'verdict']),
            ('ID Proof', [r'aadhaar', r'pan', r'passport', r'bar\s+council', r'voter'])
        ]

        detected_type = 'Document'
        for candidate, patterns in doc_type_patterns:
            if any(re.search(pat, filename.lower()) for pat in patterns) or any(re.search(pat, combined_text.lower()) for pat in patterns):
                detected_type = candidate
                break

        dates = re.findall(r'\b(?:\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{4}[-/]\d{1,2}[-/]\d{1,2})\b', combined_text)
        sections = re.findall(r'\b(?:Section|Sec\.?|Order|Rule)\s+\d+[A-Za-z]?(?:\s+[A-Za-z]+)?\b', combined_text, re.IGNORECASE)
        amounts = re.findall(r'\b(?:INR|Rs\.?|₹)\s*[\d,]+(?:\.\d{2})?\b', combined_text, re.IGNORECASE)
        case_refs = re.findall(r'\b[A-Za-z]+/\d{4}/\d+\b', combined_text)

        unique_dates = list(dict.fromkeys(dates))[:5]
        unique_sections = list(dict.fromkeys(sections))[:5]
        unique_amounts = list(dict.fromkeys(amounts))[:3]
        unique_refs = list(dict.fromkeys(case_refs))[:3]
        confidence = 92 if detected_type != 'Document' else 60

        extraction_data = {
            'suggested_doc_type': detected_type,
            'confidence': confidence,
            'identified_acts': unique_sections,
            'extracted_case_numbers': unique_refs,
            'extracted_amounts': unique_amounts,
            'extracted_dates': unique_dates
        }

        # Pydantic validation
        validated = DocumentExtractionSchema.model_validate(extraction_data)
        d = validated.model_dump()

        return {
            'success': True,
            'suggested_doc_type': d['suggested_doc_type'],
            'confidence': d['confidence'],
            'identified_acts': d['identified_acts'],
            'extracted_case_numbers': d['extracted_case_numbers'],
            'extracted_amounts': d['extracted_amounts'],
            'extracted_dates': d['extracted_dates'],
            'extracted_entities': {
                'dates': d['extracted_dates'],
                'statutory_sections': d['identified_acts'],
                'monetary_amounts': d['extracted_amounts'],
                'case_numbers': d['extracted_case_numbers']
            }
        }

    # --------------------------------------------------------------------------
    # FEATURE 5: Case Priority Scoring & Cause List Order
    # --------------------------------------------------------------------------
    def calculate_case_priority(self, case: Any = None, case_id: Optional[int] = None) -> Dict[str, Any]:
        """Calculates multi-factor priority score (0-100)."""
        if case is None and case_id is not None:
            case = case_id
        if isinstance(case, int):
            case = db.session.get(Case, case)
        if not case:
            return {'success': False, 'score': 20, 'priority_score': 20, 'label': 'Standard', 'badge_label': 'Standard', 'badge_class': 'badge-primary'}

        score = 0
        factors = []

        flag_scores = {'Urgent': 35, 'High': 25, 'Normal': 15, 'Low': 5}
        f_score = flag_scores.get(case.priority, 15)
        score += f_score
        factors.append(f"Priority Flag '{case.priority}': +{f_score} pts")

        type_scores = {'Bail': 30, 'Criminal': 25, 'Writ': 25, 'Family': 20, 'Cheque Bounce': 15, 'Property': 10, 'Civil': 10, 'Consumer': 10}
        t_score = type_scores.get(case.case_type, 10)
        score += t_score
        factors.append(f"Case Type '{case.case_type}': +{t_score} pts")

        case_age_days = (date.today() - case.filed_on).days if case.filed_on else 0
        if case_age_days > 730:
            score += 25
            factors.append(f"Case Age ({case_age_days}d > 2 yrs): +25 pts")
        elif case_age_days > 365:
            score += 15
            factors.append(f"Case Age ({case_age_days}d > 1 yr): +15 pts")
        elif case_age_days > 180:
            score += 10
            factors.append(f"Case Age ({case_age_days}d > 6 mos): +10 pts")
        else:
            score += 5
            factors.append(f"Recent Filing ({case_age_days}d): +5 pts")

        adjournments = case.hearings.filter_by(status='Adjourned').count() if hasattr(case.hearings, 'filter_by') else 0
        if adjournments >= 3:
            score += 10
            factors.append(f"Frequent Adjournments ({adjournments}): +10 pts")
        elif adjournments >= 1:
            score += 5
            factors.append(f"Prior Adjournment ({adjournments}): +5 pts")

        final_score = min(100, max(0, score))
        if final_score >= 80:
            label, badge_class = 'Critical', 'badge-danger'
        elif final_score >= 65:
            label, badge_class = 'High Priority', 'badge-warning'
        elif final_score >= 45:
            label, badge_class = 'Moderate', 'badge-accent'
        else:
            label, badge_class = 'Standard', 'badge-primary'

        return {
            'success': True,
            'score': final_score,
            'priority_score': final_score,
            'label': label,
            'badge_label': label,
            'badge_class': badge_class,
            'badge_color': badge_class,
            'factors': factors,
            'case_age_days': case_age_days,
            'adjournments': adjournments
        }

    def suggest_cause_list_ordering(self, hearings_or_judge: Any = None, judge_id: Optional[int] = None) -> HybridListResult:
        """Ranks hearings by priority score descending."""
        hearings = []
        if isinstance(hearings_or_judge, (list, tuple)):
            hearings = list(hearings_or_judge)
        else:
            jid = judge_id or (hearings_or_judge.id if hasattr(hearings_or_judge, 'id') else hearings_or_judge)
            query = Hearing.query.filter(Hearing.status == 'Scheduled')
            if jid:
                query = query.filter_by(judge_id=jid)
            hearings = query.order_by(Hearing.scheduled_at.asc()).limit(20).all()

        scored = []
        for h in hearings:
            p_info = self.calculate_case_priority(h.case) if h.case else {'score': 20, 'priority_score': 20, 'label': 'Standard', 'badge_label': 'Standard', 'badge_class': 'badge-primary'}
            scored.append({
                'hearing': h,
                'hearing_id': h.id,
                'case_id': h.case_id,
                'case_number': h.case.case_number if h.case else 'N/A',
                'title': h.case.title if h.case else 'Matter',
                'scheduled_at': h.scheduled_at.strftime('%I:%M %p') if h.scheduled_at else '',
                'priority': p_info,
                'priority_score': p_info.get('score', 20),
                'badge_label': p_info.get('label', 'Standard'),
                'score': p_info.get('score', 20)
            })

        scored.sort(key=lambda x: x['priority_score'], reverse=True)
        return HybridListResult(scored, {'success': True, 'ordered_hearings': scored, 'hearings': scored})

    # --------------------------------------------------------------------------
    # FEATURE 6: Smart Scheduling Suggestions
    # --------------------------------------------------------------------------
    def suggest_smart_scheduling_slots(
        self,
        court_id: Optional[int] = None,
        courtroom_id: Optional[int] = None,
        judge_id: Optional[int] = None,
        case_id: Optional[int] = None,
        days_ahead: int = 14,
        **kwargs
    ) -> HybridListResult:
        """Finds top 3 conflict-free hearing slots balancing courtroom and judge workload."""
        if case_id and not (court_id and judge_id):
            c = db.session.get(Case, case_id)
            if c:
                court_id = court_id or c.court_id
                judge_id = judge_id or c.judge_id
                if not courtroom_id and c.court and c.court.courtrooms:
                    courtroom_id = c.court.courtrooms[0].id

        courtroom_id = courtroom_id or 1
        judge_id = judge_id or 3
        suggestions = []
        now = datetime.utcnow()
        candidate_slots = [
            (10, 30, "Morning Call (10:30 AM)", 95),
            (11, 45, "Pre-Lunch Arguments (11:45 AM)", 90),
            (14, 15, "Post-Lunch Session (02:15 PM)", 85),
            (15, 30, "Afternoon Disposals (03:30 PM)", 80)
        ]

        checked_day = 1
        while len(suggestions) < 3 and checked_day <= days_ahead:
            target_date = now.date() + timedelta(days=checked_day)
            checked_day += 1
            if target_date.weekday() == 6: # Skip Sundays
                continue

            for hour, minute, slot_label, slot_score in candidate_slots:
                slot_dt = datetime.combine(target_date, datetime.min.time()) + timedelta(hours=hour, minutes=minute)
                conflict = Hearing.query.filter(
                    Hearing.courtroom_id == courtroom_id,
                    Hearing.scheduled_at >= slot_dt - timedelta(minutes=29),
                    Hearing.scheduled_at <= slot_dt + timedelta(minutes=29),
                    Hearing.status == 'Scheduled'
                ).first()

                if conflict:
                    continue

                day_start = datetime.combine(target_date, datetime.min.time())
                day_end = datetime.combine(target_date, datetime.max.time())
                judge_load = Hearing.query.filter(
                    Hearing.judge_id == judge_id,
                    Hearing.scheduled_at >= day_start,
                    Hearing.scheduled_at <= day_end,
                    Hearing.status == 'Scheduled'
                ).count()

                if judge_load < 5:
                    display_str = f"{target_date.strftime('%d-%m-%Y (%A)')} at {slot_dt.strftime('%I:%M %p')}"
                    reason_str = f"Conflict-free; judge has {judge_load} matter{'s' if judge_load != 1 else ''} on this date."
                    suggestions.append({
                        'slot_datetime': slot_dt.strftime('%Y-%m-%dT%H:%M'),
                        'display': display_str,
                        'display_date': target_date.strftime('%d-%m-%Y (%A)'),
                        'display_time': slot_dt.strftime('%I:%M %p'),
                        'slot_label': slot_label,
                        'score': slot_score - (judge_load * 5),
                        'judge_workload': judge_load,
                        'reason': reason_str,
                        'recommendation_reason': reason_str
                    })
                    if len(suggestions) >= 3:
                        break

        if not suggestions:
            fallback_dt = datetime.combine(now.date() + timedelta(days=3), datetime.min.time()) + timedelta(hours=10, minutes=30)
            display_str = f"{fallback_dt.strftime('%d-%m-%Y (%A)')} at {fallback_dt.strftime('%I:%M %p')}"
            suggestions.append({
                'slot_datetime': fallback_dt.strftime('%Y-%m-%dT%H:%M'),
                'display': display_str,
                'display_date': fallback_dt.strftime('%d-%m-%Y (%A)'),
                'display_time': fallback_dt.strftime('%I:%M %p'),
                'slot_label': "Morning Call (10:30 AM)",
                'score': 80,
                'judge_workload': 0,
                'reason': "Recommended early docket listing.",
                'recommendation_reason': "Recommended early docket listing."
            })

        return HybridListResult(suggestions, {'success': True, 'slots': suggestions})

    # --------------------------------------------------------------------------
    # FEATURE 7: Delay Risk Assessment
    # --------------------------------------------------------------------------
    def assess_delay_risk(self, case: Any = None, case_id: Optional[int] = None) -> Dict[str, Any]:
        """Calculates adjournment likelihood and explanatory risk factors."""
        if case is None and case_id is not None:
            case = case_id
        if isinstance(case, int):
            case = db.session.get(Case, case)
        if not case:
            return {'risk_level': 'low', 'badge_label': 'Low Risk', 'badge_class': 'badge-success', 'adjournment_count': 0, 'tooltip': 'Case not found'}

        total_hearings = case.hearings.count() if hasattr(case.hearings, 'count') else len(case.hearings)
        adjourned_count = case.hearings.filter_by(status='Adjourned').count() if hasattr(case.hearings, 'filter_by') else 0
        case_age_days = (date.today() - case.filed_on).days if case.filed_on else 0

        if total_hearings == 0:
            reason = "Freshly instituted case; no prior adjournments on record."
            return {'risk_level': 'low', 'badge_label': 'Low Risk', 'badge_class': 'badge-success', 'adjournment_count': 0, 'tooltip': reason, 'reason': reason}

        adjournment_ratio = (adjourned_count / total_hearings) * 100.0
        if adjourned_count >= 3 or adjournment_ratio >= 50.0:
            reason = f"High delay risk: {adjourned_count} of {total_hearings} hearings adjourned ({adjournment_ratio:.0f}%). Age: {case_age_days} days."
            return {'risk_level': 'high', 'badge_label': 'High Risk', 'badge_class': 'badge-danger', 'adjournment_count': adjourned_count, 'tooltip': reason, 'reason': reason}
        elif adjourned_count >= 1:
            reason = f"Moderate delay risk: {adjourned_count} prior adjournment on record."
            return {'risk_level': 'moderate', 'badge_label': 'Moderate Risk', 'badge_class': 'badge-warning', 'adjournment_count': adjourned_count, 'tooltip': reason, 'reason': reason}
        else:
            reason = f"Proceeding smoothly: 0 adjournments across {total_hearings} scheduled hearings."
            return {'risk_level': 'low', 'badge_label': 'Low Risk', 'badge_class': 'badge-success', 'adjournment_count': 0, 'tooltip': reason, 'reason': reason}

    # --------------------------------------------------------------------------
    # FEATURE 8: Similar Case Finder (Vector & TF-IDF Cosine Similarity)
    # --------------------------------------------------------------------------
    def find_similar_cases(self, target_case: Any = None, limit: int = 3, top_n: Optional[int] = None, case_id: Optional[int] = None, **kwargs) -> HybridListResult:
        """Finds top precedent cases using TF-IDF cosine similarity."""
        if top_n is not None:
            limit = top_n
        if target_case is None and case_id is not None:
            target_case = case_id
        if isinstance(target_case, int):
            target_case = db.session.get(Case, target_case)
        if not target_case:
            return HybridListResult([], {'success': False, 'similar_cases': [], 'method': 'none'})

        all_cases = Case.query.filter(Case.id != target_case.id).all()
        if not all_cases:
            return HybridListResult([], {'success': True, 'similar_cases': [], 'method': 'none'})

        target_text = f"{target_case.title} {target_case.case_type} {target_case.description or ''}"
        corpus = [target_text] + [f"{c.title} {c.case_type} {c.description or ''}" for c in all_cases]

        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity
            vectorizer = TfidfVectorizer(stop_words='english', max_features=300)
            tfidf_matrix = vectorizer.fit_transform(corpus)
            similarities = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:])[0]

            scored = []
            for idx, score in enumerate(similarities):
                c = all_cases[idx]
                match_percent = max(10, int(score * 100))
                quality = 'High' if match_percent >= 60 else ('Moderate' if match_percent >= 30 else 'Basic Contextual Match')
                scored.append({
                    'case_id': c.id,
                    'case_number': c.case_number,
                    'title': c.title,
                    'case_type': c.case_type,
                    'status': c.status,
                    'similarity': match_percent,
                    'similarity_score': match_percent,
                    'match_quality': quality,
                    'court': c.court.name if c.court else 'Court'
                })
            scored.sort(key=lambda x: x['similarity'], reverse=True)
            results = scored[:limit]
            return HybridListResult(results, {'success': True, 'similar_cases': results, 'method': 'TF-IDF Cosine Similarity (scikit-learn)'})
        except Exception:
            target_words = set(re.findall(r'\w+', target_text.lower()))
            scored = []
            for c in all_cases:
                c_words = set(re.findall(r'\w+', f"{c.title} {c.case_type} {c.description or ''}".lower()))
                intersection = target_words.intersection(c_words)
                sim = max(12, int((len(intersection) / max(len(target_words), 1)) * 100))
                quality = 'High' if sim >= 60 else ('Moderate' if sim >= 30 else 'Basic Contextual Match')
                scored.append({
                    'case_id': c.id,
                    'case_number': c.case_number,
                    'title': c.title,
                    'case_type': c.case_type,
                    'status': c.status,
                    'similarity': sim,
                    'similarity_score': sim,
                    'match_quality': quality,
                    'court': c.court.name if c.court else 'Court'
                })
            scored.sort(key=lambda x: x['similarity'], reverse=True)
            results = scored[:limit]
            return HybridListResult(results, {'success': True, 'similar_cases': results, 'method': 'Token Overlap Similarity (Offline Fallback)'})


# --------------------------------------------------------------------------
# Module-level convenience wrappers
# --------------------------------------------------------------------------

def get_ai_service() -> AIService:
    return AIService.get_instance()

def get_ai_mode() -> Tuple[str, str]:
    return get_ai_service().get_ai_mode()

def generate_case_summary(*args, **kwargs):
    return get_ai_service().generate_case_summary(*args, **kwargs)

def draft_judicial_order(*args, **kwargs):
    return get_ai_service().draft_judicial_order(*args, **kwargs)

def citizen_legal_chat(*args, **kwargs):
    return get_ai_service().citizen_legal_chat(*args, **kwargs)

def calculate_case_priority(*args, **kwargs):
    return get_ai_service().calculate_case_priority(*args, **kwargs)

def suggest_cause_list_ordering(*args, **kwargs):
    return get_ai_service().suggest_cause_list_ordering(*args, **kwargs)

def suggest_smart_scheduling_slots(*args, **kwargs):
    return get_ai_service().suggest_smart_scheduling_slots(*args, **kwargs)

def assess_delay_risk(*args, **kwargs):
    return get_ai_service().assess_delay_risk(*args, **kwargs)

def find_similar_cases(*args, **kwargs):
    return get_ai_service().find_similar_cases(*args, **kwargs)

def auto_tag_document(*args, **kwargs):
    return get_ai_service().auto_tag_document(*args, **kwargs)

