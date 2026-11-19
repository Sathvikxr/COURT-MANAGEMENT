"""
NyayaDesk Fictional Precedent Library & Semantic Vector Search Engine
Embeds 30 invented, clearly synthetic Indian judicial precedents across
diverse legal disciplines (Commercial, Property, Criminal, Bail, Family, NI Act,
Arbitration, Writ, Service, Cyber) into a vector index using numpy cosine similarity
and TF-IDF / Gemini embeddings.
"""

import os
import re
import json
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.models import db, PrecedentLibrary, Order, AILog
from app.services.ai.guardrails import AI_REVIEW_BANNER

# --------------------------------------------------------------------------
# 30 Invented, Clearly Fictional Synthetic Precedents
# --------------------------------------------------------------------------
SYNTHETIC_PRECEDENTS = [
    {
        "citation": "[2024] 1 NyayaLR 101",
        "title": "Aarav Agro Industries v. State Electricity Distribution Corp",
        "court_name": "High Court of Judicature at Delhi",
        "bench": "Hon'ble Justice K. S. Sundaram & Justice Anita Sen",
        "year": 2024,
        "case_type": "Commercial / Contract",
        "statutory_sections": "Indian Contract Act 1872 Section 56 (Frustration), Electricity Act 2003 Section 43",
        "headnote": "Force Majeure cannot be invoked to avoid payment obligations under a power purchase agreement where an alternative grid route remained commercially viable.",
        "key_passages": "Commercial hardship or fluctuations in tariff prices do not constitute frustration of contract under Section 56 of the Contract Act. The doctrine of impossibility applies only when the very substratum of the contract ceases to exist.",
        "full_judgment_text": "The Petitioner, an agro-processing cold chain warehouse, challenged supplemental demand charges billed by the distribution licensee during grid disruptions. Held, that non-availability of subsidized power for a brief period does not excuse contractual performance where grid supply was restored via feeder bypass."
    },
    {
        "citation": "[2024] 1 NyayaLR 102",
        "title": "Kavita Rao & Anr. v. Hyderabad Urban Infrastructure Board",
        "court_name": "High Court of Telangana",
        "bench": "Hon'ble Justice Rameshwar Rao",
        "year": 2024,
        "case_type": "Property / Land Acquisition",
        "statutory_sections": "Right to Fair Compensation Act 2013 Section 24, Constitution Article 300A",
        "headnote": "Failure to deposit compensation in court within statutory five-year period leads to lapse of acquisition proceedings under Section 24(2).",
        "key_passages": "Property rights under Article 300A remain a constitutional and human right. When the State retains physical possession without disbursing adjudicated compensation, the citizen cannot be left indefinitely prejudiced.",
        "full_judgment_text": "The State acquisition of agricultural parcels for ring road expansion was challenged. The State pleaded lack of municipal funds. The Bench held the acquisition lapsed by operation of law and directed restitution of title with solatium."
    },
    {
        "citation": "[2024] 1 NyayaLR 103",
        "title": "Vikramaditya Transport Corp v. Modern Logistics Pvt Ltd",
        "court_name": "High Court of Judicature at Bombay",
        "bench": "Hon'ble Justice Meenakshi Iyer",
        "year": 2024,
        "case_type": "Cheque Bounce / Banking",
        "statutory_sections": "Negotiable Instruments Act 1881 Section 138, 141",
        "headnote": "Independent Non-Executive Directors cannot be arrayed as vicariously liable accused under Section 141 NI Act without specific averment of day-to-day management.",
        "key_passages": "Merely reproducing the statutory language that a director was in charge of corporate affairs is insufficient. The complainant must specify the overt act establishing that the director signed the cheque or managed treasury finances.",
        "full_judgment_text": "Petitioner sought quashing of criminal summons under Section 482 CrPC. Held, criminal process cannot be used as an instrument of coercive leverage against non-executive advisory board members."
    },
    {
        "citation": "[2023] 3 NyayaLR 204",
        "title": "Dr. Sunayana Sen v. Union Medical Council of India",
        "court_name": "High Court of Judicature at Delhi",
        "bench": "Hon'ble Chief Justice Rajesh Sharma",
        "year": 2023,
        "case_type": "Writ / Administrative Law",
        "statutory_sections": "Constitution Article 14, 19(1)(g), National Medical Commission Act 2019",
        "headnote": "Disciplinary suspension of medical license without serving inquiry report or affording personal hearing violates fundamental Audi Alteram Partem.",
        "key_passages": "An adverse administrative ruling that terminates the professional livelihood of a citizen demands rigorous compliance with the principles of natural justice. Post-decisional hearing is not a substitute for pre-decisional inquiry.",
        "full_judgment_text": "Suspension order quashed. The Council was granted liberty to institute fresh disciplinary inquiry in accordance with principles of natural justice within sixty days."
    },
    {
        "citation": "[2023] 3 NyayaLR 205",
        "title": "State of Nyaya (CBI) v. Manasvi & Ors.",
        "court_name": "Supreme Court of Judicature (Appellate Division)",
        "bench": "Hon'ble Justice S. K. Kaul & Justice H. Roy",
        "year": 2023,
        "case_type": "Criminal / Regular Bail",
        "statutory_sections": "Code of Criminal Procedure 1973 Section 439, Prevention of Corruption Act 1988",
        "headnote": "Prolonged incarceration during trial stage without likelihood of early conclusion violates Article 21; bail is the rule and jail is the exception even in economic matters.",
        "key_passages": "Pre-trial detention cannot take the character of punitive punishment. Where evidence is predominantly documentary and already seized by the investigating agency, custody cannot be prolonged merely on the gravity of the allegations.",
        "full_judgment_text": "Respondent was accused of banking consortium loan diversion. Chargesheet was filed and 84 witnesses were cited. Held, since trial was unlikely to conclude within three years, bail granted on strict financial surrender conditions."
    },
    {
        "citation": "[2023] 2 NyayaLR 306",
        "title": "Ananya Urban Developers LLP v. Real Estate Regulatory Authority",
        "court_name": "High Court of Karnataka",
        "bench": "Hon'ble Justice B. V. Nagaraj",
        "year": 2023,
        "case_type": "Consumer / RERA",
        "statutory_sections": "Real Estate (Regulation and Development) Act 2016 Section 18",
        "headnote": "Allottee has unqualified right to seek complete refund of deposited monies along with prescribed MCLR interest upon developer's failure to deliver possession within agreed timeline.",
        "key_passages": "The builder cannot compel an allottee to accept delayed delivery or offer alternative housing units when the statutory occupancy deadline in the registered agreement has expired.",
        "full_judgment_text": "Developer's appeal dismissed with exemplary costs. RERA direction for immediate restitution of Rs. 84,00,000/- with 10.75% interest upheld."
    },
    {
        "citation": "[2023] 2 NyayaLR 307",
        "title": "Rishabh Jain v. Preeti Jain",
        "court_name": "High Court of Judicature at Allahabad",
        "bench": "Hon'ble Justice Devendra Gupta",
        "year": 2023,
        "case_type": "Family / Matrimonial",
        "statutory_sections": "Hindu Marriage Act 1955 Section 13B(2)",
        "headnote": "The statutory six-month waiting period in Section 13B(2) is directory, not mandatory; Family Courts may waive the period if all efforts at reconciliation have failed.",
        "key_passages": "Where spouses have resided separately for over four years, all maintenance and custody claims are settled, and no possibility of cohabitation survives, prolonging the waiting period inflicts needless psychological distress.",
        "full_judgment_text": "Family Court order rejecting waiver application set aside. Decree of mutual divorce granted."
    },
    {
        "citation": "[2023] 1 NyayaLR 408",
        "title": "Bharat Heavy Engineering v. Precision Tooling Systems Ltd",
        "court_name": "High Court of Judicature at Delhi",
        "bench": "Hon'ble Justice Pratibha Singh",
        "year": 2023,
        "case_type": "Arbitration / Commercial",
        "statutory_sections": "Arbitration and Conciliation Act 1996 Section 9, 11",
        "headnote": "Court under Section 9 may grant protective interim injunction against encashment of unconditional bank guarantee only upon establishing egregious fraud or irretrievable injustice.",
        "key_passages": "An unconditional bank guarantee is an independent contractual undertaking. Commercial disputes regarding breach of delivery milestones do not amount to egregious fraud sufficient to restrain guarantee encashment.",
        "full_judgment_text": "Injunction refused. Parties relegated to sole arbitrator appointed under Section 11."
    },
    {
        "citation": "[2022] 4 NyayaLR 509",
        "title": "Consumer Protection Collective v. Swift Telecom Ltd",
        "court_name": "National Consumer Disputes Redressal Commission",
        "bench": "Hon'ble Justice R. K. Agrawal (President)",
        "year": 2022,
        "case_type": "Consumer Protection",
        "statutory_sections": "Consumer Protection Act 2019 Section 2(47), 38",
        "headnote": "Automatic debiting for unsolicited value-added caller tune services constitutes an unfair trade practice and deficiency in service.",
        "key_passages": "Passive consent or failure to opt-out cannot be construed as an affirmative agreement to purchase digital services. Transparent consumer consent must be explicit and verifiable.",
        "full_judgment_text": "Telecom operator directed to refund deducted charges to 42,000 subscribers and deposit Rs. 25,00,000/- in the Consumer Welfare Fund."
    },
    {
        "citation": "[2022] 4 NyayaLR 510",
        "title": "State Police Agency v. Satish Kumar Verma",
        "court_name": "High Court of Punjab and Haryana",
        "bench": "Hon'ble Justice Jasjit Singh",
        "year": 2022,
        "case_type": "Criminal / Anticipatory Bail",
        "statutory_sections": "Code of Criminal Procedure Section 41A, 438",
        "headnote": "Failure of police to record written reasons for arrest under Section 41 CrPC in offences punishable with less than 7 years entitles accused to anticipatory bail protection.",
        "key_passages": "The guidelines in Arnesh Kumar are mandatory checks against arbitrary arrest. Police authorities cannot bypass the statutory notice regime under Section 41A without documenting imminent risk of witness tampering.",
        "full_judgment_text": "Anticipatory bail granted subject to joining investigation upon 48-hour prior written summons."
    },
    {
        "citation": "[2022] 3 NyayaLR 611",
        "title": "Green Earth Foundation v. Central Petrochemical Refinery",
        "court_name": "National Green Tribunal (Principal Bench)",
        "bench": "Hon'ble Justice A. K. Goel & Expert Member Dr. Nagin Nanda",
        "year": 2022,
        "case_type": "Environmental Law",
        "statutory_sections": "Environment (Protection) Act 1986, NGT Act 2010 Section 15",
        "headnote": "Polluter Pays Principle is absolute; industrial units operating without updated Consent to Operate (CTO) must pay environmental restitution damages calculated on turnover.",
        "key_passages": "Environmental clearance conditions are non-negotiable prerequisites. Post-facto regularizations cannot absolve chemical industrial operators from damage caused to local aquifers and agricultural topsoil.",
        "full_judgment_text": "Refinery fined Rs. 18.5 Crores towards local groundwater bioremediation and afforestation."
    },
    {
        "citation": "[2022] 3 NyayaLR 612",
        "title": "Cyber Security Agency v. Rohit Mehra & Ors.",
        "court_name": "High Court of Judicature at Delhi",
        "bench": "Hon'ble Justice Sanjeev Narula",
        "year": 2022,
        "case_type": "Cyber Law / IP",
        "statutory_sections": "Information Technology Act 2000 Section 43, 66, Copyright Act 1957",
        "headnote": "Unauthorised scraping of proprietary court docket database and bypassing API rate-limiters constitutes criminal breach under Section 66 IT Act.",
        "key_passages": "Public judicial records are accessible for legitimate scrutiny, but commercial mass harvesting that degrades judicial infrastructure and compromises non-public draft judgments violates statutory computer protection norms.",
        "full_judgment_text": "Injunction granted restraining data scraping. Defendant directed to purge cached server dumps."
    },
    {
        "citation": "[2022] 2 NyayaLR 713",
        "title": "Shalini Nair v. Principal Kendriya Vidyalaya & Ors.",
        "court_name": "Central Administrative Tribunal (Principal Bench)",
        "bench": "Hon'ble Vice Chairman R. N. Singh",
        "year": 2022,
        "case_type": "Service Law",
        "statutory_sections": "Maternity Benefit Act 1961 Section 5, Central Civil Services (Leave) Rules",
        "headnote": "Contractual and ad-hoc government employees are entitled to full 26-week paid maternity leave on par with regular permanent civil servants.",
        "key_passages": "Maternity benefits are an integral facets of gender justice and human dignity under Article 21. Denying equal leave on the technical pretext of contractual tenure is unconstitutional discrimination.",
        "full_judgment_text": "Writ allowed. Withheld maternity remuneration directed to be paid with 6% interest within 30 days."
    },
    {
        "citation": "[2022] 2 NyayaLR 714",
        "title": "Grand Horizon Hospitality v. City Municipal Corporation",
        "court_name": "High Court of Judicature at Madras",
        "bench": "Hon'ble Justice M. Sundar",
        "year": 2022,
        "case_type": "Municipal / Licensing",
        "statutory_sections": "Municipal Corporation Act Section 279, Doctrine of Proportionality",
        "headnote": "Summary sealing of hotel premises for minor fire-exit signage defects without provisional cure notice violates administrative proportionality.",
        "key_passages": "The power of closure is an extreme measure of last resort. Regulatory bodies must issue graduated compliance notices allowing reasonable periods for rectification unless imminent life safety peril is demonstrated.",
        "full_judgment_text": "Sealing de-notified upon submission of safety compliance undertaking and payment of compounding fee."
    },
    {
        "citation": "[2022] 1 NyayaLR 815",
        "title": "Naveen Chand v. Union of India (Armed Forces Tribunal)",
        "court_name": "Supreme Court of Judicature (Appellate Division)",
        "bench": "Hon'ble Justice D. Y. Chandrachud & Justice Surya Kant",
        "year": 2022,
        "case_type": "Military / Pension Law",
        "statutory_sections": "Pension Regulations for the Army 1961 Regulation 173",
        "headnote": "Disability contracted during military service in high altitude operational deployments is presumed attributable to service unless the Medical Board proves pre-existing origin.",
        "key_passages": "The soldier who enters service in sound physical condition is entitled to the benefit of doubt. The onus lies strictly on the military establishment to demonstrate that physical deterioration was independent of rigorous field conditions.",
        "full_judgment_text": "Disability pension with broad-banding benefits restored with arrears for three years prior to petition filing."
    },
    {
        "citation": "[2021] 4 NyayaLR 916",
        "title": "Apex Fintech Solutions v. Reserve Bank of India",
        "court_name": "High Court of Judicature at Delhi",
        "bench": "Hon'ble Justice Vipin Sanghi",
        "year": 2021,
        "case_type": "Banking / Administrative Law",
        "statutory_sections": "Payment and Settlement Systems Act 2007 Section 18",
        "headnote": "Central Bank regulatory circulars mandating local data localization for financial transactions are valid exercises of sovereign monetary and cybersecurity oversight.",
        "key_passages": "National financial stability and jurisdictional access to real-time audit trails outweigh multinational business convenience. The regulatory requirement of domestic data storage is neither arbitrary nor disproportionate.",
        "full_judgment_text": "Challenge to regulatory localization circular dismissed."
    },
    {
        "citation": "[2021] 4 NyayaLR 917",
        "title": "Vandana Sharma v. Alok Sharma",
        "court_name": "High Court of Judicature at Rajasthan",
        "bench": "Hon'ble Justice Sandeep Mehta",
        "year": 2021,
        "case_type": "Family / Custody",
        "statutory_sections": "Guardians and Wards Act 1890 Section 17, 25",
        "headnote": "Welfare of the minor child is the paramount consideration; financial superiority of one parent cannot override emotional bonding and primary maternal care of a toddler.",
        "key_passages": "Custody disputes are not adjudications of parental rights, but tests of the child's psychological and emotional security. A child under five years of age ordinarily requires the daily nurturing care of the mother.",
        "full_judgment_text": "Primary custody awarded to mother with comprehensive weekend visitation and festival shared-time rights for father."
    },
    {
        "citation": "[2021] 3 NyayaLR 1018",
        "title": "M/s Metro Infrastructure v. General Manager Northern Railways",
        "court_name": "High Court of Judicature at Delhi",
        "bench": "Hon'ble Justice Rekha Palli",
        "year": 2021,
        "case_type": "Arbitration",
        "statutory_sections": "Arbitration and Conciliation Act Section 12(5), Seventh Schedule",
        "headnote": "Unilateral appointment of an employee or serving official as sole arbitrator is impermissible and void ab initio in view of statutory neutrality mandates.",
        "key_passages": "The statutory bar under Section 12(5) read with the Seventh Schedule cannot be waived by an agreement executed prior to the dispute arising. Impartiality of the tribunal is the cornerstone of arbitral legitimacy.",
        "full_judgment_text": "Arbitrator mandate terminated; independent retired High Court judge appointed as substitute sole arbitrator."
    },
    {
        "citation": "[2021] 3 NyayaLR 1019",
        "title": "State of Nyaya v. Tariq Ahmed (Bail in Narcotics Matter)",
        "court_name": "High Court of Jammu & Kashmir and Ladakh",
        "bench": "Hon'ble Justice Ali Mohammad Magrey",
        "year": 2021,
        "case_type": "Criminal / NDPS",
        "statutory_sections": "Narcotic Drugs and Psychotropic Substances Act 1985 Section 37, 50",
        "headnote": "Non-compliance with Section 50 statutory search warnings in personal searches renders recovery suspect and establishes reasonable grounds under Section 37 for bail.",
        "key_passages": "Section 50 provides an invaluable statutory safeguard to the citizen. The option to be searched before a Gazetted Officer or Magistrate must be conveyed unambiguously, not as a casual formality.",
        "full_judgment_text": "Bail granted upon furnishing two local sureties of Rs. 1,00,000/- each."
    },
    {
        "citation": "[2021] 2 NyayaLR 1120",
        "title": "Bio-Pharma Labs v. Generic Therapeutics Pvt Ltd",
        "court_name": "High Court of Judicature at Bombay",
        "bench": "Hon'ble Justice S. J. Kathawalla",
        "year": 2021,
        "case_type": "Intellectual Property / Patents",
        "statutory_sections": "Patents Act 1970 Section 3(d), 48",
        "headnote": "Evergreening of pharmaceutical patents through minor polymorph modifications without demonstrating enhanced therapeutic efficacy is barred under Section 3(d).",
        "key_passages": "Section 3(d) was enacted to safeguard public health and encourage genuine incremental innovation. A mere crystalline form of a known substance cannot claim patent monopoly without clear clinical evidence of enhanced efficacy.",
        "full_judgment_text": "Interim injunction against generic drug manufacture denied; expeditious trial ordered."
    },
    {
        "citation": "[2021] 2 NyayaLR 1121",
        "title": "Dinesh Kumar v. Election Commission of Nyaya",
        "court_name": "High Court of Judicature at Patna",
        "bench": "Hon'ble Justice Sanjay Karol",
        "year": 2021,
        "case_type": "Election / Constitutional Law",
        "statutory_sections": "Representation of the People Act 1951 Section 33A, 100",
        "headnote": "Non-disclosure of pending criminal cases where charges have been framed by a competent magistrate vitiates election on grounds of undue influence.",
        "key_passages": "The voter's right to know the antecedent criminal background of a candidate is a facet of democratic franchise under Article 19(1)(a). Intentional suppression of trial dockets invalidates the mandate.",
        "full_judgment_text": "Election petition allowed; seat declared vacant and fresh by-election ordered."
    },
    {
        "citation": "[2020] 4 NyayaLR 1222",
        "title": "Heritage Preservation Trust v. Smart City Development Authority",
        "court_name": "High Court of Judicature at Calcutta",
        "bench": "Hon'ble Justice Thottathil B. Radhakrishnan",
        "year": 2020,
        "case_type": "Public Interest Litigation",
        "statutory_sections": "Ancient Monuments and Archaeological Sites Act 1958, Public Trust Doctrine",
        "headnote": "Urban redevelopment projects cannot demolish Grade-I heritage buildings without prior approval from statutory Heritage Conservation Committee.",
        "key_passages": "Historical and architectural heritage is held in public trust for future generations. Economic modernization must harmonize with cultural conservation.",
        "full_judgment_text": "Demolition notices quashed; structural preservation and adaptive reuse mandated."
    },
    {
        "citation": "[2020] 4 NyayaLR 1223",
        "title": "Karan Malhotra v. State Cyber Crime Cell",
        "court_name": "High Court of Judicature at Delhi",
        "bench": "Hon'ble Justice Mukta Gupta",
        "year": 2020,
        "case_type": "Criminal / Digital Evidence",
        "statutory_sections": "Indian Evidence Act 1872 Section 65B(4)",
        "headnote": "Electronic records in the form of WhatsApp chat exports and server call detail records are inadmissible in criminal trials without a contemporaneous Section 65B certificate.",
        "key_passages": "The requirements of Section 65B are mandatory conditions precedent to ensure electronic media has not been tampered with or corrupted during export and custody.",
        "full_judgment_text": "Uncertified electronic chat printouts excluded from evidentiary consideration."
    },
    {
        "citation": "[2020] 3 NyayaLR 1324",
        "title": "Sunil Varma v. Zenith Life Insurance Co",
        "court_name": "High Court of Judicature at Madhya Pradesh",
        "bench": "Hon'ble Justice Vivek Agarwal",
        "year": 2020,
        "case_type": "Insurance / Consumer",
        "statutory_sections": "Insurance Act 1938 Section 45",
        "headnote": "Repudiation of life insurance claim on ground of pre-existing disease is invalid after expiry of three years from policy commencement under amended Section 45.",
        "key_passages": "Section 45 creates an absolute statutory quietus after three years. Insurers who collect premiums cannot invoke pre-existing lifestyle ailments after the insured passes away.",
        "full_judgment_text": "Insurer directed to disburse policy sum assured of Rs. 50,00,000/- with 9% interest from date of claim repudiation."
    },
    {
        "citation": "[2020] 3 NyayaLR 1325",
        "title": "National Transport Workers Union v. State Transport Corp",
        "court_name": "High Court of Judicature at Kerala",
        "bench": "Hon'ble Justice C. S. Dias",
        "year": 2020,
        "case_type": "Labour / Industrial Law",
        "statutory_sections": "Industrial Disputes Act 1947 Section 33C(2), 25F",
        "headnote": "Retrenchment of daily-rated transport conductors without paying one month's notice and statutory retrenchment compensation is void ab initio.",
        "key_passages": "Continuous service of 240 days in the preceding 12 months confers protective statutory rights under Section 25F. Management cannot defeat regularisation through artificial breaks in muster rolls.",
        "full_judgment_text": "Reinstatement with 50% back-wages and continuity of service ordered."
    },
    {
        "citation": "[2020] 2 NyayaLR 1426",
        "title": "Sangeeta Roy v. High Court Registry of Nyaya",
        "court_name": "High Court of Judicature at Delhi",
        "bench": "Hon'ble Justice S. Muralidhar & Justice Talwant Singh",
        "year": 2020,
        "case_type": "Judicial Service / Disability Rights",
        "statutory_sections": "Rights of Persons with Disabilities Act 2016 Section 34",
        "headnote": "Visual impairment or physical disability cannot be a disqualification for appointment to State Higher Judicial Service if candidate qualifies competitive examination.",
        "key_passages": "Reasonable accommodation is a constitutional guarantee. Modern assistive speech technology and screen readers enable visually impaired jurists to discharge adjudicatory functions with equal distinction.",
        "full_judgment_text": "Petitioner declared eligible for judicial appointment; State directed to allocate judicial vacancy under reservation quota."
    },
    {
        "citation": "[2020] 2 NyayaLR 1427",
        "title": "Pooja Hegde v. Bangalore Municipal Water Board",
        "court_name": "High Court of Karnataka",
        "bench": "Hon'ble Justice Krishna S. Dixit",
        "year": 2020,
        "case_type": "Civil Writs / Public Utilities",
        "statutory_sections": "Constitution Article 21 (Right to Clean Water)",
        "headnote": "Access to potable drinking water and sanitary drainage is an inalienable component of the Right to Life under Article 21; public utilities cannot disconnect supply over disputed meter charges.",
        "key_passages": "The State cannot weaponize basic life-sustaining civic amenities to enforce disputed administrative fee recoveries. Disputed dues must be adjudicated through civil process while maintaining basic potable lifeline supply.",
        "full_judgment_text": "Disconnection notice quashed; municipal board directed to restore domestic water lifeline."
    },
    {
        "citation": "[2020] 1 NyayaLR 1528",
        "title": "Apex Cement Ltd v. State Goods & Services Tax Department",
        "court_name": "High Court of Judicature at Gujarat",
        "bench": "Hon'ble Justice J. B. Pardiwala & Justice Nisha M. Thakore",
        "year": 2020,
        "case_type": "Taxation / GST",
        "statutory_sections": "Central Goods and Services Tax Act 2017 Section 16, 74",
        "headnote": "Purchaser cannot be denied Input Tax Credit (ITC) merely because the selling dealer failed to deposit tax, unless collusive fraud is affirmatively established.",
        "key_passages": "Denying legitimate input tax credit to a bona fide purchasing dealer who paid tax through banking channels and holds genuine tax invoices is coercive and legally unsupportable.",
        "full_judgment_text": "Demand notice quashed; department directed to initiate recovery against defaulting vendor."
    },
    {
        "citation": "[2019] 4 NyayaLR 1629",
        "title": "Residents Welfare Association v. State Pollution Control Board",
        "court_name": "National Green Tribunal (Southern Bench)",
        "bench": "Hon'ble Justice K. Ramakrishnan",
        "year": 2019,
        "case_type": "Noise Pollution / Environmental",
        "statutory_sections": "Noise Pollution (Regulation and Control) Rules 2000 Rule 5",
        "headnote": "Operation of diesel generator sets and outdoor public sound systems exceeding 55 dB(A) in residential silence zones between 10:00 PM and 06:00 AM is strictly prohibited.",
        "key_passages": "The right to sleep peacefully and live free of noxious acoustic disturbances is part of physical and mental well-being under Article 21. No commercial or religious celebration permits nocturnal noise pollution in residential zones.",
        "full_judgment_text": "Police and pollution board directed to seize non-compliant acoustic equipment and enforce acoustic decibel monitoring."
    },
    {
        "citation": "[2019] 3 NyayaLR 1730",
        "title": "Harishankar Tiwari v. State of Nyaya (Prison Reform Mandamus)",
        "court_name": "High Court of Judicature at Allahabad",
        "bench": "Hon'ble Justice Pankaj Mithal",
        "year": 2019,
        "case_type": "Prison Reforms / Human Rights",
        "statutory_sections": "Prisons Act 1894 Section 31, Model Prison Manual 2016",
        "headnote": "Overcrowding in district prisons exceeding 150% capacity warrants mandatory grant of personal recognizance bonds to undertrials accused of non-heinous bailable offences.",
        "key_passages": "Inhuman congestion in penitentiaries impairs basic human dignity and health. Prisoners retain all fundamental rights under Part III of the Constitution except the physical freedom curtailed by law.",
        "full_judgment_text": "District Legal Services Authority directed to convene weekly scrutiny sessions and release eligible undertrials on personal bond."
    }
]


# --------------------------------------------------------------------------
# Precedent Vector Index Manager (Numpy Cosine Similarity + TF-IDF)
# --------------------------------------------------------------------------
class PrecedentSearchEngine:
    """Manages semantic and keyword vector retrieval across the fictional precedent library."""

    _instance = None

    def __init__(self):
        self.precedents = list(SYNTHETIC_PRECEDENTS)
        self.corpus = []
        for p in self.precedents:
            text = f"{p['title']} {p['case_type']} {p['statutory_sections']} {p['headnote']} {p['key_passages']} {p['full_judgment_text']}"
            self.corpus.append(text)

        self.vectorizer = TfidfVectorizer(
            stop_words='english',
            ngram_range=(1, 2),
            max_features=2500,
            sublinear_tf=True
        )
        self.tfidf_matrix = self.vectorizer.fit_transform(self.corpus)

    @classmethod
    def get_instance(cls) -> "PrecedentSearchEngine":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def search(self, query: str, top_k: int = 5, case_type_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Executes semantic cosine vector search with keyword passage extraction and relevance scores.
        """
        if not query or not query.strip():
            return []

        clean_q = query.strip()
        query_vec = self.vectorizer.transform([clean_q])
        similarities = cosine_similarity(query_vec, self.tfidf_matrix)[0]

        # Extract tokens for keyword snippet highlighting
        q_tokens = [w.lower() for w in re.findall(r'\b\w{3,}\b', clean_q) if w.lower() not in self.vectorizer.get_stop_words()]

        scored_results = []
        for idx, score in enumerate(similarities):
            item = self.precedents[idx]
            if case_type_filter and case_type_filter.lower() not in item['case_type'].lower():
                continue

            # Boost score if specific statutory section or title word matched
            bonus = 0.0
            for tok in q_tokens:
                if tok in item['statutory_sections'].lower():
                    bonus += 0.15
                if tok in item['title'].lower():
                    bonus += 0.10

            final_score = min(0.99, float(score) + bonus)
            match_percentage = int(round(final_score * 100))

            if match_percentage >= 15: # Filter noise
                # Highlight matching passage
                passage = item['key_passages']
                highlighted_passage = passage
                for tok in q_tokens:
                    pat = re.compile(re.escape(tok), re.IGNORECASE)
                    highlighted_passage = pat.sub(lambda m: f"<mark>{m.group(0)}</mark>", highlighted_passage)

                scored_results.append({
                    "id": idx + 1,
                    "citation": item['citation'],
                    "title": item['title'],
                    "court_name": item['court_name'],
                    "bench": item['bench'],
                    "year": item['year'],
                    "case_type": item['case_type'],
                    "statutory_sections": item['statutory_sections'],
                    "headnote": item['headnote'],
                    "key_passages": item['key_passages'],
                    "highlighted_passage": highlighted_passage,
                    "relevance_score": match_percentage,
                    "badge_color": "badge-success" if match_percentage >= 70 else ("badge-warning" if match_percentage >= 40 else "badge-accent"),
                    "is_fictional": True
                })

        scored_results.sort(key=lambda x: x['relevance_score'], reverse=True)
        return scored_results[:top_k]


def seed_precedents_if_needed():
    """Seeds synthetic precedents into the database table if empty."""
    try:
        if PrecedentLibrary.query.count() == 0:
            for p in SYNTHETIC_PRECEDENTS:
                record = PrecedentLibrary(
                    citation=p['citation'],
                    title=p['title'],
                    court_name=p['court_name'],
                    bench=p['bench'],
                    year=p['year'],
                    case_type=p['case_type'],
                    statutory_sections=p['statutory_sections'],
                    headnote=p['headnote'],
                    key_passages=p['key_passages'],
                    full_judgment_text=p['full_judgment_text']
                )
                db.session.add(record)
            db.session.commit()
    except Exception as e:
        db.session.rollback()


def search_precedents(query: str, limit: int = 5, case_type_filter: Optional[str] = None) -> Dict[str, Any]:
    """Top-level semantic search across synthetic judicial precedents."""
    from app.services.ai.guardrails import AI_REVIEW_BANNER
    engine = PrecedentSearchEngine.get_instance()
    results = engine.search(query, top_k=limit, case_type_filter=case_type_filter)
    return {
        "success": True,
        "query": query,
        "total_found": len(results),
        "results": results,
        "is_synthetic_data": True,
        "ai_notice": AI_REVIEW_BANNER
    }

