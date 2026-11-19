"""
Prompt Template Registry & Loader.
"""

from typing import Dict, Any, Tuple
from app.services.ai.prompts import (
    case_summary_v1,
    order_draft_v1,
    citizen_chat_v1,
    doc_extraction_v1,
    smart_schedule_v1
)

PROMPT_REGISTRY = {
    ("case_summary", "1.0"): case_summary_v1,
    ("order_draft", "1.0"): order_draft_v1,
    ("citizen_chat", "1.0"): citizen_chat_v1,
    ("doc_extraction", "1.0"): doc_extraction_v1,
    ("smart_schedule", "1.0"): smart_schedule_v1,
}

def get_prompt(feature_name: str, version: str = "1.0") -> Tuple[str, str, str]:
    """
    Returns (system_instruction, user_template, version).
    Falls back to version 1.0 if requested version is not registered.
    """
    module = PROMPT_REGISTRY.get((feature_name, version)) or PROMPT_REGISTRY.get((feature_name, "1.0"))
    if not module:
        raise ValueError(f"Unknown prompt feature '{feature_name}' (version '{version}').")
    return module.SYSTEM_INSTRUCTION, module.USER_TEMPLATE, module.VERSION
