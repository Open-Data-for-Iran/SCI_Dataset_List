import unittest

from sci_dataset_list.page_parser import parse_dataset_page

PAGE_URL = "https://amar.org.ir/statistical-information/statid/20816"


def page(downloads="", metadata=""):
    return f"""<html><head><title>Generic site title</title></head><body>
    <p>موضوع: navigation</p><a class="downloadable" data-id="999" href="/ignore.pdf">Other</a>
    <div class="detail main-statistics-detail">
      <h5 class="title-style"><a href="{PAGE_URL}"> جمعیت <b>کشور</b> </a></h5>
      <div class="inner-statistics-data-info">
        <div class="each-list-type"><p>موضوع: جمعیتی &gt;&gt; جمعیت &gt;&gt; کشور</p></div>
        <div class="each-list-type"><p>زمان آماری: 1335 - 1390</p></div>
        <div class="each-list-type"><p>دوره ی انتشار: </p></div>
        {metadata}{downloads}
      </div>
    </div></body></html>"""


def download(identifier, href, format=".pdf", metadata=""):
    return f"""<p class="{format} border-box">
    <span class="bc"><span class="file-format"><img src="/icons/doc.png"></span>
      <a class="downloadable" data-id="{identifier}" href="{href}">دانلود فایل</a>
    </span>{metadata}</p>"""


class PageParserTests(unittest.TestCase):
    def test_extracts_dataset_and_all_downloads_with_separate_metadata(self):
        html = page(
            download(
                20967,
                "/files/report%20one.pdf?version=2&amp;x=1",
                metadata="""
                <span class="file-size bc">حجم:0/23 MB</span>
                <span class="file-size bc">نوع انتشار: نمودار</span>
                <span class="file-size bc">منبع: نامشخص</span>
                <span class="bc">زمان انتشار: 1391</span>
                <span class="revision-item bc">تجدید نظر شده</span>""",
            )
            + download(
                20968,
                "/files/report.docx",
                format=".docx",
                metadata="""
                <span class="bc">زمان انتشار: 1403/04/16</span>
                <span class="bc">نوع انتشار: نشریه</span>""",
            )
        )
        result = parse_dataset_page(html, page_url=PAGE_URL)
        self.assertEqual(
            result["dataset"],
            {
                "dataset_id": 20816,
                "title": "جمعیت کشور",
                "page_url": PAGE_URL,
                "subject_path": [["جمعیتی", "جمعیت", "کشور"]],
                "statistical_period": "1335 - 1390",
                "publication_frequency": None,
            },
        )
        self.assertEqual(len(result["files"]), 2)
        first, second = result["files"]
        self.assertEqual(
            first,
            {
                "dataset_id": 20816,
                "file_id": 20967,
                "download_href": "/files/report%20one.pdf?version=2&x=1",
                "download_url": "https://amar.org.ir/files/report%20one.pdf?version=2&x=1",
                "file_name": "report one.pdf",
                "file_format": "pdf",
                "file_size_display": "0/23 MB",
                "publication_type": "نمودار",
                "source": "نامشخص",
                "published_at": "1391",
                "revision": "تجدید نظر شده",
            },
        )
        self.assertEqual(second["file_format"], "docx")
        self.assertEqual(second["published_at"], "1403/04/16")
        self.assertIsNone(second["revision"])
        self.assertIsNone(second["file_size_display"])

    def test_subject_paths_preserve_breaks_levels_and_repeated_paths(self):
        html = page().replace(
            "موضوع: جمعیتی &gt;&gt; جمعیت &gt;&gt; کشور",
            "موضوع: جمعیتی &gt;&gt; <b>جمعیت</b> &gt;&gt; کشور"
            "<br/> جمعیتی &gt;&gt; خانوار <br>"
            "جمعیتی &gt;&gt; جمعیت &gt;&gt; کشور<br/><br/>",
        )
        subject = parse_dataset_page(html, page_url=PAGE_URL)["dataset"]["subject_path"]
        self.assertEqual(
            subject,
            [
                ["جمعیتی", "جمعیت", "کشور"],
                ["جمعیتی", "خانوار"],
                ["جمعیتی", "جمعیت", "کشور"],
            ],
        )

    def test_keeps_dataset_without_downloads(self):
        result = parse_dataset_page(page(), page_url=PAGE_URL)
        self.assertEqual(result["files"], [])

    def test_preserves_invalid_targets_without_inventing_urls_or_formats(self):
        for href in ("0.237 MB", "javascript:alert(1)", "data:text/plain,test", ""):
            with self.subTest(href=href):
                result = parse_dataset_page(
                    page(download(1, href, format="Other")), page_url=PAGE_URL
                )
                record = result["files"][0]
                self.assertEqual(record["download_href"], href)
                self.assertIsNone(record["download_url"])
                self.assertIsNone(record["file_name"])
                self.assertIsNone(record["file_format"])

    def test_webpage_targets_are_not_treated_as_file_formats(self):
        for href in (
            "https://nnt.sci.org.ir/newifs.aspx",
            "/Census/general-census-1#section",
        ):
            with self.subTest(href=href):
                record = parse_dataset_page(
                    page(download(1, href, format="Other")), page_url=PAGE_URL
                )["files"][0]
                self.assertIsNotNone(record["download_url"])
                self.assertIsNone(record["file_name"])
                self.assertIsNone(record["file_format"])

    def test_decodes_url_text_without_changing_escaped_separators_or_raw_href(self):
        cases = (
            (
                "/files/%D8%A2%D9%85%D8%A7%D8%B1.pdf",
                "https://amar.org.ir/files/آمار.pdf",
                "آمار.pdf",
            ),
            (
                (
                    "https://example.org/%D8%A2%D9%85%D8%A7%D8%B1%2Fpage"
                    "?name=%D8%A2%D9%85%D8%A7%D8%B1%26other%3D1&next=%252F&x=a+b"
                ),
                "https://example.org/آمار%2Fpage?name=آمار%26other%3D1&next=%252F&x=a+b",
                None,
            ),
            (
                "https://example.org/%FF/%broken",
                "https://example.org/%FF/%broken",
                None,
            ),
        )
        for href, url, filename in cases:
            with self.subTest(href=href):
                record = parse_dataset_page(
                    page(download(1, href, format="Other")), page_url=PAGE_URL
                )["files"][0]
                self.assertEqual(record["download_href"], href)
                self.assertEqual(record["download_url"], url)
                self.assertEqual(record["file_name"], filename)

    def test_resolves_relative_links_and_infers_format_when_block_is_unknown(self):
        record = parse_dataset_page(
            page(download(1, "../../files/data.zip", format="Other")), page_url=PAGE_URL
        )["files"][0]
        self.assertEqual(record["download_url"], "https://amar.org.ir/files/data.zip")
        self.assertEqual(record["file_name"], "data.zip")
        self.assertEqual(record["file_format"], "zip")

    def test_missing_optional_fields_are_null_or_empty(self):
        html = '<div class="main-statistics-detail"><h5 class="title-style">Title</h5></div>'
        record = parse_dataset_page(html, page_url=PAGE_URL)["dataset"]
        self.assertEqual(record["subject_path"], [])
        self.assertIsNone(record["statistical_period"])
        self.assertIsNone(record["publication_frequency"])

    def test_rejects_error_pages_and_missing_required_identifiers(self):
        for html, url in (
            ("<html>Access denied</html>", PAGE_URL),
            ('<div class="main-statistics-detail"></div>', PAGE_URL),
            (page(), "https://amar.org.ir/statistical-information"),
            (page(), "file:///statid/20816"),
            (page(download("invalid", "/files/report.pdf")), PAGE_URL),
            (page(download("", "/files/report.pdf")), PAGE_URL),
        ):
            with self.subTest(html=html, url=url), self.assertRaises(ValueError):
                parse_dataset_page(html, page_url=url)


if __name__ == "__main__":
    unittest.main()
