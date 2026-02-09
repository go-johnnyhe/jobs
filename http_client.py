"""HTTP client factory with retry logic."""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def create_session(
    retries: int = 3,
    backoff_factor: float = 0.5,
    status_forcelist: tuple[int, ...] = (429, 500, 502, 503, 504),
    allowed_methods: tuple[str, ...] = ("GET", "POST"),
) -> requests.Session:
    """Create a requests Session with automatic retry on transient errors.

    Args:
        retries: Number of retry attempts.
        backoff_factor: Exponential backoff factor between retries.
        status_forcelist: HTTP status codes that trigger a retry.
            Pass an empty tuple to disable status-code retries.
        allowed_methods: HTTP methods eligible for retry.
            Pass ("GET",) to prevent retrying POST on connection/timeout
            failures (avoids duplicating non-idempotent requests).
    """
    session = requests.Session()
    retry = Retry(
        total=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=list(allowed_methods),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session
