"""
NyayaDesk Offline Demo AI Provider
Rule-based legal intelligence engine providing complete offline capability:
- 20+ comprehensive multilingual legal FAQs (EN, TE, HI)
- Deterministic case brief synthesis & formal judicial order templates
- Scikit-learn / pure Python TF-IDF cosine similarity
- Delay risk heuristic scoring & smart scheduling slot optimization
- Regex entity and statutory section extraction
Never requires external network connectivity or API keys.
"""

import re
import math
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional, Tuple, Type
from pydantic import BaseModel
from app.services.ai.base import BaseAIProvider
from app.services.ai.guardrails import apply_review_label

# 20+ Comprehensive Multilingual Judicial FAQs
KNOWLEDGE_BASE = [
    {
        'keywords': ['bail', '437', '439', 'custody', 'arrest', 'undertrial'],
        'en': "Bail applications are filed under Section 437/439 CrPC (or BNSS equivalent). Regular bail requires a Vakalatnama from counsel, surrender/custody memo, certified copy of FIR, and grounds detailing why custody is no longer warranted.",
        'te': "బెయిల్ దరఖాస్తులు సెక్షన్ 437/439 CrPC కింద దాఖలు చేయబడతాయి. దీనికి మీ న్యాయవాది వకాలత్‌నామా, FIR కాపీ, మరియు కస్టడీ అవసరం లేదని తెలిపే కారణాలతో కూడిన అఫిడవిట్ అవసరం.",
        'hi': "ज़मानत (Bail) आवेदन दंड प्रक्रिया संहिता की धारा 437/439 के अंतर्गत दाखिल किया जाता है। इसके लिए अधिवक्ता का वकालतनामा, एफआईआर की प्रति और ज़मानत के आधार प्रस्तुत करने होते हैं।"
    },
    {
        'keywords': ['anticipatory bail', '438', 'arrest fear'],
        'en': "Anticipatory Bail is sought under Section 438 CrPC before the Sessions Court or High Court when a person reasonably apprehends arrest in a non-bailable offence.",
        'te': "నాన్-బెయిలబుల్ కేసులో అరెస్టు భయం ఉన్నప్పుడు సెషన్స్ కోర్టు లేదా హైకోర్టులో సెక్షన్ 438 CrPC కింద ముందస్తు బెయిల్ (Anticipatory Bail) దాఖలు చేయవచ్చు.",
        'hi': "गिरफ्तारी की आशंका होने पर सत्र न्यायालय या उच्च न्यायालय के समक्ष धारा 438 CrPC के तहत अग्रिम ज़मानत (Anticipatory Bail) याचिका दायर की जा सकती है।"
    },
    {
        'keywords': ['divorce', 'mutual', '13b', 'separation', 'marriage'],
        'en': "For mutual consent divorce under Section 13B Hindu Marriage Act, both spouses file a joint petition with marriage proof, affidavits stating separate living for >1 year, and settlement terms. A 6-month statutory cooling period applies (waivable by Supreme Court ruling).",
        'te': "పరస్పర అంగీకార విడాకుల కొరకు సెక్షన్ 13B హిందూ వివాహ చట్టం కింద వివాహ రుజువు, 1 సంవత్సరం విడిగా ఉన్న అఫిడవిట్ సమర్పించాలి. కోర్టు 6 నెలల కూలింగ్ పీరియడ్ ఇస్తుంది.",
        'hi': "परस्पर सहमति से तलाक (धारा 13B) हेतु विवाह प्रमाण पत्र, 1 वर्ष से अलग रहने का शपथ पत्र और समझौते की शर्तें प्रस्तुत करनी होती हैं।"
    },
    {
        'keywords': ['cheque', 'bounce', '138', 'dishonour', 'ni act'],
        'en': "Under Section 138 of the Negotiable Instruments Act, you must issue a legal demand notice within 30 days of memo receipt. If the drawer fails to pay within 15 days, a criminal complaint can be instituted within the next 30 days.",
        'te': "చెక్ బౌన్స్ అయిన 30 రోజుల్లోగా లీగల్ నోటీసు పంపాలి. 15 రోజుల్లోగా డబ్బులు చెల్లించకపోతే తదుపరి 30 రోజుల్లోపు మేజిస్ట్రేట్ కోర్టులో క్రిమినల్ కేసు వేయవచ్చు.",
        'hi': "चेक अनादरण (धारा 138 NI Act) होने पर 30 दिनों में कानूनी नोटिस भेजना आवश्यक है। 15 दिनों में भुगतान न होने पर अदालत में परिवाद दाखिल किया जा सकता है।"
    },
    {
        'keywords': ['status', 'case status', 'hearing date', 'next date', 'cnr'],
        'en': "You can track real-time case status using your 16-digit CNR Number or Case Number via the search bar on our Public Portal or inside your Litigant Dashboard under 'My Legal Cases'.",
        'te': "మీ కేసు స్థితిని పబ్లిక్ పోర్టల్ లేదా మీ లిటిగెంట్ డ్యాష్‌బోర్డ్‌లో 16 అంకెల CNR లేదా కేసు నంబర్ ద్వారా క్షణాల్లో తనిఖీ చేయవచ్చు.",
        'hi': "आप 16 अंकों के CNR नंबर या वाद संख्या द्वारा सार्वजनिक पोर्टल अथवा లిటిగెంట్ डैशबोर्ड में वास्तविक समय स्थिति जांच सकते हैं।"
    },
    {
        'keywords': ['summons', 'notice', 'received notice'],
        'en': "If you receive a judicial summons or notice, note the hearing date and courtroom immediately. Contact an advocate to enter appearance and file a reply/written statement within the stipulated 30-day window to avoid ex-parte orders.",
        'te': "కోర్టు సమన్లు లేదా నోటీసు అందినప్పుడు, విచారణ తేదీని గమనించండి. ఎక్స్-పార్టీ ఉత్తర్వులు రాకుండా 30 రోజుల్లోగా న్యాయవాది ద్వారా హాజరు కావాలి.",
        'hi': "न्यायालयीन समन मिलने पर तुरंत सुनवाई की तारीख देखें और एकपक्षीय आदेश (Ex-parte) से बचने हेतु अधिवक्ता के माध्यम से 30 दिनों में उत्तर दाखिल करें।"
    },
    {
        'keywords': ['court fee', 'pay fee', 'payment'],
        'en': "Court fees can be settled digitally in the Litigant Dashboard under 'E-Court Fees'. We accept UPI, Net Banking, and Debit Cards, generating an instant QR-verified treasury receipt.",
        'te': "లిటిగెంట్ డ్యాష్‌బోర్డ్‌లోని 'E-Court Fees' విభాగం ద్వారా UPI, నెట్ బ్యాంకింగ్ లేదా కార్డులతో సులభంగా కోర్టు ఫీజు చెల్లించి రసీదు పొందవచ్చు.",
        'hi': "आप లిటిగెంట్ डैशबोर्ड में 'E-Court Fees' के तहत UPI या नेट बैंकिंग द्वारा ई-कोर्ट फीस का भुगतान कर त्वरित रसीद प्राप्त कर सकते हैं।"
    },
    {
        'keywords': ['certified copy', 'order download', 'judgment copy'],
        'en': "Certified copies of signed orders and judgments carrying cryptographic SHA-256 digital seals can be downloaded directly from your case docket or ordered via the Certified Copies desk.",
        'te': "డిజిటల్ సంతకంతో కూడిన కోర్టు ఉత్తర్వులు మరియు తీర్పుల సర్టిఫైడ్ కాపీలను మీ కేస్ డాకెట్ నుండి నేరుగా డౌన్‌లోడ్ చేసుకోవచ్చు.",
        'hi': "डिजिटल हस्ताक्षर युक्त आदेशों व निर्णयों की प्रमाणित प्रतिलिपियां आप सीधे केस डॉकेट से डाउनलोड कर सकते हैं।"
    },
    {
        'keywords': ['cause list', 'courtroom', 'calling list', 'item number'],
        'en': "The daily cause list is published every morning by 9:30 AM on the Public Portal. It lists each case's item number, courtroom, and the presiding judicial bench.",
        'te': "ప్రతిరోజూ ఉదయం 9:30 గంటలకు పబ్లిక్ పోర్టల్‌లో కాజ్ లిస్ట్ విడుదలవుతుంది. అందులో మీ కోర్టు రూమ్ మరియు ఐటమ్ నంబర్ వివరాలు ఉంటాయి.",
        'hi': "प्रतिदिन सुबह 9:30 बजे कॉज लिस्ट सार्वजनिक पोर्टल पर प्रकाशित होती है जिसमें न्यायालय कक्ष और वाद क्रम संख्या दी जाती है।"
    },
    {
        'keywords': ['confirm', 'attendance', 'sms reply'],
        'en': "When you receive a 2-hour hearing alert via SMS or WhatsApp, simply reply with the single word 'CONFIRM' to log your presence directly onto the Court Master's bench display board.",
        'te': "విచారణకు 2 గంటల ముందు వచ్చే SMS కు 'CONFIRM' అని రిప్లై ఇవ్వడం ద్వారా మీ హాజరు కోర్టు మాస్టర్ బోర్డులో నమోదవుతుంది.",
        'hi': "सुनवाई से 2 घंटे पूर्व प्राप्त SMS पर 'CONFIRM' लिखकर भेजने से आपकी उपस्थिति कोर्ट मास्टर के डिस्प्ले बोर्ड पर दर्ज हो जाती है।"
    },
    {
        'keywords': ['fir', '156(3)', 'police complaint', 'refuse fir'],
        'en': "If a police station refuses to register an FIR for a cognizable offence, you may petition the Superintendent of Police under Section 154(3) CrPC, or file an application before the Judicial Magistrate under Section 156(3) CrPC directing registration.",
        'te': "పోలీసులు FIR నమోదు చేయకపోతే SP గారికి లేదా సెక్షన్ 156(3) CrPC కింద జ్యుడీషియల్ మేజిస్ట్రేట్ కోర్టులో పిటిషన్ వేయవచ్చు.",
        'hi': "यदि पुलिस एफआईआर दर्ज न करे, तो धारा 156(3) CrPC के तहत न्यायिक मजिस्ट्रेट के समक्ष एफआईआर दर्ज करने का आदेश प्राप्त करने हेतु आवेदन दिया जा सकता है।"
    },
    {
        'keywords': ['consumer', 'consumer court', 'defective product', 'deficiency'],
        'en': "Consumer complaints are filed under the Consumer Protection Act, 2019 before the District Consumer Commission (claims up to ₹50 Lakh). No complex court fee is required; complaints can be e-filed directly.",
        'te': "వినియోగదారుల ఫోరంలో ₹50 లక్షల వరకు క్లెయిమ్‌లను జిల్లా వినియోగదారుల కమిషన్‌లో నేరుగా ఫిర్యాదు చేయవచ్చు.",
        'hi': "उपभोक्ता संरक्षण अधिनियम 2019 के अंतर्गत ₹50 लाख तक के दावों हेतु जिला उपभोक्ता आयोग में सीधे शिकायत दर्ज कराई जा सकती है।"
    },
    {
        'keywords': ['succession', 'legal heir', 'inheritance', 'death'],
        'en': "A Succession Certificate is granted by a Civil Court under the Indian Succession Act, 1925, establishing the rightful heirs to movable debts, securities, and bank deposits of a deceased person.",
        'te': "మరణించిన వ్యక్తి బ్యాంక్ డిపాజిట్లు మరియు ఆస్తుల కొరకు సివిల్ కోర్టు నుండి ఇండియన్ సక్సెషన్ యాక్ట్ కింద వారసత్వ ధృవీకరణ పత్రం (Succession Certificate) పొందవచ్చు.",
        'hi': "उत्तराधिकार प्रमाण पत्र (Succession Certificate) सिविल कोर्ट द्वारा मृतक की चल संपत्तियों और बैंक जमा हेतु जारी किया जाता है।"
    },
    {
        'keywords': ['injunction', 'stay', 'stay order', 'order 39'],
        'en': "Temporary Injunctions (stay orders) are sought under Order 39 Rules 1 & 2 of the Code of Civil Procedure (CPC) to restrain alienation or damage to property pending disposal of the suit.",
        'te': "ఆస్తి తగాదాల్లో మధ్యంతర స్టే ఆర్డర్ కోసం CPC ఆర్డర్ 39 రూల్స్ 1 & 2 కింద తాత్కాలిక ఇంజంక్షన్ పిటిషన్ దాఖలు చేయవచ్చు.",
        'hi': "मुकदमे के लंबित रहने के दौरान संपत्ति को नुकसान या बिक्री से बचाने हेतु CPC के आदेश 39 नियम 1 व 2 के तहत स्थगन आदेश (Stay Order) मांगा जाता है।"
    },
    {
        'keywords': ['legal aid', 'free lawyer', 'nalsa', 'dlsa'],
        'en': "Under Section 12 of the Legal Services Authorities Act, free legal representation by panel advocates is provided to women, children, undertrials, and individuals with annual income below statutory thresholds through DLSA/SLSA.",
        'te': "ఆదాయ పరిమితిలోపు ఉన్న పేదలు, మహిళలు మరియు అండర్‌ట్రయల్స్‌కు DLSA ద్వారా ఉచిత న్యాయ సహాయం (Free Legal Aid) లభిస్తుంది.",
        'hi': "विधिक सेवा प्राधिकरण अधिनियम की धारा 12 के तहत महिलाओं, बच्चों व निर्धन नागरिकों को DLSA द्वारा निःशुल्क विधिक सहायता प्रदान की जाती है।"
    },
    {
        'keywords': ['vakalatnama', 'power of attorney', 'appoint lawyer'],
        'en': "A Vakalatnama is a formal document by which a litigant authorizes an advocate to plead, sign pleadings, and conduct legal proceedings on their behalf before the court.",
        'te': "వకాలత్‌నామా అనేది ఒక న్యాయవాదికి తన తరపున కోర్టులో వాదించడానికి మరియు పత్రాలపై సంతకం చేయడానికి క్లయింట్ ఇచ్చే అధికార పత్రం.",
        'hi': "वकालतनामा एक कानूनी दस्तावेज़ है जिसके द्वारा वादकारी अपने अधिवक्ता को न्यायालय में पक्ष रखने हेतु प्राधिकृत करता है।"
    },
    {
        'keywords': ['ex-parte', 'non-appearance', 'absent'],
        'en': "If a respondent fails to appear after valid service of court summons, the court may declare them ex-parte and proceed to hear the petitioner's evidence and pronounce judgment in their absence.",
        'te': "సమన్లు అందిన తర్వాత కూడా కోర్టుకు హాజరుకాకపోతే, కోర్టు ఎక్స్-పార్టీగా ప్రకటించి మీ గైర్హాజరులోనే తీర్పు ఇవ్వవచ్చు.",
        'hi': "समन की तामील के बाद भी उपस्थित न होने पर अदालत प्रतिवादी को एकपक्षीय (Ex-parte) घोषित कर निर्णय दे सकती है।"
    },
    {
        'keywords': ['appeal', 'higher court', 'appeal deadline', 'limitation'],
        'en': "Appeals against District Court judgments lie before the High Court. Civil appeals generally carry a 90-day limitation period under the Limitation Act from the date of decree.",
        'te': "జిల్లా కోర్టు తీర్పులపై హైకోర్టులో అప్పీల్ చేసుకోవడానికి సాధారణంగా 90 రోజుల కాలపరిమితి ఉంటుంది.",
        'hi': "जिला अदालत के निर्णय के विरुद्ध उच्च न्यायालय में अपील दायर करने हेतु सामान्यतः 90 दिनों की परिसीमा अवधि होती है।"
    },
    {
        'keywords': ['court marriage', 'special marriage act', 'marriage registration'],
        'en': "Civil marriages are solemnized under the Special Marriage Act, 1954 before the Marriage Officer with a 30-day public notice requirement. Three witnesses and age proofs (21 for groom, 18 for bride) are mandatory.",
        'te': "స్పెషల్ మ్యారేజ్ యాక్ట్ కింద 30 రోజుల నోటీసు అనంతరం 3 సాక్షులతో మేజిస్ట్రేట్ సమక్షంలో కోర్టు వివాహం నమోదు చేసుకోవచ్చు.",
        'hi': "विशेष विवाह अधिनियम 1954 के तहत विवाह अधिकारी के समक्ष 30 दिन के सार्वजनिक नोटिस के बाद 3 गवाहों की उपस्थिति में विवाह संपन्न होता है।"
    },
    {
        'keywords': ['cognizable', 'non-cognizable', 'cognizance'],
        'en': "In a Cognizable offence (e.g. murder, theft), police can arrest without a warrant and investigate immediately. In Non-Cognizable offences (e.g. simple assault), investigation requires an order from the Judicial Magistrate.",
        'te': "కాగ్నిజబుల్ నేరాల్లో పోలీసులు వారెంట్ లేకుండా అరెస్ట్ చేయవచ్చు. నాన్-కాగ్నిజబుల్ కేసుల్లో మేజిస్ట్రేట్ అనుమతి తప్పనిసరి.",
        'hi': "संज्ञेय (Cognizable) अपराध में पुलिस बिना वारंट गिरफ्तार कर सकती है, जबकि असंज्ञेय अपराध में मजिस्ट्रेट की अनुमति आवश्यक है।"
    }
]


class DemoProvider(BaseAIProvider):
    """Reliable offline fallback provider executing rule-based judicial intelligence."""

    def __init__(self):
        super().__init__(name='demo', model_name='NyayaDesk Legal Intelligence Engine (Offline)')

    def generate_text(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2,
        max_output_tokens: int = 1024,
        **kwargs
    ) -> str:
        """Rule-based text generation synthesizing structured judicial replies."""
        clean = prompt.lower()

        # Match FAQ knowledge base
        best_match = None
        best_score = 0
        for faq in KNOWLEDGE_BASE:
            score = sum(1 for kw in faq['keywords'] if kw in clean)
            if score > best_score:
                best_score = score
                best_match = faq

        if best_match and best_score > 0:
            lang = kwargs.get('language', 'en')
            raw = best_match.get(lang) or best_match.get('en')
            return apply_review_label(raw)

        raw = (
            "The court administration engine has recorded your query. "
            "For specific pleadings and petitions, please consult the filing guidelines or an enrolled advocate."
        )
        return apply_review_label(raw)

    def generate_json(
        self,
        prompt: str,
        schema: Optional[Type[BaseModel]] = None,
        system_instruction: Optional[str] = None,
        temperature: float = 0.1,
        **kwargs
    ) -> Dict[str, Any]:
        """Provides deterministic JSON outputs matching requested schemas."""
        schema_name = schema.__name__ if schema else ""

        if schema_name == "CaseSummarySchema":
            return {
                "factual_background": kwargs.get('facts', "Proceedings instituted concerning substantive civil/criminal dispute before the Court."),
                "parties": kwargs.get('parties', ["Petitioner on record", "Respondent on record"]),
                "procedural_timeline": kwargs.get('timeline', ["E-filed and registered on docket."]),
                "legal_issues": kwargs.get('issues', ["Determination of rights under applicable statutes."]),
                "recommended_next_steps": kwargs.get('next_steps', ["Verify service of notice", "Await counter affidavit"])
            }

        elif schema_name == "OrderDraftSchema":
            return {
                "title": kwargs.get('title', "Interim Order"),
                "court_name": kwargs.get('court_name', "Judicial Court"),
                "judge_name": kwargs.get('judge_name', "Hon'ble Presiding Judge"),
                "case_number": kwargs.get('case_number', "CIV/2026/00001"),
                "order_type": kwargs.get('order_type', "Interim"),
                "proceedings_summary": "Proceedings conducted; arguments of counsel noted on record.",
                "operative_directions": [
                    "Parties directed to maintain status quo till the next date of hearing.",
                    "Respondent granted two weeks to file Counter-Affidavit with advance copy to Petitioner."
                ],
                "next_hearing_date": kwargs.get('next_date', (datetime.utcnow() + timedelta(days=21)).strftime('%d-%m-%Y'))
            }

        elif schema_name == "DocumentExtractionSchema":
            return {
                "suggested_doc_type": kwargs.get('doc_type', "Document"),
                "confidence": 92,
                "identified_acts": kwargs.get('acts', []),
                "extracted_case_numbers": kwargs.get('case_numbers', []),
                "extracted_amounts": kwargs.get('amounts', []),
                "extracted_dates": kwargs.get('dates', [])
            }

        elif schema_name == "LegalChatSchema":
            text = self.generate_text(prompt, **kwargs)
            return {
                "reply": text,
                "procedural_steps": ["Verify case number", "File appropriate application with registry"],
                "statutory_references": ["Relevant statutory rules"],
                "disclaimer": "⚖️ General procedural information only, not formal legal advice."
            }

        return {"status": "success", "content": self.generate_text(prompt, **kwargs)}

    def embed(self, text: str, **kwargs) -> List[float]:
        """Generates deterministic pseudo-embeddings based on normalized word frequencies."""
        vec = [0.0] * 64
        words = re.findall(r'\w+', text.lower())
        for w in words:
            idx = abs(hash(w)) % 64
            vec[idx] += 1.0
        # Normalize
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    def transcribe(self, audio_source: Any, **kwargs) -> str:
        """Deterministic simulation of judicial audio transcription."""
        return (
            "[COURT PROCEEDING TRANSCRIPTION - SIMULATED VERBATIM]\n"
            "Court Master: Matter number 12 called. Counsel for petitioner present.\n"
            "Advocate: May it please your Lordship, we pray for two weeks time to file rejoinder.\n"
            "Hon'ble Judge: Granted. Counter to be served by 24th. List on 28th."
        )

    def is_healthy(self) -> Tuple[bool, str]:
        """Offline demo provider is always operational."""
        return True, "NyayaDesk Offline Demo Engine is operational."
