"""Typed records extracted from an SCI dataset landing page.

All keys are present in parser results. Empty metadata is represented by None;
dates, periods, and displayed sizes retain their source text for later normalization.
Publication times can be a Jalali year or a full date. A download block may
contain a web-page link or a malformed target rather than a direct file URL.
These TypedDict definitions provide static typing, not runtime validation.
"""

from typing import TypedDict


class DatasetRecord(TypedDict):
    """Dataset-level metadata shared by all downloads on a landing page."""

    dataset_id: int
    title: str
    page_url: str
    subject_path: list[list[str]]  # Separate paths, each ordered broad to specific.
    statistical_period: str | None
    publication_frequency: str | None


class FileRecord(TypedDict):
    """One advertised download and its own metadata, even if the link is invalid.

    Preserve download_href exactly as supplied in the HTML. download_url is the
    resolved URL with readable Unicode text; escaped ASCII syntax is preserved.
    It is None for unusable targets such as "0.237 MB". A usable URL
    can lead to a web page rather than a file; file_name is then None unless an
    actual file can be identified. file_format is None when unknown, otherwise
    the format from the download block (e.g. "docx", not the generic "doc" icon).
    """

    dataset_id: int
    file_id: int
    download_href: str
    download_url: str | None
    file_name: str | None
    file_format: str | None
    file_size_display: str | None
    publication_type: str | None
    source: str | None
    published_at: str | None  # Preserve year-only values and full Jalali dates.
    revision: str | None


class DatasetPageResult(TypedDict):
    """One dataset record and all download blocks; files is [] when none exist."""

    dataset: DatasetRecord
    files: list[FileRecord]
