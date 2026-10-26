"""Extract dataset and download records from saved SCI landing-page HTML."""

import re
from collections.abc import Iterable
from pathlib import PurePosixPath
from urllib.parse import unquote, urljoin, urlsplit

from bs4 import BeautifulSoup, Tag

from .model import DatasetPageResult, DatasetRecord, FileRecord

# Keep source-language labels here; extraction logic uses model field names.
_LABELS = {
    "موضوع": "subject_path",
    "زمان آماری": "statistical_period",
    "دوره ی انتشار": "publication_frequency",
    "حجم": "file_size_display",
    "نوع انتشار": "publication_type",
    "منبع": "source",
    "زمان انتشار": "published_at",
}


def _text(tag: Tag | None) -> str | None:
    if tag is None:
        return None
    return " ".join(tag.get_text(" ", strip=True).split()) or None


def _metadata(tags: Iterable[Tag]) -> dict[str, str | None]:
    fields = {}
    for tag in tags:
        label, separator, value = (_text(tag) or "").partition(":")
        field = _LABELS.get(label.strip())
        if separator and field is not None:
            if field == "subject_path":
                for br in tag.find_all("br"):
                    br.replace_with("\n")
                value = tag.get_text(" ", strip=False).partition(":")[2]
            fields[field] = value.strip() or None
    return fields


def _decode_url_text(url: str) -> str:
    """Decode UTF-8 text while preserving escaped ASCII URL syntax."""

    def decode(match: re.Match[str]) -> str:
        try:
            return unquote(match[0], errors="strict")
        except UnicodeDecodeError:
            return match[0]

    return re.sub(r"(?:%[89a-fA-F][0-9a-fA-F])+", decode, url)


def _download_url(href: str, page_url: str) -> str | None:
    target = href.strip()
    if not target or re.fullmatch(
        r"\d+(?:[.,/]\d+)?\s*[KMGT]?B", target, re.IGNORECASE
    ):
        return None
    try:
        resolved = urljoin(page_url, target)
        parts = urlsplit(resolved)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            return None
    except ValueError:
        return None
    return _decode_url_text(resolved)


def _file_record(anchor: Tag, dataset_id: int, page_url: str) -> FileRecord:
    identifier = str(anchor.get("data-id", ""))
    if not re.fullmatch(r"[0-9]+", identifier):
        raise ValueError(f"Dataset {dataset_id} has a download without a valid file ID")
    block = anchor.find_parent("p", class_="border-box")
    if block is None:
        raise ValueError(f"File {identifier} is missing its download metadata block")
    href = str(anchor.get("href", ""))
    url = _download_url(href, page_url)
    name = unquote(PurePosixPath(urlsplit(url).path).name) if url else None
    suffix = PurePosixPath(name).suffix.lower().lstrip(".") if name else ""
    if not suffix or suffix in ("html", "htm", "aspx", "asp", "php", "jsp"):
        name, suffix = None, ""
    declared_format = next(
        (
            value[1:].lower()
            for value in block.get("class", [])
            if re.fullmatch(r"\.[a-zA-Z0-9]+", value)
        ),
        None,
    )
    fields = _metadata(block.select("span.bc"))
    return {
        "dataset_id": dataset_id,
        "file_id": int(identifier),
        "download_href": href,
        "download_url": url,
        "file_name": name,
        "file_format": declared_format or suffix or None,
        "file_size_display": fields.get("file_size_display"),
        "publication_type": fields.get("publication_type"),
        "source": fields.get("source"),
        "published_at": fields.get("published_at"),
        "revision": _text(block.select_one(".revision-item")),
    }


def parse_dataset_page(html: str, *, page_url: str) -> DatasetPageResult:
    """Parse one page into a dataset record and all advertised download records.

    page_url must be an absolute HTTP(S) SCI page URL containing /statid/<id>.
    subject_path contains one list of hierarchy levels per line, preserving repeats.
    Missing optional metadata becomes None (or [] for subject_path). Dates,
    periods, sizes, and unknown-value labels retain their source text. Malformed
    download targets are retained with a null download_url. Missing page details,
    titles, or required identifiers raise ValueError. Performs no file/network I/O.
    """
    parts = urlsplit(page_url)
    match = re.search(r"/statid/([0-9]+)(?:/|$)", parts.path)
    if parts.scheme not in ("http", "https") or not parts.hostname or match is None:
        raise ValueError("page_url must be an absolute HTTP(S) URL with /statid/<id>")
    dataset_id = int(match[1])
    detail = BeautifulSoup(html, "lxml").select_one(".main-statistics-detail")
    if detail is None:
        raise ValueError(f"Dataset {dataset_id} page has no dataset detail section")
    title = _text(detail.select_one(".title-style"))
    if title is None:
        raise ValueError(f"Dataset {dataset_id} page has no dataset title")
    fields = _metadata(detail.select(".each-list-type p"))
    subject = fields.get("subject_path") or ""
    dataset: DatasetRecord = {
        "dataset_id": dataset_id,
        "title": title,
        "page_url": page_url,
        "subject_path": [
            [" ".join(part.split()) for part in line.split(">>") if part.strip()]
            for line in subject.splitlines()
            if line.replace(">>", "").strip()
        ],
        "statistical_period": fields.get("statistical_period"),
        "publication_frequency": fields.get("publication_frequency"),
    }
    return {
        "dataset": dataset,
        "files": [
            _file_record(anchor, dataset_id, page_url)
            for anchor in detail.select("a.downloadable")
        ],
    }
