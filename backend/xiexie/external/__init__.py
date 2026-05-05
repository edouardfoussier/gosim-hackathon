"""External free-tier APIs Xiexie cross-references during scam analysis.

Each module exposes a ``lookup(...) -> dict`` that returns ``{"available":
False, ...}`` instead of raising when the API is unreachable or unkeyed —
so skills degrade gracefully (mock fixture stays the demo source of truth).
"""

from . import email_rep, safe_browsing, urlscan  # noqa: F401
