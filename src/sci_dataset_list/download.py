"""Download SCI responses as bytes, retrying temporary failures up to three times.

Retries wait one then two seconds and re-raise the final original exception.
Saving and parsing are separate steps.
"""

from __future__ import annotations

import re

import requests
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

RSS_URL = "https://amar.org.ir/StatisticRssHandler.ashx?tabid=1411"
DATASET_PAGE_BASE_URL = "https://amar.org.ir/statistical-information/statid"

_CRITICAL_ERROR = "یک خطای بحرانی اتفاق افتاده است".encode()


class PortalError(ValueError):
    """SCI returned its known critical-error page instead of the requested data."""


def _retryable(error: BaseException) -> bool:
    if isinstance(error, requests.exceptions.SSLError):
        return False
    if isinstance(error, requests.HTTPError):
        response = error.response
        return response is not None and (
            response.status_code in (408, 429) or 500 <= response.status_code < 600
        )
    return isinstance(
        error,
        (
            PortalError,
            requests.ConnectionError,
            requests.Timeout,
            requests.exceptions.ChunkedEncodingError,
        ),
    )


@retry(
    retry=retry_if_exception(_retryable),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, max=5),
    reraise=True,
)
def _download(
    url: str,
    *,
    timeout: float,
    verify: bool,
    session: requests.Session | None,
) -> bytes:
    client = requests if session is None else session
    with client.get(url, timeout=timeout, verify=verify) as response:
        response.raise_for_status()
        content = response.content
        if _CRITICAL_ERROR in content:
            raise PortalError(f"SCI portal returned a critical error for {url}")
        return content


def download_rss(
    *,
    url: str = RSS_URL,
    timeout: float = 30,
    verify: bool = False,
    session: requests.Session | None = None,
) -> bytes:
    """Fetch RSS bytes, rejecting HTTP errors and the known SCI critical-error page.

    A supplied session remains open. verify matches the existing SCI builders'
    default; pass verify=True to enable certificate verification.
    """
    return _download(url, timeout=timeout, verify=verify, session=session)


def download_dataset_page(
    dataset_id: int | str,
    *,
    timeout: float = 30,
    verify: bool = False,
    session: requests.Session | None = None,
) -> bytes:
    """Fetch a dataset landing page by positive numeric ID as raw bytes.

    HTTP errors propagate; the known SCI critical-error message raises ValueError.
    Other content validation is left to parse_dataset_page(). A supplied session
    remains open. Pass verify=True to enable certificate verification.
    """
    if not re.fullmatch(r"[0-9]+", str(dataset_id)) or int(dataset_id) <= 0:
        raise ValueError("dataset_id must be a positive integer or numeric string")
    return _download(
        f"{DATASET_PAGE_BASE_URL}/{int(dataset_id)}",
        timeout=timeout,
        verify=verify,
        session=session,
    )
