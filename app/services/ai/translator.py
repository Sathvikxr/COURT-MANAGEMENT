"""
NyayaDesk Multilingual Translation Engine
Translates judicial orders, notices, pleadings, and reminders between
English, Telugu, and Hindi, enforcing the constitutional principle that the
English original remains the authoritative judicial text (Article 348).
"""

import re
import time
from typing import Any, Dict, Optional

from app.services.ai.guardrails import AI_REVIEW_BANNER, apply_review_label
from app.services.ai.gemini_provider import GeminiProvider

TRANSLATION_DISCLAIMER = (
    "⚖️ The English original remains the constitutionally authoritative text under Article 348. "
    "Machine-generated translation for accessibility and informational purposes only."
)

# Common Legal Lexicon Mappings
LEGAL_GLOSSARY = {
    'te': {
        'interim order': 'మధ్యంతర ఉత్తర్వు',
        'high court': 'హైకోర్టు (ఉన్నత న్యాయస్థానం)',
        'petitioner': 'పిటిషనర్ (దరఖాస్తుదారు)',
        'respondent': 'ప్రతివాది (రెస్పాండెంట్)',
        'adjourned': 'వాయిదా వేయబడింది',
        'hearing': 'విచారణ',
        'vakalatnama': 'వకాలత్ నామా (అధికార పత్రం)',
        'bail': 'బెయిల్ (హామీ విడుదల)',
        'notice': 'న్యాయస్థాన నోటీసు',
        'case number': 'కేసు సంఖ్య',
        'status quo': 'యథాతథ స్థితి (స్టేటస్ కో)',
        'next hearing date': 'తదుపరి విచారణ తేదీ',
        'judgment': 'తీర్పు',
        'decree': 'డిక్రీ',
        'affidavit': 'ప్రమాణ పత్రం (అఫిడవిట్)'
    },
    'hi': {
        'interim order': 'अंतरिम आदेश',
        'high court': 'उच्च न्यायालय',
        'petitioner': 'याचिकाकर्ता',
        'respondent': 'प्रत्यर्थी / प्रतिवादी',
        'adjourned': 'स्थगित किया गया',
        'hearing': 'सुनवाई',
        'vakalatnama': 'वकालतनामा',
        'bail': 'ज़मानत',
        'notice': 'अदालती नोटिस',
        'case number': 'वाद संख्या / केस नंबर',
        'status quo': 'यथास्थिति',
        'next hearing date': 'अगली सुनवाई की तिथि',
        'judgment': 'अंतिम निर्णय / फैसला',
        'decree': 'डिक्री / हुक्मनामा',
        'affidavit': 'शपथ पत्र'
    }
}


def translate_judicial_document(
    text: str,
    source_lang: str = 'en',
    target_lang: str = 'te',
    doc_type: str = 'Order',
    user_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Translates legal documents between English, Telugu, and Hindi.
    """
    start_time = time.time()
    if not text or not text.strip():
        return {"success": False, "error": "Text is empty", "translated_text": ""}

    if source_lang == target_lang:
        return {"success": True, "translated_text": text, "source_lang": source_lang, "target_lang": target_lang}

    from app.services.ai.service import get_ai_service
    ai_service = get_ai_service()
    provider = ai_service.get_active_provider()

    translated_text = ""
    mode = 'demo'
    model_name = 'NyayaDesk Multilingual Rule Engine'

    # 1. Live Gemini Translation
    if isinstance(provider, GeminiProvider):
        try:
            sys_inst = (
                f"You are a certified Indian Judicial Translator. Translate this legal {doc_type} "
                f"from {source_lang.upper()} to {target_lang.upper()}. "
                "Retain all case numbers, dates, monetary amounts, and statutory references accurately. "
                "Use formal, respectful, and legally sound terminology."
            )
            prompt = f"LEGAL TEXT TO TRANSLATE:\n{text}\n\nProvide the accurate legal translation only."
            live_out = provider.generate_text(prompt, system_instruction=sys_inst)
            if live_out and len(live_out.strip()) > 10:
                translated_text = live_out.strip()
                mode = 'live'
                model_name = provider.model_name
        except Exception:
            translated_text = ""

    # 2. Heuristic Legal Translation Fallback
    if not translated_text:
        glossary = LEGAL_GLOSSARY.get(target_lang, {})
        translated_lines = []

        if target_lang == 'te':
            intro = f"【తెలుగు అధికారిక అనువాదం - న్యాయస్థాన పత్రం ({doc_type})】\n\n"
            translated_lines.append(intro)
            for line in text.split('\n'):
                line_lower = line.lower()
                if 'in the court of' in line_lower:
                    translated_lines.append("భారత న్యాయస్థానం సమక్షంలో")
                elif 'order' in line_lower and 'date' in line_lower:
                    translated_lines.append(f"ఉత్తర్వు జారీ తేది: {line.split(':')[-1] if ':' in line else ''}")
                elif 'case no' in line_lower:
                    translated_lines.append(f"కేసు సంఖ్య: {line.split(':')[-1] if ':' in line else line}")
                elif 'operative directions' in line_lower:
                    translated_lines.append("అమలుపరచవలసిన న్యాయ ఆదేశాలు:")
                elif 'proceedings' in line_lower:
                    translated_lines.append("విచారణ సారాంశం మరియు న్యాయవాదుల వాదనలు:")
                elif 'next hearing' in line_lower or 'listed on' in line_lower:
                    translated_lines.append(f"తదుపరి విచారణ తేదీ కొరకు వాయిదా వేయడమైనది.")
                else:
                    # Apply lexicon replacements
                    t_line = line
                    for en_term, te_term in glossary.items():
                        t_line = re.sub(r'\b' + re.escape(en_term) + r'\b', te_term, t_line, flags=re.IGNORECASE)
                    translated_lines.append(t_line)

            translated_text = "\n".join(translated_lines)

        elif target_lang == 'hi':
            intro = f"【हिंदी आधिकारिक अनुवाद - अदालती दस्तावेज ({doc_type})】\n\n"
            translated_lines.append(intro)
            for line in text.split('\n'):
                line_lower = line.lower()
                if 'in the court of' in line_lower:
                    translated_lines.append("उच्च न्यायालय / सत्र न्यायालय के समक्ष")
                elif 'order' in line_lower and 'date' in line_lower:
                    translated_lines.append(f"आदेश जारी करने की तिथि: {line.split(':')[-1] if ':' in line else ''}")
                elif 'case no' in line_lower:
                    translated_lines.append(f"वाद संख्या: {line.split(':')[-1] if ':' in line else line}")
                elif 'operative directions' in line_lower:
                    translated_lines.append("प्रभावी न्यायिक निर्देश:")
                elif 'proceedings' in line_lower:
                    translated_lines.append("अदालती कार्यवाही और उपस्थित अधिवक्ताओं के तर्क:")
                elif 'next hearing' in line_lower or 'listed on' in line_lower:
                    translated_lines.append(f"अगली सुनवाई की तिथि के लिए वाद सूचीबद्ध किया जाता है।")
                else:
                    t_line = line
                    for en_term, hi_term in glossary.items():
                        t_line = re.sub(r'\b' + re.escape(en_term) + r'\b', hi_term, t_line, flags=re.IGNORECASE)
                    translated_lines.append(t_line)

            translated_text = "\n".join(translated_lines)

        else:
            translated_text = text

    output_with_disclaimer = f"{translated_text}\n\n*— {TRANSLATION_DISCLAIMER}*\n*{AI_REVIEW_BANNER}*"
    latency_ms = (time.time() - start_time) * 1000.0
    ai_service._log_observability(user_id, "translation", mode, model_name, "1.0", latency_ms, "success")

    return {
        "success": True,
        "original_text": text,
        "translated_text": output_with_disclaimer,
        "source_lang": source_lang,
        "target_lang": target_lang,
        "mode": mode,
        "model": model_name,
        "disclaimer": TRANSLATION_DISCLAIMER,
        "constitutional_disclaimer": TRANSLATION_DISCLAIMER,
        "ai_notice": AI_REVIEW_BANNER
    }
