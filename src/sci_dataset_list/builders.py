"""Produce SCI resources using existing parsers and FHRS working storage.

Call builders explicitly with a managed resource. Inputs must already exist in
working storage; builders do not recursively build dependencies. Existing outputs
are skipped unless overwrite=True. Batch failures propagate and retain previously
completed files so the next run can resume. Directory builds do not remove stale
outputs. Download builders use certificate verification by default.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from urllib.parse import urlsplit

import requests

from .download import (
    DATASET_PAGE_BASE_URL,
    RSS_URL,
    download_dataset_page,
    download_rss,
)
from .page_parser import parse_dataset_page
from .page_parser.model import DatasetRecord, FileRecord
from .parser import rss_to_csv_buffer

if TYPE_CHECKING:
    from fhrs.runtime import ManagedResource

_LOGGER = logging.getLogger(__name__)


def _destination(
    resource: ManagedResource, expected_type: Literal["file", "directory"]
) -> Path:
    if resource.resource_type != expected_type:
        raise TypeError(f"This builder requires a {expected_type} resource")
    return resource.working_path


def build_rss(
    resource: ManagedResource,
    *,
    url: str = RSS_URL,
    timeout: float = 30,
    verify: bool = False,
    overwrite: bool = True,
) -> Path:
    """Download the original RSS export into a file resource."""
    destination = _destination(resource, "file")
    if destination.exists() and not overwrite:
        return destination
    content = download_rss(url=url, timeout=timeout, verify=verify)
    return resource.put(content, overwrite=overwrite)


def build_rss_catalog(
    resource: ManagedResource,
    *,
    source_resource: str = "rss",
    overwrite: bool = True,
) -> Path:
    """Convert the working RSS export into a CSV file resource."""
    destination = _destination(resource, "file")
    if destination.exists() and not overwrite:
        return destination
    source = resource.dataset.resources[source_resource].working_path
    return resource.put(rss_to_csv_buffer(source), overwrite=overwrite)


def build_dataset_pages(
    resource: ManagedResource,
    *,
    source_resource: str = "rss_catalog",
    timeout: float = 30,
    verify: bool = False,
    overwrite: bool = False,
) -> Path:
    """Download distinct catalog links as <dataset_id>.html, skipping saved pages."""
    destination = _destination(resource, "directory")
    catalog = resource.dataset.table(source_resource).load(source="working")
    destination.mkdir(parents=True, exist_ok=True)
    with requests.Session() as session:
        for page_url in catalog["link"].dropna().drop_duplicates():
            match = re.search(r"/statid/([0-9]+)(?:/|$)", urlsplit(page_url).path)
            if match is None:
                raise ValueError(f"Catalog link has no valid dataset ID: {page_url!r}")
            filename = f"{int(match[1])}.html"
            if (destination / filename).exists() and not overwrite:
                continue
            content = download_dataset_page(
                int(match[1]), timeout=timeout, verify=verify, session=session
            )
            resource.add(filename, content, overwrite=overwrite)
    return destination


def build_page_metadata(
    resource: ManagedResource,
    *,
    source_resource: str = "dataset_pages",
    overwrite: bool = False,
    skip_invalid: bool = False,
) -> Path:
    """Parse saved pages into JSON; optionally log and skip invalid page content."""
    destination = _destination(resource, "directory")
    source = resource.dataset.resources[source_resource].working_path
    if not source.exists():
        raise FileNotFoundError(source)
    if not source.is_dir():
        raise NotADirectoryError(source)
    destination.mkdir(parents=True, exist_ok=True)
    for path in sorted(source.glob("*.html")):
        filename = f"{path.stem}.json"
        if (destination / filename).exists() and not overwrite:
            continue
        try:
            result = parse_dataset_page(
                path.read_text(encoding="utf-8"),
                page_url=f"{DATASET_PAGE_BASE_URL}/{path.stem}",
            )
        except ValueError as error:
            if not skip_invalid:
                raise
            _LOGGER.warning("Skipping invalid dataset page %s: %s", path.name, error)
            continue
        resource.add(
            filename,
            json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8"),
            overwrite=overwrite,
        )
    return destination


def _build_metadata_csv(
    resource: ManagedResource,
    *,
    record_type: Literal["dataset", "files"],
    source_resource: str,
    overwrite: bool,
) -> Path:
    destination = _destination(resource, "file")
    if destination.exists() and not overwrite:
        return destination
    source = resource.dataset.resources[source_resource].working_path
    if not source.exists():
        raise FileNotFoundError(source)
    if not source.is_dir():
        raise NotADirectoryError(source)
    model = DatasetRecord if record_type == "dataset" else FileRecord
    buffer = io.StringIO(newline="")
    fields = [
        field
        for field in model.__annotations__
        if field not in ("page_url", "download_href")
    ]
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    for path in sorted(source.glob("*.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        records = [result["dataset"]] if record_type == "dataset" else result["files"]
        for record in records:
            if record_type == "dataset":
                record = dict(
                    record,
                    subject_path=json.dumps(record["subject_path"], ensure_ascii=False),
                )
            writer.writerow({field: record[field] for field in fields})
    return resource.put(buffer.getvalue().encode("utf-8"), overwrite=overwrite)


def build_datasets(
    resource: ManagedResource,
    *,
    source_resource: str = "page_metadata",
    overwrite: bool = True,
) -> Path:
    """Write one CSV row per dataset, including references without downloads.

    Omit page_url, which is derived from dataset_id.
    Preserve subject_path as a JSON nested list in a single CSV cell.
    None becomes an empty CSV field. Publish only after all inputs are read.
    """
    return _build_metadata_csv(
        resource,
        record_type="dataset",
        source_resource=source_resource,
        overwrite=overwrite,
    )


def build_references(
    resource: ManagedResource,
    *,
    source_resource: str = "page_metadata",
    overwrite: bool = True,
) -> Path:
    """Write one CSV row per advertised reference, linked by dataset_id.

    Omit download_href, which remains available in page metadata.
    Include file downloads, page links, and unusable targets.
    None becomes an empty CSV field.
    Dates, periods and displayed sizes are not normalized.
    """
    return _build_metadata_csv(
        resource,
        record_type="files",
        source_resource=source_resource,
        overwrite=overwrite,
    )
