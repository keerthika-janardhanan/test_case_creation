import os
import requests
from typing import List, Dict
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

load_dotenv()  # Loads .env from current working directory (repo root expected)

JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
JIRA_BASE_URL = os.getenv("JIRA_BASE_URL")
JIRA_DEBUG = os.getenv("JIRA_DEBUG", "0").lower() in {"1", "true", "yes"}

def _validate_env() -> None:
    missing = [name for name, val in [
        ("JIRA_EMAIL", JIRA_EMAIL),
        ("JIRA_API_TOKEN", JIRA_API_TOKEN),
        ("JIRA_BASE_URL", JIRA_BASE_URL),
    ] if not val]
    if missing:
        raise RuntimeError(
            "Missing Jira environment variables: " + ", ".join(missing) + 
            ". Set them in a .env file or process environment. Expected keys: JIRA_EMAIL, JIRA_API_TOKEN, JIRA_BASE_URL"
        )

def _debug(msg: str) -> None:
    if JIRA_DEBUG:
        print(f"[JIRA] {msg}")

class JiraEndpointUnavailable(RuntimeError):
    """Raised when a Jira REST path is disabled or removed."""


def fetch_jira_issues(jql_query: str, max_results: int = 50) -> List[Dict]:
    """Fetch issues from Jira using a JQL query with basic pagination.

    Raises:
        RuntimeError: When required env vars are missing or HTTP errors occur.
    Returns:
        List[Dict]: Raw issue objects returned by Jira.
    """
    _validate_env()

    auth = HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)  # type: ignore[arg-type]
    headers = {"Accept": "application/json"}

    def _fetch_with_endpoint(api_suffix: str) -> List[Dict]:
        """Fetch issues while targeting a specific REST path."""
        start_at = 0
        next_page_token: str | None = None
        all_issues: List[Dict] = []
        total: int | None = None
        while True:
            url = f"{JIRA_BASE_URL.rstrip('/')}{api_suffix}"
            params = {
                "jql": jql_query,
                "startAt": start_at,
                "maxResults": max_results,
                "fields": "summary,description,issuetype,project,status,parent,priority,assignee",
            }
            if next_page_token:
                params["nextPageToken"] = next_page_token
                params.pop("startAt", None)
            try:
                response = requests.get(url, headers=headers, auth=auth, params=params, timeout=30)
            except requests.RequestException as exc:  # noqa: BLE001
                raise RuntimeError(f"Jira request network error: {exc}") from exc

            if response.status_code in {404, 410}:
                raise JiraEndpointUnavailable(
                    f"{api_suffix} unavailable (HTTP {response.status_code})."
                )
            if response.status_code != 200:
                snippet = response.text[:500].replace("\n", " ")
                raise RuntimeError(f"Jira request failed {response.status_code}: {snippet}")

            data = response.json()
            uses_token_pagination = "isLast" in data or "nextPageToken" in data
            if uses_token_pagination:
                # When using /search/jql the API relies on an opaque nextPageToken instead of numeric offsets.
                next_page_token = data.get("nextPageToken")
            else:
                if total is None:
                    reported_total = data.get("total")
                    if reported_total is not None:
                        total = int(reported_total)
                        _debug(f"Total issues reported: {total}")

            issues = data.get("issues", [])
            fetched_count = len(issues)
            _debug(f"Fetched batch startAt={start_at} count={fetched_count}")

            if not issues:
                break

            all_issues.extend(issues)

            if uses_token_pagination:
                if not data.get("isLast", True) and next_page_token:
                    # Continue with the server-provided cursor.
                    continue
                break

            # Legacy pagination uses numeric offsets with optional totals.
            if total is not None:
                start_at += max_results
                if start_at >= total:
                    break
                continue

            # No total available (older servers) - stop once returned rows are smaller than requested.
            if fetched_count < max_results:
                break
            start_at += max_results

        _debug(f"Completed fetch via {api_suffix}. Total collected={len(all_issues)}")
        return all_issues

    errors: List[str] = []
    for path in ("/rest/api/3/search/jql", "/rest/api/3/search"):
        try:
            return _fetch_with_endpoint(path)
        except JiraEndpointUnavailable as exc:
            errors.append(str(exc))
            continue

    details = "; ".join(errors) if errors else "Unknown cause"
    raise RuntimeError(
        f"Unable to query Jira search API. Attempted new (/search/jql) and legacy (/search) endpoints: {details}"
    )
