"""
NyayaDesk AI Structured Output Schemas (Pydantic v2)
Enforces strict schema validation for all judicial AI generations.
"""

from typing import List, Optional
from pydantic import BaseModel, Field

class CaseSummarySchema(BaseModel):
    """Structured legal case brief."""
    factual_background: str = Field(description="Objective chronological summary of the facts and cause of action.")
    parties: List[str] = Field(default_factory=list, description="Names of petitioners, respondents, and counsel on record.")
    procedural_timeline: List[str] = Field(default_factory=list, description="Chronological listing of filings and past hearing events.")
    legal_issues: List[str] = Field(default_factory=list, description="Key legal questions and statutory provisions under consideration.")
    recommended_next_steps: List[str] = Field(default_factory=list, description="Concrete judicial administration and procedural next steps.")


class OrderDraftSchema(BaseModel):
    """Structured judicial order draft with operative directives."""
    title: str = Field(description="Formal title of the order, e.g. 'Interim Order on Bail Petition'.")
    court_name: str = Field(description="Official name of the court.")
    judge_name: str = Field(description="Name and title of presiding judicial bench.")
    case_number: str = Field(description="Official case tracking number.")
    order_type: str = Field(description="Interim, Direction, Notice, Bail, or Final Judgment.")
    proceedings_summary: str = Field(description="Record of counsel appearance and arguments heard.")
    operative_directions: List[str] = Field(default_factory=list, description="Numbered judicial directives and requirements.")
    next_hearing_date: Optional[str] = Field(default=None, description="Next date of listing or compliance in DD-MM-YYYY format.")


class DocumentExtractionSchema(BaseModel):
    """Extracted legal metadata and classification from scanned / uploaded pleadings."""
    suggested_doc_type: str = Field(description="Classification: Petition, Affidavit, Bail Application, Order, etc.")
    confidence: int = Field(ge=0, le=100, description="Confidence score between 0 and 100.")
    identified_acts: List[str] = Field(default_factory=list, description="Statutory sections and legal Acts mentioned.")
    extracted_case_numbers: List[str] = Field(default_factory=list, description="Case / FIR numbers found in text.")
    extracted_amounts: List[str] = Field(default_factory=list, description="Monetary figures, claim amounts, or stamp duty values.")
    extracted_dates: List[str] = Field(default_factory=list, description="Pertinent dates referenced in the document.")


class SchedulingSlotItem(BaseModel):
    """Individual conflict-free hearing slot suggestion."""
    slot_datetime: str = Field(description="ISO 8601 formatted datetime YYYY-MM-DDTHH:MM.")
    display: str = Field(description="Human readable date and time display string.")
    display_date: str = Field(description="Date representation e.g. 25-11-2026 (Wednesday).")
    display_time: str = Field(description="Time representation e.g. 10:30 AM.")
    slot_label: str = Field(description="Session phase label e.g. Morning Call.")
    score: int = Field(description="Calculated balance score 0-100.")
    reason: str = Field(description="Administrative justification for this slot.")


class SchedulingSuggestionSchema(BaseModel):
    """List of optimal conflict-free hearing slot recommendations."""
    slots: List[SchedulingSlotItem] = Field(default_factory=list, description="Ranked conflict-free hearing slots.")


class LegalChatSchema(BaseModel):
    """Citizen legal assistant structured guidance."""
    reply: str = Field(description="Accurate procedural explanation in requested language.")
    procedural_steps: List[str] = Field(default_factory=list, description="Sequential steps citizen must take.")
    statutory_references: List[str] = Field(default_factory=list, description="Relevant statutory sections cited.")
    disclaimer: str = Field(description="Standard mandatory non-legal-advice disclaimer.")
