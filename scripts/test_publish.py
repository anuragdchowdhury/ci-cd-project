"""Regression checks for GHCR bootstrap, tag preservation and denied access."""
import io
import json
import unittest
import urllib.error
from unittest.mock import patch

import publish


class RegistryPreflightTest(unittest.TestCase):
    def check(self, outcome):
        response = io.BytesIO(json.dumps({"token": "test-bearer"}).encode())
        with patch("publish.urllib.request.urlopen", side_effect=[response, outcome]) as opener:
            publish.ensure_tag_absent("ghcr.io/example/notekeeper-backend", "a" * 40, "example", "test-credential")
            request = opener.call_args.args[0]
            self.assertEqual(request.get_method(), "HEAD")
            self.assertEqual(request.get_header("Authorization"), "Bearer test-bearer")

    def test_missing_manifest_allows_first_publication(self):
        self.check(urllib.error.HTTPError("https://ghcr.io", 404, "missing", {}, None))

    def test_existing_manifest_is_preserved(self):
        with self.assertRaisesRegex(RuntimeError, "already exists"):
            self.check(io.BytesIO(b""))

    def test_denied_manifest_is_not_treated_as_missing(self):
        for code in (401, 403):
            with self.subTest(code=code), self.assertRaisesRegex(RuntimeError, f"HTTP {code}"):
                self.check(urllib.error.HTTPError("https://ghcr.io", code, "denied", {}, None))

    def test_network_failure_refuses_publication(self):
        with self.assertRaisesRegex(RuntimeError, "refusing publication"):
            self.check(urllib.error.URLError("offline"))

    def test_token_failure_does_not_attempt_manifest_check(self):
        error = urllib.error.HTTPError("https://ghcr.io", 403, "denied", {}, None)
        with patch("publish.urllib.request.urlopen", side_effect=error) as opener:
            with self.assertRaisesRegex(RuntimeError, "authentication failed"):
                publish.ensure_tag_absent("ghcr.io/example/notekeeper-backend", "a" * 40, "example", "test-credential")
            self.assertEqual(opener.call_count, 1)


if __name__ == "__main__":
    unittest.main()
