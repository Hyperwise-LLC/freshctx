"""Live claim-to-source validation without interpreting research claims.

This bounded integration uses a C&EN article and two DOI records from the
three-source brief proposed by Callum Pierce. It deliberately keeps source
access and metadata normalization above FreshCtx Core:

* a registration wall, HTTP 401/403, timeout, or unavailable source becomes
  UNVERIFIABLE rather than a false content-change signal;
* DOI sources are fingerprinted from selected Crossref metadata, not rendered
  publisher HTML; and
* FreshCtx reports which source moved and which claims declared it. It does not
  decide whether a revised source still supports a claim.

The live runner performs two reads in one process. Optional C&EN credentials
remain process-local and are never written to FreshCtx tokens or audit events.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable
from urllib.parse import quote, urlsplit, urlunsplit

from freshctx import MemoryStore, ObservationToken, guard, observe, reasoning, register_adapter
from freshctx.model import AdapterResult


CEN_URL = "https://cen.acs.org/pharmaceuticals/neuroscience/ssris-mental-health-debate/104/web/2026/03"
REVIEW_DOI = "10.1038/s41380-022-01661-0"
REBUTTAL_DOI = "10.1038/s41380-023-02095-y"

CLAIM_SOURCES = {
    "claim-treatment-timing": ("news-report",),
    "claim-review-conclusion": ("review",),
    "claim-rebuttal-exists": ("rebuttal",),
    "claim-current-probe-status": ("news-report",),
}

WALL_MARKERS = (
    "sign in to continue",
    "register to continue",
    "subscribe to continue",
    "create a free account to continue",
    "subscription required",
    "access denied",
)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _safe_url(url: str) -> str:
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme, host, parsed.path, parsed.query, ""))


@dataclass(frozen=True)
class FetchResponse:
    status: int
    body: bytes
    headers: dict[str, str]
    final_url: str


class SourceUnavailable(Exception):
    def __init__(self, error_code: str, evidence: dict[str, Any] | None = None):
        super().__init__(error_code)
        self.error_code = error_code
        self.evidence = evidence or {}


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._ignored = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._ignored += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._ignored:
            self._ignored -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored:
            value = " ".join(data.split())
            if value:
                self.parts.append(value)


def _json_ld_articles(html: str) -> list[dict[str, Any]]:
    blocks = re.findall(
        r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    articles: list[dict[str, Any]] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            kind = value.get("@type")
            kinds = set(kind if isinstance(kind, list) else [kind])
            if kinds.intersection({"Article", "NewsArticle", "Report"}):
                articles.append(value)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    for block in blocks:
        try:
            visit(json.loads(block.strip()))
        except (json.JSONDecodeError, TypeError):
            continue
    return articles


def _article_fingerprint(response: FetchResponse) -> tuple[str, str, dict[str, Any]]:
    evidence = {"status": response.status, "url": _safe_url(response.final_url)}
    if response.status in {401, 403}:
        raise SourceUnavailable(f"http_{response.status}", evidence)
    if response.status < 200 or response.status >= 300:
        raise SourceUnavailable(f"http_{response.status}", evidence)

    html = response.body.decode("utf-8", errors="replace")
    lower = " ".join(html.lower().split())
    if any(marker in lower for marker in WALL_MARKERS):
        raise SourceUnavailable("registration_wall", evidence)
    final_path = urlsplit(response.final_url).path.lower()
    if any(part in final_path for part in ("/login", "/signin", "/register")):
        raise SourceUnavailable("registration_wall_redirect", evidence)

    articles = _json_ld_articles(html)
    if articles:
        article = articles[0]
        payload = {
            "headline": article.get("headline"),
            "datePublished": article.get("datePublished"),
            "dateModified": article.get("dateModified"),
            "articleBody": article.get("articleBody"),
        }
        if any(value not in (None, "") for value in payload.values()):
            return _sha(payload), "article_json_ld", evidence

    etag = response.headers.get("ETag") or response.headers.get("etag")
    if etag and not str(etag).startswith("W/"):
        return _sha({"etag": str(etag)}), "strong_etag", evidence

    parser = _VisibleTextParser()
    parser.feed(html)
    visible_text = " ".join(parser.parts)
    if not visible_text:
        raise SourceUnavailable("article_content_unavailable", evidence)
    return _sha({"visible_text": visible_text}), "normalized_visible_text", evidence


def _crossref_fingerprint(response: FetchResponse, doi: str) -> tuple[str, str, dict[str, Any]]:
    evidence = {"status": response.status, "doi": doi.lower()}
    if response.status < 200 or response.status >= 300:
        raise SourceUnavailable(f"crossref_http_{response.status}", evidence)
    try:
        document = json.loads(response.body.decode("utf-8"))
        message = document["message"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise SourceUnavailable("crossref_malformed", evidence) from exc
    if not isinstance(message, dict) or str(message.get("DOI", "")).lower() != doi.lower():
        raise SourceUnavailable("crossref_doi_mismatch", evidence)

    payload = {
        "DOI": str(message.get("DOI", "")).lower(),
        "title": message.get("title"),
        "type": message.get("type"),
        "published": message.get("published"),
        "published-online": message.get("published-online"),
        "published-print": message.get("published-print"),
        "update-to": message.get("update-to"),
        "updated-by": message.get("updated-by"),
        "relation": message.get("relation"),
    }
    return _sha(payload), "crossref_selected_metadata", evidence


def default_fetcher(url: str, headers: dict[str, str], timeout: float) -> FetchResponse:
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return FetchResponse(
                status=int(response.status),
                body=response.read(),
                headers=dict(response.headers.items()),
                final_url=response.geturl(),
            )
    except urllib.error.HTTPError as exc:
        return FetchResponse(
            status=int(exc.code),
            body=exc.read(),
            headers=dict(exc.headers.items()),
            final_url=exc.geturl(),
        )


class ResearchSourceAdapter:
    """Example-only adapter for authenticated articles and Crossref records."""

    name = "research_source_live"
    thread_safe = True

    def __init__(self, fetcher: Callable[[str, dict[str, str], float], FetchResponse] = default_fetcher):
        self.fetcher = fetcher
        self._runtime_headers: dict[str, dict[str, str]] = {}

    @staticmethod
    def _crossref_url(doi: str) -> str:
        return f"https://api.crossref.org/works/{quote(doi, safe='')}"

    def _snapshot(
        self,
        locator: str,
        source_kind: str,
        headers: dict[str, str],
        timeout: float,
    ) -> tuple[str, str, dict[str, Any]]:
        url = self._crossref_url(locator) if source_kind == "crossref" else locator
        try:
            response = self.fetcher(url, headers, timeout)
        except (TimeoutError, urllib.error.URLError, OSError, ValueError) as exc:
            code = "source_timeout" if isinstance(exc, TimeoutError) else type(exc).__name__
            raise SourceUnavailable(code, {"source": _safe_url(url)}) from exc
        if source_kind == "crossref":
            return _crossref_fingerprint(response, locator)
        if source_kind == "article":
            return _article_fingerprint(response)
        raise ValueError("source_kind must be 'article' or 'crossref'")

    def observe(
        self,
        locator: str,
        *,
        source_kind: str,
        headers: dict[str, str] | None = None,
        timeout: float = 8.0,
    ) -> ObservationToken:
        runtime_headers = dict(headers or {})
        timeout = float(timeout)
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        safe_locator = str(locator).lower() if source_kind == "crossref" else _safe_url(str(locator))
        metadata: dict[str, Any] = {"source_kind": source_kind, "timeout": timeout}
        try:
            fingerprint, strategy, evidence = self._snapshot(str(locator), source_kind, runtime_headers, timeout)
            metadata.update({"baseline_access": "available", "fingerprint_strategy": strategy, **evidence})
        except SourceUnavailable as exc:
            fingerprint = _sha({"unverifiable": exc.error_code, "locator": safe_locator})
            metadata.update(
                {
                    "baseline_access": "unverifiable",
                    "fingerprint_strategy": "unverifiable",
                    "baseline_error": exc.error_code,
                    **exc.evidence,
                }
            )
        token = ObservationToken(self.name, safe_locator, fingerprint, metadata=metadata)
        self._runtime_headers[token.id] = runtime_headers
        return token

    def validate(self, token: ObservationToken) -> AdapterResult:
        if token.metadata.get("baseline_access") != "available":
            return AdapterResult(
                "indeterminate",
                evidence={"source": token.locator, "baseline_error": token.metadata.get("baseline_error")},
                error_code="baseline_unverifiable_reobserve_required",
            )
        headers = dict(self._runtime_headers.get(token.id, {}))
        try:
            fingerprint, strategy, evidence = self._snapshot(
                token.locator,
                str(token.metadata.get("source_kind")),
                headers,
                float(token.metadata.get("timeout", 8.0)),
            )
        except SourceUnavailable as exc:
            return AdapterResult("indeterminate", evidence={"source": token.locator, **exc.evidence}, error_code=exc.error_code)
        return AdapterResult(
            "equivalent" if fingerprint == token.fingerprint else "changed",
            evidence={"source": token.locator, "fingerprint_strategy": strategy, **evidence},
        )


def _run(
    fetcher: Callable[[str, dict[str, str], float], FetchResponse],
    news_headers: dict[str, str] | None,
    timeout: float,
    audit_path: Path,
) -> dict[str, Any]:
    adapter = ResearchSourceAdapter(fetcher)
    register_adapter(adapter.name, adapter)
    store = MemoryStore()

    with guard(store=store, audit_path=audit_path):
        sources = {
            "news-report": observe(
                CEN_URL,
                adapter=adapter.name,
                source_kind="article",
                headers=news_headers,
                timeout=timeout,
            ),
            "review": observe(REVIEW_DOI, adapter=adapter.name, source_kind="crossref", timeout=timeout),
            "rebuttal": observe(REBUTTAL_DOI, adapter=adapter.name, source_kind="crossref", timeout=timeout),
        }
        claims = {}
        for claim_name, dependencies in CLAIM_SOURCES.items():
            with reasoning(claim_name, [sources[source] for source in dependencies]) as claim:
                claims[claim_name] = claim

    with guard(policy="allow", store=store, audit_path=audit_path) as ctx:
        source_results = {name: ctx.check(token).to_dict() for name, token in sources.items()}
        claim_results = {name: ctx.check(claim).to_dict() for name, claim in claims.items()}

    return {
        "scenario": "callum-three-source-live-boundary",
        "scope": "source movement and claim dependency mapping only",
        "sources": source_results,
        "claims": claim_results,
        "limitations": [
            "FreshCtx does not determine whether a source or claim is true.",
            "FreshCtx does not interpret whether revised material still supports a claim.",
            "C&EN credentials, when supplied, remain process-local.",
            "A walled or inaccessible source is UNVERIFIABLE, not silently current.",
            "DOI fingerprints use selected Crossref metadata rather than publisher HTML.",
        ],
    }


def run_live_scenario(
    *,
    fetcher: Callable[[str, dict[str, str], float], FetchResponse] = default_fetcher,
    news_headers: dict[str, str] | None = None,
    timeout: float = 8.0,
    audit_path: Path | None = None,
) -> dict[str, Any]:
    if audit_path is not None:
        return _run(fetcher, news_headers, timeout, audit_path)
    with TemporaryDirectory() as directory:
        return _run(fetcher, news_headers, timeout, Path(directory) / "live-document-source-audit.jsonl")


def _headers_from_environment(cookie_env: str | None, authorization_env: str | None) -> dict[str, str]:
    headers = {"Accept": "text/html,application/xhtml+xml", "User-Agent": "freshctx-live-research/1"}
    if cookie_env and os.environ.get(cookie_env):
        headers["Cookie"] = os.environ[cookie_env]
    if authorization_env and os.environ.get(authorization_env):
        headers["Authorization"] = os.environ[authorization_env]
    return headers


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cen-cookie-env", help="environment variable containing an optional C&EN Cookie header")
    parser.add_argument("--cen-authorization-env", help="environment variable containing an optional Authorization header")
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result = run_live_scenario(
        news_headers=_headers_from_environment(args.cen_cookie_env, args.cen_authorization_env),
        timeout=args.timeout,
    )
    rendered = json.dumps(result, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
