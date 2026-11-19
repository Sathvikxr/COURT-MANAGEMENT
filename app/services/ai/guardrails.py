"""
NyayaDesk AI Safety & Guardrails
Implements PII redaction/restoration, prompt injection defense, and output labeling.
"""

import re
from typing import Dict, Tuple

# --------------------------------------------------------------------------
# 1. PII Redaction & Restoration
# --------------------------------------------------------------------------

# Regex Patterns for Common Indian Personal Identifiable Information (PII)
PHONE_REGEX = re.compile(r'(?:\+91[-\s]?)?[6-9]\d{4}[-\s]?\d{5}\b')
EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b')
AADHAAR_REGEX = re.compile(r'\b\d{4}\s\d{4}\s\d{4}\b|\b\d{12}\b')
PAN_REGEX = re.compile(r'\b[A-Z]{5}[0-9]{4}[A-Z]\b')
ADDRESS_PATTERNS = [
    re.compile(r'\b(?:Plot|Flat|H\.No|House|Door|Street|Road|Nagar|Colony|Sector|Lane|Enclave|Apartment|Apt|Bldg)\b[^;\n\.\)]{4,120}?\b[1-9][0-9]{5}\b', re.IGNORECASE),
    re.compile(r'\b(?:Plot|Flat|H\.No|House|Door|Street|Road|Nagar|Colony|Sector|Lane|Enclave)\b[^\n,]{2,40}(?:,\s*[^,\n]{2,40}){1,4}', re.IGNORECASE)
]

def redact_pii(text: str) -> Tuple[str, Dict[str, str]]:
    """
    Redacts phone numbers, emails, Aadhaar-like numbers, PANs, and addresses
    with numbered placeholders.
    Returns (redacted_text, placeholder_to_original_map).
    """
    if not text:
        return "", {}

    redaction_map: Dict[str, str] = {}
    counters = {"PHONE": 0, "EMAIL": 0, "AADHAAR": 0, "PAN": 0, "ADDRESS": 0}

    # 1. Redact Emails
    def replace_email(match):
        original = match.group(0)
        counters["EMAIL"] += 1
        placeholder = f"[REDACTED_EMAIL_{counters['EMAIL']}]"
        redaction_map[placeholder] = original
        return placeholder

    redacted = EMAIL_REGEX.sub(replace_email, text)

    # 2. Redact Aadhaar (12-digit / 4-4-4)
    def replace_aadhaar(match):
        original = match.group(0)
        # Avoid redacting typical 12-digit timestamps or CNR-like non-Aadhaar
        cleaned = re.sub(r'\s', '', original)
        if len(cleaned) == 12 and cleaned.isdigit():
            counters["AADHAAR"] += 1
            placeholder = f"[REDACTED_AADHAAR_{counters['AADHAAR']}]"
            redaction_map[placeholder] = original
            return placeholder
        return original

    redacted = AADHAAR_REGEX.sub(replace_aadhaar, redacted)

    # 3. Redact PAN Cards
    def replace_pan(match):
        original = match.group(0)
        counters["PAN"] += 1
        placeholder = f"[REDACTED_PAN_{counters['PAN']}]"
        redaction_map[placeholder] = original
        return placeholder

    redacted = PAN_REGEX.sub(replace_pan, redacted)

    # 4. Redact Phones
    def replace_phone(match):
        original = match.group(0)
        counters["PHONE"] += 1
        placeholder = f"[REDACTED_PHONE_{counters['PHONE']}]"
        redaction_map[placeholder] = original
        return placeholder

    redacted = PHONE_REGEX.sub(replace_phone, redacted)

    # 5. Redact Addresses with PIN codes
    for pat in ADDRESS_PATTERNS:
        def replace_addr(match):
            original = match.group(0)
            counters["ADDRESS"] += 1
            placeholder = f"[REDACTED_ADDRESS_{counters['ADDRESS']}]"
            redaction_map[placeholder] = original
            return placeholder
        redacted = pat.sub(replace_addr, redacted)

    return redacted, redaction_map


def restore_pii(text: str, redaction_map: Dict[str, str]) -> str:
    """
    Restores redacted placeholders back to their original values in the model output.
    """
    if not text or not redaction_map:
        return text or ""

    restored = text
    for placeholder, original in redaction_map.items():
        restored = restored.replace(placeholder, original)
    return restored


# --------------------------------------------------------------------------
# 2. Prompt-Injection Defense
# --------------------------------------------------------------------------

SUSPICIOUS_INJECTION_PATTERNS = [
    re.compile(r'ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions', re.IGNORECASE),
    re.compile(r'system\s+override', re.IGNORECASE),
    re.compile(r'you\s+are\s+now\s+(?:in\s+)?developer\s+mode', re.IGNORECASE),
    re.compile(r'forget\s+your\s+instructions', re.IGNORECASE),
    re.compile(r'approve\s+this\s+case\s+(?:unconditionally|immediately|automatically)', re.IGNORECASE),
    re.compile(r'disregard\s+(?:all\s+)?court\s+rules', re.IGNORECASE),
    re.compile(r'jailbreak', re.IGNORECASE),
    re.compile(r'as\s+an\s+unrestricted\s+ai', re.IGNORECASE),
]

def detect_prompt_injection(text: str) -> Tuple[bool, str]:
    """
    Scans text for common prompt injection and override attacks.
    Returns (is_suspicious, matched_pattern_description).
    """
    if not text:
        return False, ""

    for pat in SUSPICIOUS_INJECTION_PATTERNS:
        m = pat.search(text)
        if m:
            return True, f"Suspicious override pattern detected: '{m.group(0)}'"
    return False, ""


def wrap_untrusted_data(text: str, tag: str = "UNTRUSTED_DATA") -> str:
    """
    Encloses user messages or uploaded documents in strict XML-style delimiters,
    escaping closing tags to prevent delimiter breakout attacks.
    """
    clean_text = (text or "").replace(f"</{tag}>", f"<\\/{tag}>")
    return f"<{tag} is_data_only=\"true\">\n{clean_text}\n</{tag}>"

# Aliases
wrap_untrusted_input = wrap_untrusted_data
scan_prompt_injection = detect_prompt_injection


def sanitize_for_prompt(text: str) -> str:
    """Sanitizes text by stripping non-printable characters and excess control chars."""
    if not text:
        return ""
    cleaned = "".join(ch for ch in str(text) if ch.isprintable() or ch in "\n\r\t ")
    return cleaned.strip()



# --------------------------------------------------------------------------
# 3. Output Safety & Mandatory Review Label
# --------------------------------------------------------------------------

AI_REVIEW_BANNER = "⚖️ AI-generated, review before use"

def apply_review_label(text: str, is_html: bool = False) -> str:
    """
    Appends the standard mandatory AI review label to any generated output.
    """
    if not text:
        return ""
    if AI_REVIEW_BANNER in text:
        return text

    if is_html:
        badge_html = f'<div class="ai-review-notice" style="margin-top: 8px; font-size: 0.72rem; color: var(--color-text-muted);"><span class="badge badge-outline" style="font-size: 0.65rem;">{AI_REVIEW_BANNER}</span></div>'
        return f"{text}\n{badge_html}"

    return f"{text}\n\n*{AI_REVIEW_BANNER}*"
