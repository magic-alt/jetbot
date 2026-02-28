from __future__ import annotations

import uuid


def new_doc_id() -> str:
    return uuid.uuid4().hex
