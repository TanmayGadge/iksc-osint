"""Search public results for a Facebook profile and summarize permitted public data.

Confidence scores are deterministic heuristics, not probabilities. External API
contracts are isolated in small request/response adapters.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence
from urllib.parse import quote, urlparse

SERPER_ENDPOINT = "https://google.serper.dev/search"
APIFY_API_BASE = "https://api.apify.com/v2"
DEFAULT_TIMEOUT_SECONDS = 30
MAX_SEARCH_QUERIES = 6
MIN_CONFIDENCE = 0.55
AMBIGUITY_MARGIN = 0.08
MAX_WORK_ITEMS = 10
MAX_EDUCATION_ITEMS = 10
MAX_POST_ITEMS = 10
MAX_TEXT_LENGTH = 2_000

# Explainable heuristic weights. A valid Facebook URL is an eligibility check,
# not identity evidence. Name is required; context can support but not replace it.
NAME_WEIGHT = 0.60
LOCATION_WEIGHT = 0.15
WORK_WEIGHT = 0.15
EDUCATION_WEIGHT = 0.10


class FacebookProfileFinderError(Exception):
    """Base class for safe, user-facing finder errors."""


class InputValidationError(FacebookProfileFinderError):
    """Raised when biodata is malformed or lacks a usable name."""


class ConfigurationError(FacebookProfileFinderError):
    """Raised when required runtime configuration is missing."""


class ExternalServiceError(FacebookProfileFinderError):
    """Raised when a configured external service fails or returns invalid data."""


@dataclass
class FinderSettings:
    """Runtime settings; secrets are read from the environment when omitted."""

    serper_api_key: str | None = None
    apify_api_token: str | None = None
    apify_actor_id: str | None = None
    # Actor input schemas differ. Configure the field name for the chosen actor.
    apify_profile_url_field: str | None = None
    timeout: float = DEFAULT_TIMEOUT_SECONDS
    max_queries: int = MAX_SEARCH_QUERIES
    min_confidence: float = MIN_CONFIDENCE
    ambiguity_margin: float = AMBIGUITY_MARGIN
    extra_apify_input: Mapping[str, Any] = field(default_factory=dict)

    def resolved_serper_key(self) -> str | None:
        return self.serper_api_key or os.getenv("SERPER_API_KEY")

    def resolved_apify_token(self) -> str | None:
        return self.apify_api_token or os.getenv("APIFY_API_TOKEN")


@dataclass
class Candidate:
    """A deduplicated, eligible public search result."""

    url: str
    title: str
    snippets: list[str]
    dorks: list[str]
    order: int


def _clean_text(value: Any, limit: int = MAX_TEXT_LENGTH) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", value).strip()[:limit]


def _normalize_values(value: Any) -> list[str]:
    """Normalize strings/lists of strings without stringifying nested objects."""
    values = value if isinstance(value, list) else [value]
    normalized: list[str] = []
    seen: set[str] = set()
    
    for item in values:
        if not isinstance(item, str):
            continue
        text = _clean_text(item)
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            normalized.append(text)
    return normalized


def _first_values(data: Mapping[str, Any], keys: Sequence[str]) -> list[str]:
    for key in keys:
        values = _normalize_values(data.get(key))
        if values:
            return values
    return []


def _normalize_biodata(biodata_json: Any) -> dict[str, Any]:
    if not isinstance(biodata_json, Mapping):
        raise InputValidationError("biodata_json must be a mapping")

    names = _normalize_values(biodata_json.get("name"))
    
    if not names:
        first_name = _clean_text(biodata_json.get("first_name"))
        last_name = _clean_text(biodata_json.get("last_name"))
        full_name = f"{first_name} {last_name}".strip()
        if full_name:
            names = [full_name]
    
    if not names:
        raise InputValidationError("A non-empty name is required")

    original_name = next(
        (value.strip() for value in [biodata_json.get("name")] if isinstance(value, str)),
        names[0],
    )
    return {
        "target_name": original_name,
        "name": names[0],
        "locations": _first_values(biodata_json, ("city", "location")),
        "work": _first_values(biodata_json, ("company", "occupation")),
        "education": _first_values(biodata_json, ("education",)),
    }


def _safe_query_phrase(value: str) -> str:
    # Remove operators and quote characters so biodata cannot alter query syntax.
    safe = re.sub(r"[\"'\\<>]", " ", value)
    safe = re.sub(r"[\[\]{}()|]", " ", safe)
    safe = re.sub(r"\s+", " ", safe).strip()
    return f'"{safe}"' if " " in safe else safe


def generate_search_dorks(biodata_json: Mapping[str, Any]) -> list[str]:
    """Build a deterministic, bounded list of Facebook-restricted queries."""
    data = _normalize_biodata(biodata_json)
    name = _safe_query_phrase(data["name"])
    if not name:
        raise InputValidationError("A usable name is required")

    dorks = [f"site:facebook.com {name}"]
    for values in (data["locations"], data["work"], data["education"]):
        dorks.extend(f"site:facebook.com {name} {_safe_query_phrase(value)}" for value in values)

    # Add a limited combined query only when distinct supplied context exists.
    if data["locations"] and data["work"]:
        dorks.append(
            f"site:facebook.com {name} "
            f"{_safe_query_phrase(data['locations'][0])} "
            f"{_safe_query_phrase(data['work'][0])}"
        )

    unique: list[str] = []
    seen: set[str] = set()
    for dork in dorks:
        key = dork.casefold()
        if key not in seen:
            seen.add(key)
            unique.append(dork)
    return unique[:MAX_SEARCH_QUERIES]

    
def _normalize_profile_url(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    url = value.strip()
    if not url:
        return ""
    if url.startswith("//"):
        url = "https:" + url
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if host not in {"facebook.com", "m.facebook.com", "www.facebook.com"}:
        return ""
    path = parsed.path.strip("/")
    if not path or path.lower().startswith(("search", "groups", "events", "pages")):
        return ""
    # Keep only the URL; remove tracking and fragments.
    return f"https://www.facebook.com/{path}"


def _normalize_for_match(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", without_marks).strip()


def _tokens(value: str) -> set[str]:
    return set(_normalize_for_match(value).split())


def _name_matches(target_name: str, evidence: str) -> bool:
    target_tokens = _tokens(target_name)
    evidence_tokens = _tokens(evidence)
    if not target_tokens or not evidence_tokens:
        return False
    # Require all name tokens, avoiding short substring and partial-name matches.
    return target_tokens.issubset(evidence_tokens)


def _has_token_match(values: Sequence[str], evidence: str) -> bool:
    evidence_tokens = _tokens(evidence)
    return any(_tokens(value).issubset(evidence_tokens) for value in values if _tokens(value))


def _extract_results(serper_response: Any, dork: str, order_start: int) -> list[Candidate]:
    if not isinstance(serper_response, Mapping):
        return []
    organic = serper_response.get("organic")
    if not isinstance(organic, list):
        return []

    candidates: list[Candidate] = []
    for offset, item in enumerate(organic):
        if not isinstance(item, Mapping):
            continue
        url = _normalize_profile_url(item.get("link"))
        if not url:
            continue
        candidates.append( 
            Candidate(
                url=url,
                title=_clean_text(item.get("title")),
                snippets=[text for text in [_clean_text(item.get("snippet"))] if text],
                dorks=[dork],
                order=order_start + offset,
            )
        )
    return candidates


def _merge_candidates(candidates: Sequence[Candidate]) -> list[Candidate]:
    merged: dict[str, Candidate] = {}
    for candidate in candidates:
        existing = merged.get(candidate.url.casefold())
        if existing is None:
            merged[candidate.url.casefold()] = candidate
            continue
        existing.snippets = list(dict.fromkeys(existing.snippets + candidate.snippets))
        existing.dorks = list(dict.fromkeys(existing.dorks + candidate.dorks))
        existing.order = min(existing.order, candidate.order)
        if not existing.title and candidate.title:
            existing.title = candidate.title
    return list(merged.values())


def match_candidate_results(
    biodata_json: Mapping[str, Any], serper_response: Any
) -> dict[str, Any] | None:
    """Return the best credible candidate, or None for no-match/ambiguity."""
    data = _normalize_biodata(biodata_json)
    responses = serper_response if isinstance(serper_response, list) else [serper_response]
    candidates: list[Candidate] = []
    for index, response in enumerate(responses):
        dork = ""
        payload = response
        if isinstance(response, tuple) and len(response) == 2:
            dork, payload = response
        candidates.extend(_extract_results(payload, str(dork), index * 1000))
    candidates = _merge_candidates(candidates)

    ranked: list[dict[str, Any]] = []
    for candidate in candidates:
        evidence = " ".join([candidate.title, *candidate.snippets, candidate.url])
        if not _name_matches(data["name"], evidence):
            continue

        score = NAME_WEIGHT
        reasons = ["name matched"]
        if data["locations"] and _has_token_match(data["locations"], evidence):
            score += LOCATION_WEIGHT
            reasons.append("location matched")
        if data["work"] and _has_token_match(data["work"], evidence):
            score += WORK_WEIGHT
            reasons.append("work or occupation matched")
        if data["education"] and _has_token_match(data["education"], evidence):
            score += EDUCATION_WEIGHT
            reasons.append("education matched")

        ranked.append(
            {
                "url": candidate.url,
                "confidence_score": min(1.0, float(score)),
                "raw_match_reasons": reasons,
                "order": candidate.order,
            }
        )

    ranked.sort(key=lambda item: (-item["confidence_score"], item["order"], item["url"]))
    if not ranked or ranked[0]["confidence_score"] < MIN_CONFIDENCE:
        return None
    if len(ranked) > 1 and (
        ranked[0]["confidence_score"] - ranked[1]["confidence_score"] < AMBIGUITY_MARGIN
    ):
        return None
    return ranked[0]


def _request_json(
    http_client: Any,
    method: str,
    url: str,
    *,
    timeout: float,
    **kwargs: Any,
) -> Any:
    try:
        response = getattr(http_client, method)(url, timeout=timeout, **kwargs)
        response.raise_for_status()
        return response.json()
    except FacebookProfileFinderError:
        raise
    except Exception as exc:
        # Do not include exception text; HTTP clients can include credential-bearing URLs.
        raise ExternalServiceError(f"External service {method.upper()} request failed") from exc


def run_serper_search(
    dorks: Sequence[str],
    api_key: str,
    http_client: Any,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> list[tuple[str, Any]]:
    """Execute bounded per-dork Serper requests, retaining dork provenance."""
    if not api_key:
        raise ConfigurationError("SERPER_API_KEY is required")
    results: list[tuple[str, Any]] = []
    for dork in dorks[:MAX_SEARCH_QUERIES]:
        payload = _request_json(
            http_client,
            "post",
            SERPER_ENDPOINT,
            timeout=timeout,
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"q": dork},
        )
        if not isinstance(payload, Mapping):
            raise ExternalServiceError("Serper returned an invalid response")
        results.append((dork, payload))
    return results


def scrape_profile_with_apify(
    profile_url: str,
    api_token: str,
    actor_id: str,
    http_client: Any,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    profile_url_field: str | None = None,
    extra_input: Mapping[str, Any] | None = None,
) -> Any:
    """Run an actor synchronously and retrieve its dataset items.

    Configure the URL input field to match the selected actor's documented schema.
    """
    normalized_url = _normalize_profile_url(profile_url)
    if not normalized_url:
        raise InputValidationError("A valid public Facebook profile URL is required")
    if not api_token or not actor_id or not profile_url_field:
        raise ConfigurationError(
            "APIFY_API_TOKEN, APIFY_ACTOR_ID, and the actor URL input field are required"
        )

    actor_path = quote(actor_id, safe="~")
    endpoint = (
        f"{APIFY_API_BASE}/acts/{actor_path}/run-sync-get-dataset-items"
        f"?token={quote(api_token, safe='')}&clean=true&format=json"
    )
    actor_input = dict(extra_input or {})
    actor_input[profile_url_field] = [normalized_url]

    payload = _request_json(
        http_client,
        "post",
        endpoint,
        timeout=timeout,
        json=actor_input,
    )
    if not isinstance(payload, (Mapping, list)):
        raise ExternalServiceError("Apify returned an invalid dataset response")
    return payload


def _record_list(raw_payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(raw_payload, Mapping):
        records = raw_payload.get("items")
        if isinstance(records, list):
            return [item for item in records if isinstance(item, Mapping)]
        return [raw_payload]
    if isinstance(raw_payload, list):
        return [item for item in raw_payload if isinstance(item, Mapping)]
    return []


def _record_values(record: Mapping[str, Any], keys: Sequence[str]) -> list[str]:
    values: list[str] = []
    for key in keys:
        values.extend(_normalize_values(record.get(key)))
    return list(dict.fromkeys(values))


def _first_record_value(record: Mapping[str, Any], keys: Sequence[str]) -> str:
    values = _record_values(record, keys)
    return values[0][:MAX_TEXT_LENGTH] if values else ""


def _bounded_values(values: Sequence[str], limit: int) -> list[str]:
    return list(dict.fromkeys(value[:MAX_TEXT_LENGTH] for value in values if value))[:limit]


def transform_apify_payload(
    biodata_json: Mapping[str, Any],
    profile_url: str,
    raw_payload: Any,
    confidence: float,
    match_reasons: Sequence[str],
) -> dict[str, Any]:
    """Map only returned actor fields into the agreed JSON-safe output schema."""
    data = _normalize_biodata(biodata_json)
    safe_url = _normalize_profile_url(profile_url)
    if not safe_url:
        raise InputValidationError("A valid matched profile URL is required")

    records = _record_list(raw_payload)
    record = records[0] if records else {}
    summary = {
        "current_city": _first_record_value(
            record, ("currentCity", "current_city", "city", "location")
        ),
        "work_history": _bounded_values(
            _record_values(record, ("workHistory", "work_history", "work", "employment")),
            MAX_WORK_ITEMS,
        ),
        "education": _bounded_values(
            _record_values(record, ("education", "educationHistory", "education_history")),
            MAX_EDUCATION_ITEMS,
        ),
        "profile_picture_url": _first_record_value(
            record, ("profilePictureUrl", "profile_picture_url", "profilePic", "image")
        ),
        "bio_or_about": _first_record_value(
            record, ("about", "bio", "description", "intro")
        ),
        "public_posts_summary": _bounded_values(
            _record_values(record, ("publicPostsSummary", "public_posts_summary", "posts")),
            MAX_POST_ITEMS,
        ),
    }
    result = {
        "target_name": data["target_name"],
        "matched_profile_url": safe_url,
        "confidence_score": max(0.0, min(1.0, float(confidence))),
        "summary": summary,
        "raw_match_reasons": _bounded_values(list(match_reasons), 20),
    }
    # Validate JSON compatibility before returning.
    json.dumps(result, ensure_ascii=False)
    return result


def _no_match_result(biodata_json: Mapping[str, Any]) -> dict[str, Any]:
    data = _normalize_biodata(biodata_json)
    return {
        "target_name": data["target_name"],
        "matched_profile_url": "",
        "confidence_score": 0.0,
        "summary": {
            "current_city": "",
            "work_history": [],
            "education": [],
            "profile_picture_url": "",
            "bio_or_about": "",
            "public_posts_summary": [],
        },
        "raw_match_reasons": ["No sufficiently credible, unambiguous candidate found"],
    }


def facebook_profile_finder(
    biodata_json: Mapping[str, Any],
    settings: FinderSettings | Mapping[str, Any] | None,
    http_client: Any,
) -> dict[str, Any]:
    """Run validation, search, candidate matching, scraping, and transformation."""
    data = _normalize_biodata(biodata_json)
    if settings is None:
        config = FinderSettings()
    elif isinstance(settings, FinderSettings):
        config = settings
    elif isinstance(settings, Mapping):
        allowed = FinderSettings.__dataclass_fields__
        config = FinderSettings(**{key: value for key, value in settings.items() if key in allowed})
    else:
        raise ConfigurationError("settings must be a mapping or FinderSettings")

    api_key = config.resolved_serper_key()
    if not api_key:
        raise ConfigurationError("SERPER_API_KEY is required for a live search")

    dorks = generate_search_dorks(biodata_json)[: max(1, config.max_queries)]
    search_results = run_serper_search(dorks, api_key, http_client, config.timeout)
    candidate = match_candidate_results(biodata_json, search_results)
    if candidate is None or candidate["confidence_score"] < config.min_confidence:
        return _no_match_result(biodata_json)

    apify_token = config.resolved_apify_token()
    if not apify_token:
        raise ConfigurationError("APIFY_API_TOKEN is required to scrape a matched profile")

    raw_payload = scrape_profile_with_apify(
        candidate["url"],
        apify_token,
        config.apify_actor_id or os.getenv("APIFY_ACTOR_ID", ""),
        http_client,
        timeout=config.timeout,
        profile_url_field=(
            config.apify_profile_url_field or os.getenv("APIFY_PROFILE_URL_FIELD")
        ),
        extra_input=config.extra_apify_input,
    )
    return transform_apify_payload(
        biodata_json,
        candidate["url"],
        raw_payload,
        candidate["confidence_score"],
        candidate["raw_match_reasons"],
    )