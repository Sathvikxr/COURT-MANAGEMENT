"""
Version 1.0 Prompt Template for Smart Scheduling Slot Selection.
"""

from app.services.ai.prompts.base_instructions import BASE_JUDICIAL_SYSTEM_INSTRUCTION

VERSION = "1.0"

SYSTEM_INSTRUCTION = BASE_JUDICIAL_SYSTEM_INSTRUCTION + """
TASK: Evaluate candidate hearing slots for a court case and provide administrative recommendations balancing judge workload, courtroom availability, and urgency.
"""

USER_TEMPLATE = """Case Number: {case_number}
Case Priority: {priority} ({case_type})
Judge: {judge_name}
Courtroom: {courtroom_name}

<CANDIDATE_SLOTS_DATA>
{candidate_slots_summary}
</CANDIDATE_SLOTS_DATA>

Rank and return the optimal slots in structured JSON matching SchedulingSuggestionSchema.
"""
