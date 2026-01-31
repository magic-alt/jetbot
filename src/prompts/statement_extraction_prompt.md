# Statement Extraction Prompt

You are extracting a single financial statement from a PDF report. Return JSON only.

Requirements:
- Output must follow the JSON schema provided by the caller.
- Populate `statement_type` as one of: income, balance, cashflow.
- Each line item must include `name_raw`, `name_norm`, `value_current`, `value_prior`, `unit`, `currency`, and `source_refs`.
- `source_refs` must include page number, ref_type, and optional table_id/quote.
- Do not invent numbers. If a value is missing, use null and add an issue.
- Ensure `extraction_confidence` is between 0 and 1.
- If unsure, reduce confidence and add issues.

Return JSON only.
