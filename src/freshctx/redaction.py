from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

REDACTED = "[REDACTED]"
SENSITIVE_KEYS = {"authorization", "cookie", "set-cookie", "password", "passwd", "pwd", "secret", "token", "access_token", "refresh_token", "api_key", "apikey", "client_secret", "private_key", "dsn"}
SENSITIVE_QUERY_KEYS = {"token", "key", "api_key", "apikey", "password", "secret", "signature", "sig"}
BEARER = re.compile(r"(?i)\b(bearer|basic)\s+[a-z0-9._~+/=-]+")

def redact(value: Any, extra_keys: set[str] | None = None) -> Any:
    keys = SENSITIVE_KEYS | {k.lower() for k in (extra_keys or set())}
    if isinstance(value, Mapping):
        return {str(k): (REDACTED if str(k).lower() in keys else redact(v, keys)) for k, v in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact(item, keys) for item in value]
    if isinstance(value, str): return _redact_string(value)
    return value

def _redact_string(value: str) -> str:
    cleaned = BEARER.sub(lambda m: f"{m.group(1)} {REDACTED}", value)
    try:
        parts = urlsplit(cleaned)
        if parts.scheme and parts.netloc:
            host = parts.hostname or ""
            if parts.port: host = f"{host}:{parts.port}"
            if parts.username or parts.password: host = f"{REDACTED}@{host}"
            query = urlencode([(k, REDACTED if k.lower() in SENSITIVE_QUERY_KEYS else v) for k, v in parse_qsl(parts.query, keep_blank_values=True)])
            return urlunsplit((parts.scheme, host, parts.path, query, parts.fragment))
    except ValueError: pass
    return cleaned
