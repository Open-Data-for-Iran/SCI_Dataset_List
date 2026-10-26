# SCI Dataset List

Build a catalog of Statistical Center of Iran datasets from its RSS list and
metadata available on each dataset landing page.

## Resources

| Resource | Type | Purpose |
| --- | --- | --- |
| `rss` | XML file | Original SCI RSS export. |
| `rss_catalog` | CSV file | Dataset entries extracted from the RSS export, before landing-page enrichment. |
| `dataset_pages` | Directory | Saved dataset landing pages used to enrich the catalog. |
| `page_metadata` | Directory | Extracted page results, one `<dataset_id>.json` file containing the dataset record and all advertised downloads. |
| `datasets` | CSV file / table | One row per dataset, including website references without downloads. |
| `references` | CSV file / table | One row per advertised reference (file or web page), linked to `datasets` by `dataset_id`. |

Working resources are stored under `data/sci_dataset_list/`: `rss.xml`,
`rss_catalog.csv`, `dataset_pages/`, `page_metadata/`, `datasets.csv`, and
`references.csv`. Save each landing page as
`<dataset_id>.html`, using the SCI identifier in its URL so it can be matched
back to the RSS entry.

To regenerate the CSV from the locally saved RSS export:

```python
import fhrs
from sci_dataset_list.parser import rss_to_csv_buffer

dataset = fhrs.load("sci_dataset_list", manage=True)
dataset.resource("rss_catalog").put(
    rss_to_csv_buffer(dataset.resource("rss").source("working").urlpath),
    overwrite=True,
)
```

The final dataset list will combine `rss_catalog` with metadata extracted from
`dataset_pages` and saved in `page_metadata`, matching entries by their SCI
identifier or landing-page URL.
The final enriched list is assembled separately from the page parser results.


## Parse dataset landing pages

```python
from pathlib import Path
from sci_dataset_list.page_parser import parse_dataset_page

path = Path("data/sci_dataset_list/dataset_pages/20804.html")
result = parse_dataset_page(
    path.read_text(encoding="utf-8"),
    page_url="https://amar.org.ir/statistical-information/statid/20804",
)
dataset_record = result["dataset"]
file_records = result["files"]
```

The parser returns TypedDict-compatible dictionaries: one dataset and zero or
more file records, each carrying its dataset ID. It reads only the dataset detail
section, keeping each download's metadata separate. Missing metadata becomes
`None`, while absent subjects or downloads become an empty list.
`subject_path` is a list of lists: each inner list holds one hierarchy from
broadest subject to most specific. HTML line breaks separate paths; their order
and repeated paths are preserved.
Dates, statistical periods, displayed file sizes, and unknown-value labels are
preserved as text for later normalization.

Relative targets are resolved against `page_url`. Percent-encoded UTF-8 text in
`download_url` is decoded with `urllib.parse.unquote()` for readability; escaped
ASCII characters (including URL separators) and invalid UTF-8 escapes stay encoded.
Each file preserves its original
HTML `href` value in `download_href`; malformed targets (including file sizes
misplaced in links) have `download_url=None`. Web-page targets are retained as URLs
without inventing file names or formats. Formats come from the download block,
falling back to a file extension in its URL; generic icons are not used.

Missing dataset details, titles, or required IDs raise `ValueError`. The parser
performs no file or network I/O and does not create DataFrames or save records.


## Store extracted page metadata

Save each `parse_dataset_page()` result as UTF-8 JSON in `page_metadata`:

```python
import json
import fhrs

# result is the dictionary returned by parse_dataset_page().
dataset = fhrs.load("sci_dataset_list", manage=True)
dataset_id = result["dataset"]["dataset_id"]
dataset.resource("page_metadata").add(
    f"{dataset_id}.json",
    json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8"),
    overwrite=True,
)
```

For example, `data/sci_dataset_list/page_metadata/20804.json` stores one dataset
record plus its `files` list. JSON preserves nested subject paths, multiple
file records, and null metadata. These are parsed page results; the final dataset
and reference tables are assembled separately.


## Resource builders

The functions in `sci_dataset_list.builders` produce the six resources. Pass a
managed resource and run the steps explicitly in dependency order:

```python
import fhrs
from sci_dataset_list.builders import (
    build_rss,
    build_rss_catalog,
    build_dataset_pages,
    build_page_metadata,
    build_datasets,
    build_references,
)

dataset = fhrs.load("sci_dataset_list", manage=True)
build_rss(dataset.resource("rss"))
build_rss_catalog(dataset.resource("rss_catalog"))
build_dataset_pages(dataset.resource("dataset_pages"))
build_page_metadata(dataset.resource("page_metadata"))
build_datasets(dataset.resource("datasets"))
build_references(dataset.resource("references"))
```

Directory outputs are skipped by default. Pass `overwrite=True` to refresh them;
directory builders replace matching files but preserve unrelated or stale files.
All builders return their working destination as a `Path`. Missing inputs, HTTP
errors, and parse errors propagate. Completed batch files remain available for a
subsequent run to resume.

Download builders accept `timeout` and `verify`; certificate verification defaults
to `True`. `build_rss` also accepts `url`. The other builders accept `source_resource`
to choose their input resource (or table, for the catalog). Inputs are read from
working storage. Manifest-based builder dispatch is not yet implemented in FHRS;
these functions are called directly.


### Invalid saved pages

The SCI portal can return its error-page HTML instead of a dataset detail page.
The parser rejects these pages rather than creating incomplete dataset records.
To extract the remaining valid pages, enable `skip_invalid`:

```python
build_page_metadata(dataset.resource("page_metadata"), skip_invalid=True)
```

Each skipped page is reported through the `sci_dataset_list.builders` logger with
its filename and parse error. No JSON is written for an invalid page; existing
JSON is preserved if parsing fails during an overwrite. The original HTML remains
available for inspection or re-downloading. By default, `skip_invalid=False` keeps
fail-fast behavior. File-system and write errors still propagate.


## Download individual inputs

`download.py` exposes downloads independently of FHRS storage:

```python
from sci_dataset_list.download import download_rss, download_dataset_page

rss_xml = download_rss()
page_html = download_dataset_page(20804)  # Numeric strings are accepted too.

dataset.resource("rss").put(rss_xml, overwrite=True)
dataset.resource("dataset_pages").add("20804.html", page_html, overwrite=True)
```

Both functions return raw bytes, accept `timeout` and `verify`, and propagate HTTP
errors. `download_rss` also accepts a custom `url`. Pass `session=` to reuse an
existing `requests.Session`; the caller retains ownership of it. The dataset-page
URL is constructed from its ID using the SCI HTTPS endpoint.

Certificate verification defaults to `False`, matching the current builders;
pass `verify=True` to enable it. Both download functions reject SCI's known critical-error message with
`ValueError`, even if the HTTP status is 200, before returning content for saving.
Other invalid pages are rejected by the page parser. Download functions do not
write files. The resource builders reuse these functions.


### Download retries

RSS and dataset-page downloads use Tenacity for up to **three total attempts**,
waiting one second before the second attempt and two seconds before the third.
Retryable failures are connection errors, timeouts, interrupted chunked responses,
HTTP 408/429, HTTP 5xx, and SCI's known critical-error page (including HTTP 200).
Other HTTP client errors, invalid URLs/IDs, and certificate errors are not retried.

The final original exception is re-raised after exhausted retries. SCI's known
error page raises `PortalError`, a subclass of `ValueError`, so existing handlers
continue to work. The same supplied session and request options are reused;
responses are closed between attempts and builders only save a successful result.


## Build metadata CSV tables

`build_datasets()` and `build_references()` read the saved `page_metadata/*.json`
files in filename order and write UTF-8 `datasets.csv` and `references.csv` in working
storage. They accept `source_resource="page_metadata"` and `overwrite=True`,
matching the existing CSV builder's default; pass `overwrite=False` to skip an
existing output without reading its inputs. Both return the CSV path.

The dataset CSV contains `DatasetRecord` columns except `page_url`, which can
be reconstructed as `https://amar.org.ir/statistical-information/statid/{dataset_id}`.
The `subject_path` column stores a JSON nested list in one CSV cell;
`json.loads()` restores the separate paths and their levels. Missing subjects
are stored as `[]`. Website
references and other datasets without downloads remain in this table. The references
CSV contains `FileRecord` columns except `download_href`, including page links
and unusable targets. Original `download_href` values remain in `page_metadata`.
The parser input retains its `files` key; file-specific fields remain empty when
not applicable to a reference.
Null metadata becomes empty CSV fields; dates, periods, sizes, and source labels
remain as collected. Empty input directories produce headers with no data rows.
Missing directories and malformed input raise errors; existing CSVs are replaced
only after every input has been read successfully. The source JSON is unchanged.
No RSS enrichment or website classification is inferred.

Both CSVs have embedded locations pointing to the files included in this
repository, so the tables can be loaded directly:

```python
datasets = dataset.table("datasets").load()
references = dataset.table("references").load()
```

`datasets.csv` and `references.csv` are included in version control; the RSS inputs,
saved HTML pages, and intermediate JSON metadata remain ignored.
