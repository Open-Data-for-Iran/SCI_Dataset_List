"""FHRS dataset declaration for the SCI dataset list."""

from fhrs.manifest.models import Dataset, EmbeddedStorage, Location, Resource, Table
from jdatetime import datetime

dataset = Dataset(
    name="sci_dataset_list",
    title="SCI Dataset List",
    schema_version="0.1.0",
    release=datetime.today().strftime(r"%Y-%m-%d"),
    storages={
        "embedded": EmbeddedStorage(path="../../data/sci_dataset_list"),
    },
    resources={
        "rss": Resource(
            suffix=".xml",
            title="SCI RSS export",
            description="Original dataset listings published by SCI.",
        ),
        "rss_catalog": Resource(
            suffix=".csv",
            title="RSS catalog",
            description="Dataset entries extracted from the SCI RSS export.",
        ),
        "dataset_pages": Resource(
            type="directory",
            title="Dataset pages",
            description="Saved SCI landing pages used for metadata extraction.",
        ),
        "page_metadata": Resource(
            type="directory",
            title="Page metadata",
            description="Parsed dataset metadata and references from each landing page.",
        ),
        "datasets": Resource(
            suffix=".csv",
            locations=[Location(storage="embedded", uri="datasets.csv")],
            title="Datasets",
            description="One row per SCI dataset, including website references.",
        ),
        "references": Resource(
            suffix=".csv",
            locations=[Location(storage="embedded", uri="references.csv")],
            title="References",
            description="File downloads and page links advertised by each dataset.",
        ),
    },
    tables={
        "rss_catalog": Table(
            resource="rss_catalog",
            reader="csv",
            title="RSS catalog",
            description="Dataset entries extracted from the SCI RSS export.",
        ),
        "datasets": Table(
            resource="datasets",
            reader="csv",
            title="Datasets",
            description="One row per SCI dataset, including website references.",
        ),
        "references": Table(
            resource="references",
            reader="csv",
            title="References",
            description="File downloads and page links advertised by each dataset.",
        ),
    },
)
