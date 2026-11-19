"""
NyayaDesk AI Layer - Production Service Package
Provides dual-mode intelligence (Live Google Gemini via modern google-genai SDK
with seamless offline DemoProvider fallback), PII redaction, prompt injection defense,
response caching, rate limiting, and observability.
"""

from app.services.ai.base import BaseAIProvider
from app.services.ai.gemini_provider import GeminiProvider
from app.services.ai.demo_provider import DemoProvider
from app.services.ai.schemas import (
    CaseSummarySchema,
    OrderDraftSchema,
    DocumentExtractionSchema,
    SchedulingSuggestionSchema,
    SchedulingSlotItem,
    LegalChatSchema,
)
from app.services.ai.guardrails import (
    redact_pii,
    restore_pii,
    wrap_untrusted_input,
    scan_prompt_injection,
    AI_REVIEW_BANNER,
)
from app.services.ai.cache import AICacheManager, get_prompt_hash
from app.services.ai.rate_limiter import AIRateLimiter
from app.services.ai.service import (
    AIService,
    get_ai_service,
    get_ai_mode,
    generate_case_summary,
    draft_judicial_order,
    citizen_legal_chat,
    calculate_case_priority,
    suggest_cause_list_ordering,
    suggest_smart_scheduling_slots,
    assess_delay_risk,
    find_similar_cases,
    auto_tag_document,
    HybridListResult,
)

__all__ = [
    "BaseAIProvider",
    "GeminiProvider",
    "DemoProvider",
    "CaseSummarySchema",
    "OrderDraftSchema",
    "DocumentExtractionSchema",
    "SchedulingSuggestionSchema",
    "SchedulingSlotItem",
    "LegalChatSchema",
    "redact_pii",
    "restore_pii",
    "wrap_untrusted_input",
    "scan_prompt_injection",
    "AI_REVIEW_BANNER",
    "AICacheManager",
    "get_prompt_hash",
    "AIRateLimiter",
    "AIService",
    "get_ai_service",
    "get_ai_mode",
    "generate_case_summary",
    "draft_judicial_order",
    "citizen_legal_chat",
    "calculate_case_priority",
    "suggest_cause_list_ordering",
    "suggest_smart_scheduling_slots",
    "assess_delay_risk",
    "find_similar_cases",
    "auto_tag_document",
    "HybridListResult",
]

