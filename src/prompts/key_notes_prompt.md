# Key Notes Extraction Prompt

Extract key notes from the provided context. Return JSON array only.

Requirements:
- Each item must follow the KeyNote schema with `note_type`, `summary`, and `source_refs`.
- `note_type` must be one of: accounting_policy, audit_opinion, related_party, impairment, contingency, segment, guidance, other.
- `source_refs` must include page number and quote (<=200 chars) when possible.
- Do not invent facts; if unclear, summarize cautiously and lower confidence in the evidence.

Return JSON only.
