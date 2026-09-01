import json
import unittest

from examples.live_document_source_validation import (
    CEN_URL,
    REBUTTAL_DOI,
    REVIEW_DOI,
    FetchResponse,
    run_live_scenario,
)


def _crossref(doi, **overrides):
    message = {
        "DOI": doi,
        "title": [f"Title for {doi}"],
        "type": "journal-article",
        "published": {"date-parts": [[2022, 7, 20]]},
        "published-online": {"date-parts": [[2022, 7, 20]]},
        "relation": {},
    }
    message.update(overrides)
    return FetchResponse(200, json.dumps({"status": "ok", "message": message}).encode(), {}, "https://api.crossref.org")


def _article(body="Article body", headers=None):
    payload = {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": "Serotonin article",
        "datePublished": "2026-03-16",
        "dateModified": "2026-03-16",
        "articleBody": body,
    }
    html = f'<html><script type="application/ld+json">{json.dumps(payload)}</script><body>{body}</body></html>'
    return FetchResponse(200, html.encode(), headers or {}, CEN_URL)


def _thin_json_ld_article(body="Article body", navigation="Home Products About"):
    payload = {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": "Serotonin article",
        "datePublished": "2026-03-16",
    }
    html = (
        f'<html><script type="application/ld+json">{json.dumps(payload)}</script>'
        f"<body><nav>{navigation}</nav><article>{body}</article></body></html>"
    )
    return FetchResponse(200, html.encode(), {}, CEN_URL)


class _SequenceFetcher:
    def __init__(self, responses):
        self.responses = {key: list(value) for key, value in responses.items()}
        self.headers = []

    def __call__(self, url, headers, _timeout):
        self.headers.append(dict(headers))
        if "crossref.org" in url:
            key = REVIEW_DOI if "01661-0" in url else REBUTTAL_DOI
        else:
            key = CEN_URL
        responses = self.responses[key]
        return responses.pop(0) if len(responses) > 1 else responses[0]


class LiveDocumentSourceValidationTests(unittest.TestCase):
    def base_responses(self):
        return {
            CEN_URL: [_article(), _article()],
            REVIEW_DOI: [_crossref(REVIEW_DOI), _crossref(REVIEW_DOI)],
            REBUTTAL_DOI: [_crossref(REBUTTAL_DOI), _crossref(REBUTTAL_DOI)],
        }

    def test_same_live_metadata_keeps_all_claims_current(self):
        result = run_live_scenario(fetcher=_SequenceFetcher(self.base_responses()))
        self.assertEqual({name: value["state"] for name, value in result["claims"].items()}, {
            "claim-review-conclusion": "CURRENT",
            "claim-rebuttal-exists": "CURRENT",
            "claim-current-probe-status": "CURRENT",
        })
        self.assertIn("claim-treatment-timing", result["excluded_claims"])

    def test_registration_wall_is_unverifiable_and_flags_only_news_claims(self):
        responses = self.base_responses()
        wall = FetchResponse(403, b"sign in to continue", {}, CEN_URL)
        responses[CEN_URL] = [wall]
        result = run_live_scenario(fetcher=_SequenceFetcher(responses))
        self.assertEqual(result["sources"]["news-report"]["state"], "UNVERIFIABLE")
        self.assertEqual(result["claims"]["claim-current-probe-status"]["state"], "UNVERIFIABLE")
        self.assertEqual(result["claims"]["claim-review-conclusion"]["state"], "CURRENT")
        self.assertEqual(result["claims"]["claim-rebuttal-exists"]["state"], "CURRENT")

    def test_article_change_marks_only_supported_news_claim_stale(self):
        responses = self.base_responses()
        responses[CEN_URL] = [_article("Original"), _article("Revised")]
        result = run_live_scenario(fetcher=_SequenceFetcher(responses))
        self.assertEqual(result["claims"]["claim-current-probe-status"]["state"], "STALE_REASONING")
        self.assertEqual(result["claims"]["claim-review-conclusion"]["state"], "CURRENT")
        self.assertEqual(result["claims"]["claim-rebuttal-exists"]["state"], "CURRENT")
        self.assertIn("claim-treatment-timing", result["excluded_claims"])

    def test_thin_json_ld_falls_back_to_visible_article_body(self):
        responses = self.base_responses()
        responses[CEN_URL] = [_thin_json_ld_article("Original"), _thin_json_ld_article("Revised")]
        result = run_live_scenario(fetcher=_SequenceFetcher(responses))
        self.assertEqual(result["sources"]["news-report"]["state"], "STALE_SOURCE")
        self.assertEqual(result["claims"]["claim-current-probe-status"]["state"], "STALE_REASONING")

    def test_navigation_redesign_does_not_change_article_fingerprint(self):
        responses = self.base_responses()
        responses[CEN_URL] = [
            _thin_json_ld_article("Stable article body", "Home Products About"),
            _thin_json_ld_article("Stable article body", "New navigation Sign in Search"),
        ]
        result = run_live_scenario(fetcher=_SequenceFetcher(responses))
        self.assertEqual(result["sources"]["news-report"]["state"], "CURRENT")

    def test_crossref_wrapper_and_layout_noise_do_not_change_fingerprint(self):
        responses = self.base_responses()
        first = _crossref(REVIEW_DOI)
        second_document = json.loads(first.body)
        second_document["message"]["URL"] = "https://www.nature.com/redesigned/article"
        second_document["message"]["publisher"] = "Layout-only publisher field"
        responses[REVIEW_DOI] = [first, FetchResponse(200, json.dumps(second_document).encode(), {}, "https://api.crossref.org/v2")]
        result = run_live_scenario(fetcher=_SequenceFetcher(responses))
        self.assertEqual(result["claims"]["claim-review-conclusion"]["state"], "CURRENT")

    def test_crossref_update_notice_marks_only_its_claim_stale(self):
        responses = self.base_responses()
        responses[REVIEW_DOI] = [
            _crossref(REVIEW_DOI),
            _crossref(REVIEW_DOI, **{"update-to": [{"DOI": "10.1000/correction", "type": "correction"}]}),
        ]
        result = run_live_scenario(fetcher=_SequenceFetcher(responses))
        self.assertEqual(result["claims"]["claim-review-conclusion"]["state"], "STALE_REASONING")
        self.assertEqual(result["claims"]["claim-rebuttal-exists"]["state"], "CURRENT")
        self.assertIn("claim-treatment-timing", result["excluded_claims"])

    def test_article_credentials_remain_process_local(self):
        fetcher = _SequenceFetcher(self.base_responses())
        secret = "session=secret-cookie"
        result = run_live_scenario(fetcher=fetcher, news_headers={"Cookie": secret})
        self.assertTrue(any(headers.get("Cookie") == secret for headers in fetcher.headers))
        self.assertNotIn(secret, json.dumps(result))


if __name__ == "__main__":
    unittest.main()
