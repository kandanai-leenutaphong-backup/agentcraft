import unittest

from data_collection.document import inspect_document


class DocumentTests(unittest.TestCase):
    def test_small_static_page_does_not_require_browser(self):
        document = inspect_document(b"<title>Example</title><main>Hello world</main>")
        self.assertFalse(document.needs_browser)
        self.assertEqual(document.title, "Example")
        self.assertEqual(document.text, "Hello world")

    def test_script_shell_requires_browser(self):
        document = inspect_document(b'<div id="root"></div><script src="/app.js"></script>')
        self.assertTrue(document.needs_browser)

    def test_selector_is_an_explicit_readiness_contract(self):
        document = inspect_document("<main>Server-side text</main>", wait_selector="#result")
        self.assertTrue(document.needs_browser)
        ready = inspect_document('<main id="result">Done</main>', wait_selector="#result")
        self.assertFalse(ready.needs_browser)

    def test_legacy_html_encoding(self):
        document = inspect_document(b'<meta charset="windows-1252"><p>caf\xe9</p>')
        self.assertEqual(document.text, "caf\u00e9")

    def test_challenge_is_not_content(self):
        document = inspect_document("<title>Just a moment...</title><p>Verifying your browser</p>")
        self.assertTrue(document.access_barrier)

    def test_article_about_access_denied_is_content(self):
        document = inspect_document("<title>HTTP guide</title><main>Access denied explained</main>")
        self.assertFalse(document.access_barrier)


if __name__ == "__main__":
    unittest.main()