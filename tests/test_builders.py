import csv
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import requests
from fhrs import runtime
from fhrs.manifest import models as manifest

from sci_dataset_list.builders import (
    build_dataset_pages,
    build_datasets,
    build_page_metadata,
    build_references,
    build_rss,
    build_rss_catalog,
)

RSS = b"""<rss><channel><item><title>First</title>
<link>https://amar.org.ir/statistical-information/statid/20804</link>
<description>First dataset</description></item></channel></rss>"""
PAGE = """<div class="main-statistics-detail"><h5 class="title-style">Dataset</h5>
<div class="each-list-type"><p>زمان آماری: 1390</p></div>
<p class=".xls border-box"><a class="downloadable" data-id="20957"
href="/files/data.xls">Download</a></p></div>"""


class BuilderTests(unittest.TestCase):
    def setUp(self):
        sleeper = patch(
            "sci_dataset_list.download._download.retry.sleep", return_value=None
        )
        sleeper.start()
        self.addCleanup(sleeper.stop)
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.dataset = runtime.ManagedDataset(
            manifest.Dataset(
                name="test",
                resources={
                    "rss": {"suffix": ".xml"},
                    "rss_catalog": {"suffix": ".csv"},
                    "dataset_pages": {"type": "directory"},
                    "page_metadata": {"type": "directory"},
                    "datasets": {"suffix": ".csv"},
                    "references": {"suffix": ".csv"},
                },
            ),
            working_directory=self.root,
        )

    def test_rss_download_checks_status_and_skips_existing_output(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.content = RSS
        resource = self.dataset.resource("rss")
        with patch(
            "sci_dataset_list.download.requests.get", return_value=response
        ) as get:
            path = build_rss(resource, timeout=12, verify=False)
            self.assertEqual(path.read_bytes(), RSS)
            response.raise_for_status.assert_called_once()
            self.assertEqual(get.call_args.kwargs, {"timeout": 12, "verify": False})
            self.assertEqual(build_rss(resource, overwrite=False), path)
            self.assertEqual(get.call_count, 1)
            response.content = b"new"
            build_rss(resource, overwrite=True)
            self.assertEqual(path.read_bytes(), b"new")

    def test_http_failure_does_not_publish_output(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.raise_for_status.side_effect = requests.HTTPError("failed")
        with (
            patch("sci_dataset_list.download.requests.get", return_value=response),
            self.assertRaises(requests.HTTPError),
        ):
            build_rss(self.dataset.resource("rss"))
        self.assertFalse((self.root / "rss.xml").exists())

    def test_portal_error_does_not_replace_existing_resource(self):
        resource = self.dataset.resource("rss")
        existing = resource.put(RSS)
        response = MagicMock()
        response.__enter__.return_value = response
        response.content = "یک خطای بحرانی اتفاق افتاده است".encode()
        with (
            patch("sci_dataset_list.download.requests.get", return_value=response),
            self.assertRaisesRegex(ValueError, "critical error"),
        ):
            build_rss(resource, overwrite=True)
        self.assertEqual(existing.read_bytes(), RSS)

    def test_catalog_build_reads_rss_preserves_input_and_supports_overwrite(self):
        source = self.dataset.resource("rss").put(RSS)
        resource = self.dataset.resource("rss_catalog")
        path = build_rss_catalog(resource)
        self.assertIn("First dataset", path.read_text(encoding="utf-8"))
        self.assertEqual(source.read_bytes(), RSS)
        path.write_text("existing", encoding="utf-8")
        build_rss_catalog(resource, overwrite=False)
        self.assertEqual(path.read_text(encoding="utf-8"), "existing")
        build_rss_catalog(resource, overwrite=True)
        self.assertIn("First dataset", path.read_text(encoding="utf-8"))

    def test_pages_build_is_incremental_and_reuses_session(self):
        self.dataset.resource("rss_catalog").put(
            b"title,link\nFirst,https://amar.org.ir/statistical-information/statid/20804\n"
            b"Duplicate,https://amar.org.ir/statistical-information/statid/20804\n"
            b"Second,https://amar.org.ir/statistical-information/statid/20816\n"
        )
        pages = self.dataset.resource("dataset_pages")
        existing = pages.add("20804.html", b"keep")
        response = MagicMock()
        response.__enter__.return_value = response
        response.content = PAGE.encode("utf-8")
        session = MagicMock()
        session.__enter__.return_value = session
        session.get.return_value = response
        with patch("sci_dataset_list.builders.requests.Session", return_value=session):
            path = build_dataset_pages(pages, timeout=12, verify=True)
            self.assertEqual(path, self.root / "dataset_pages")
            self.assertEqual(existing.read_bytes(), b"keep")
            self.assertEqual((path / "20816.html").read_bytes(), PAGE.encode("utf-8"))
            session.get.assert_called_once_with(
                "https://amar.org.ir/statistical-information/statid/20816",
                timeout=12,
                verify=True,
            )
            build_dataset_pages(pages, overwrite=True)
            self.assertEqual(existing.read_bytes(), PAGE.encode("utf-8"))
            self.assertEqual(session.get.call_count, 3)

    def test_metadata_build_saves_parser_results_and_skips_existing_records(self):
        self.dataset.resource("dataset_pages").add("20804.html", PAGE.encode("utf-8"))
        resource = self.dataset.resource("page_metadata")
        path = build_page_metadata(resource)
        record_path = path / "20804.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        self.assertEqual(record["dataset"]["dataset_id"], 20804)
        self.assertEqual(record["dataset"]["statistical_period"], "1390")
        self.assertEqual(record["files"][0]["file_id"], 20957)
        record_path.write_text("existing", encoding="utf-8")
        build_page_metadata(resource)
        self.assertEqual(record_path.read_text(encoding="utf-8"), "existing")
        build_page_metadata(resource, overwrite=True)
        self.assertEqual(json.loads(record_path.read_text(encoding="utf-8")), record)

    def test_metadata_build_rejects_invalid_pages_without_saving_records(self):
        pages = self.dataset.resource("dataset_pages")
        pages.add("20804.html", b"<html>Access denied</html>")
        with self.assertRaises(ValueError):
            build_page_metadata(self.dataset.resource("page_metadata"))
        self.assertFalse((self.root / "page_metadata/20804.json").exists())

    def test_metadata_can_skip_invalid_pages_and_continue_with_warning(self):
        pages = self.dataset.resource("dataset_pages")
        pages.add("20804.html", b"<html>Access denied</html>")
        pages.add("20816.html", PAGE.encode("utf-8"))
        metadata = self.dataset.resource("page_metadata")
        with self.assertLogs("sci_dataset_list.builders", level="WARNING") as logs:
            destination = build_page_metadata(metadata, skip_invalid=True)
        self.assertFalse((destination / "20804.json").exists())
        result = json.loads((destination / "20816.json").read_text(encoding="utf-8"))
        self.assertEqual(result["dataset"]["dataset_id"], 20816)
        self.assertIn("20804.html", "\n".join(logs.output))
        self.assertIn("no dataset detail section", "\n".join(logs.output))

    def test_csv_tables_preserve_metadata_and_datasets_without_files(self):
        from sci_dataset_list.page_parser import parse_dataset_page

        result = parse_dataset_page(
            PAGE, page_url="https://amar.org.ir/statistical-information/statid/20804"
        )
        result["dataset"]["title"] = 'عنوان, "جدول"\nدوم'
        result["dataset"]["subject_path"] = [
            ["آمارهای جمعیتی و اجتماعی", "نیروی کار", "نیروی انسانی"],
            ["آمارهای جمعیتی و اجتماعی", "جمعیت و مهاجرت", "جمعیت"],
        ]
        result["files"][0]["download_url"] = None
        second_file = dict(result["files"][0], file_id=20958)
        result["files"].append(second_file)
        result["files"].append(
            dict(
                second_file,
                file_id=20959,
                download_href="https://example.org/statistics",
                download_url="https://example.org/statistics",
                file_name=None,
                file_format=None,
            )
        )
        reference = {
            "dataset": dict(result["dataset"], dataset_id=20808, subject_path=[]),
            "files": [],
        }
        source = self.dataset.resource("page_metadata")
        for record in (result, reference):
            source.add(
                f"{record['dataset']['dataset_id']}.json",
                json.dumps(record, ensure_ascii=False).encode("utf-8"),
            )
        datasets_path = build_datasets(self.dataset.resource("datasets"))
        files_path = build_references(self.dataset.resource("references"))
        self.assertEqual(datasets_path, self.root / "datasets.csv")
        self.assertEqual(files_path, self.root / "references.csv")
        with datasets_path.open(encoding="utf-8", newline="") as stream:
            datasets = list(csv.DictReader(stream))
        with files_path.open(encoding="utf-8", newline="") as stream:
            files = list(csv.DictReader(stream))
        self.assertEqual([row["dataset_id"] for row in datasets], ["20804", "20808"])
        self.assertNotIn("page_url", datasets[0])
        self.assertEqual(datasets[0]["title"], result["dataset"]["title"])
        self.assertEqual(
            json.loads(datasets[0]["subject_path"]),
            result["dataset"]["subject_path"],
        )
        self.assertEqual(json.loads(datasets[1]["subject_path"]), [])
        self.assertEqual(datasets[0]["publication_frequency"], "")
        self.assertEqual([row["file_id"] for row in files], ["20957", "20958", "20959"])
        self.assertEqual(files[2]["download_url"], "https://example.org/statistics")
        self.assertEqual(files[2]["file_name"], "")
        self.assertEqual({row["dataset_id"] for row in files}, {"20804"})
        self.assertEqual(files[0]["download_url"], "")
        self.assertNotIn("download_href", files[0])
        original = json.loads(
            (source.working_path / "20804.json").read_text(encoding="utf-8")
        )
        self.assertEqual(original["files"][0]["download_href"], "/files/data.xls")

    def test_csv_tables_have_headers_for_empty_input_and_support_overwrite(self):
        from sci_dataset_list.page_parser.model import DatasetRecord, FileRecord

        self.dataset.resource("page_metadata").working_path.mkdir()
        for builder, name, model in (
            (build_datasets, "datasets", DatasetRecord),
            (build_references, "references", FileRecord),
        ):
            with self.subTest(table=name):
                resource = self.dataset.resource(name)
                path = builder(resource)
                with path.open(encoding="utf-8", newline="") as stream:
                    self.assertEqual(
                        list(csv.reader(stream)),
                        [
                            [
                                field
                                for field in model.__annotations__
                                if field not in ("page_url", "download_href")
                            ]
                        ],
                    )
                expected = path.read_bytes()
                path.write_bytes(b"existing")
                builder(resource, overwrite=False, source_resource="unused")
                self.assertEqual(path.read_bytes(), b"existing")
                builder(resource, overwrite=True)
                self.assertEqual(path.read_bytes(), expected)

    def test_csv_tables_reject_missing_or_corrupt_inputs_without_replacing_output(self):
        for builder, name in (
            (build_datasets, "datasets"),
            (build_references, "references"),
        ):
            with self.subTest(table=name), self.assertRaises(FileNotFoundError):
                builder(self.dataset.resource(name))
        source = self.dataset.resource("page_metadata")
        source.add("bad.json", b"invalid json")
        for builder, name in (
            (build_datasets, "datasets"),
            (build_references, "references"),
        ):
            with self.subTest(table=name):
                path = self.dataset.resource(name).put(b"existing")
                with self.assertRaises(json.JSONDecodeError):
                    builder(self.dataset.resource(name), overwrite=True)
                self.assertEqual(path.read_bytes(), b"existing")

    def test_missing_input_directory_is_an_error(self):
        with self.assertRaises(FileNotFoundError):
            build_page_metadata(self.dataset.resource("page_metadata"))


if __name__ == "__main__":
    unittest.main()
