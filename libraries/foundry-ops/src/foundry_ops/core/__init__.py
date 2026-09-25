"""Foundation: errors, evidence ledger, run manifests, bounded polling, log excerpts, identifier guards. Stdlib only."""

from .bounds import PollResult, collect_bounded, poll_until
from .errors import (BoundExceededError, FoundryOpsError, OutcomeUnknownError, ReadbackError, RefusedError,
                     UnresolvedIntentError, VerificationError)
from .identifiers import IDENTIFIER, safe_identifier, validate_version_label
from .logs import DEFAULT_KEYWORDS, exception_lines, log_messages, redact
from .manifest import PinSource, RunManifest, load_run_manifest, series_directory
from .records import (RECORD_NAME, SENSITIVE_KEYS, EvidenceLedger, encode_json, error_summary, pin, read_pinned,
                      read_receipt, redact_text, sanitize, sha256_file, sha256_hex, to_plain, utc_stamp)

__all__ = [
    "PollResult", "collect_bounded", "poll_until",
    "BoundExceededError", "FoundryOpsError", "OutcomeUnknownError", "ReadbackError", "RefusedError",
    "UnresolvedIntentError", "VerificationError",
    "IDENTIFIER", "safe_identifier", "validate_version_label",
    "DEFAULT_KEYWORDS", "exception_lines", "log_messages", "redact",
    "PinSource", "RunManifest", "load_run_manifest", "series_directory",
    "RECORD_NAME", "SENSITIVE_KEYS", "EvidenceLedger", "encode_json", "error_summary", "pin", "read_pinned",
    "read_receipt", "redact_text", "sanitize", "sha256_file", "sha256_hex", "to_plain", "utc_stamp",
]
