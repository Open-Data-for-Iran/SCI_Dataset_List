import unittest
from unittest.mock import MagicMock, patch

import requests

from sci_dataset_list.download import download_dataset_page, download_rss


class DownloadTests(unittest.TestCase):
    def setUp(self):
        sleeper = patch(
            "sci_dataset_list.download._download.retry.sleep", return_value=None
        )
        self.sleep = sleeper.start()
        self.addCleanup(sleeper.stop)

    def response(self, content=b"downloaded content"):
        response = MagicMock()
        response.__enter__.return_value = response
        response.content = content
        return response

    def test_rss_returns_bytes_and_forwards_request_options(self):
        response = self.response(b"<rss/>")
        with patch(
            "sci_dataset_list.download.requests.get", return_value=response
        ) as get:
            content = download_rss(
                url="https://example.org/rss", timeout=12, verify=True
            )
        self.assertEqual(content, b"<rss/>")
        get.assert_called_once_with("https://example.org/rss", timeout=12, verify=True)
        response.raise_for_status.assert_called_once()
        response.__exit__.assert_called_once()

    def test_dataset_page_accepts_integer_and_string_ids(self):
        for identifier in (20804, "20804", "020804"):
            with self.subTest(identifier=identifier):
                response = self.response(b"<html>page</html>")
                with patch(
                    "sci_dataset_list.download.requests.get", return_value=response
                ) as get:
                    content = download_dataset_page(
                        identifier, timeout=10, verify=False
                    )
                self.assertEqual(content, b"<html>page</html>")
                get.assert_called_once_with(
                    "https://amar.org.ir/statistical-information/statid/20804",
                    timeout=10,
                    verify=False,
                )
                response.raise_for_status.assert_called_once()

    def test_invalid_ids_are_rejected_before_network_access(self):
        with patch("sci_dataset_list.download.requests.get") as get:
            for identifier in (None, 0, -1, "../20804", "1/2", True, "", 1.2):
                with self.subTest(identifier=identifier), self.assertRaises(ValueError):
                    download_dataset_page(identifier)
            get.assert_not_called()

    def test_http_errors_propagate(self):
        for call in (lambda: download_rss(), lambda: download_dataset_page(20804)):
            response = self.response()
            response.raise_for_status.side_effect = requests.HTTPError("failed")
            with (
                patch("sci_dataset_list.download.requests.get", return_value=response),
                self.assertRaises(requests.HTTPError),
            ):
                call()

    def test_critical_error_in_http_200_response_is_rejected(self):
        content = "<html><span>یک خطای بحرانی اتفاق افتاده است</span></html>".encode()
        for call in (lambda: download_rss(), lambda: download_dataset_page(21111)):
            with self.subTest(call=call):
                response = self.response(content)
                with (
                    patch(
                        "sci_dataset_list.download.requests.get", return_value=response
                    ),
                    self.assertRaisesRegex(ValueError, "critical error"),
                ):
                    call()
                self.assertEqual(response.raise_for_status.call_count, 3)
                self.assertEqual(response.__exit__.call_count, 3)

    def test_timeout_retries_then_succeeds(self):
        response = self.response(b"success")
        with patch(
            "sci_dataset_list.download.requests.get",
            side_effect=[requests.Timeout("slow"), response],
        ) as get:
            self.assertEqual(download_rss(), b"success")
        self.assertEqual(get.call_count, 2)
        self.sleep.assert_called_once_with(1)

    def test_portal_error_retries_then_succeeds(self):
        invalid = self.response("یک خطای بحرانی اتفاق افتاده است".encode())
        valid = self.response(b"valid page")
        with patch(
            "sci_dataset_list.download.requests.get", side_effect=[invalid, valid]
        ) as get:
            self.assertEqual(download_dataset_page(21111), b"valid page")
        self.assertEqual(get.call_count, 2)
        invalid.__exit__.assert_called_once()
        valid.__exit__.assert_called_once()

    def test_temporary_http_errors_retry_but_not_permanent_errors(self):
        for status in (408, 429, 500, 502, 503, 504, 400, 401, 403, 404):
            with self.subTest(status=status):
                response = self.response()
                response.status_code = status
                response.raise_for_status.side_effect = requests.HTTPError(
                    "failed", response=response
                )
                self.sleep.reset_mock()
                with (
                    patch(
                        "sci_dataset_list.download.requests.get", return_value=response
                    ) as get,
                    self.assertRaises(requests.HTTPError),
                ):
                    download_rss()
                expected = 3 if status in (408, 429, 500, 502, 503, 504) else 1
                self.assertEqual(get.call_count, expected)
                self.assertEqual(self.sleep.call_count, expected - 1)

    def test_connection_failure_stops_after_three_attempts_and_reraises(self):
        error = requests.ConnectionError("offline")
        with (
            patch("sci_dataset_list.download.requests.get", side_effect=error) as get,
            self.assertRaises(requests.ConnectionError) as raised,
        ):
            download_dataset_page(20804)
        self.assertIs(raised.exception, error)
        self.assertEqual(get.call_count, 3)
        self.assertEqual([call.args[0] for call in self.sleep.call_args_list], [1, 2])

    def test_ssl_and_invalid_url_errors_are_not_retried(self):
        for error in (
            requests.exceptions.SSLError("certificate"),
            requests.exceptions.InvalidURL("invalid"),
        ):
            with self.subTest(error=error):
                with (
                    patch(
                        "sci_dataset_list.download.requests.get", side_effect=error
                    ) as get,
                    self.assertRaises(type(error)),
                ):
                    download_rss()
                get.assert_called_once()

    def test_supplied_session_is_reused_and_left_open(self):
        session = MagicMock()
        session.get.return_value = self.response()
        with patch("sci_dataset_list.download.requests.get") as get:
            download_rss(session=session)
            download_dataset_page(20804, session=session)
        get.assert_not_called()
        self.assertEqual(session.get.call_count, 2)
        session.close.assert_not_called()
        session.__enter__.assert_not_called()


if __name__ == "__main__":
    unittest.main()
