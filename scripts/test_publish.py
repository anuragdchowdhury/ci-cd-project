"""Security regressions for registry denials, tag preservation and candidate tampering."""
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import publish
import release_candidate
from ci_tools import sha256

COMMIT = "a" * 40
IMAGE_ID = "sha256:" + "b" * 64


class RegistryPreflightTest(unittest.TestCase):
    def setUp(self):
        self.registry = publish.Registry("example.azurecr.io", "fake-refresh-token")

    def manifest(self, outcome):
        with patch.object(self.registry, "request", side_effect=[
            (200, {}, b'{"access_token":"fake-scoped-token"}'), outcome,
        ]):
            return self.registry.manifest("notekeeper-backend", COMMIT)

    def test_missing_manifest_allows_first_publication(self):
        for code in ("MANIFEST_UNKNOWN", "NAME_UNKNOWN"):
            self.assertIsNone(self.manifest(publish.RegistryError(404, [code])))

    def test_auth_denial_and_unclassified_404_are_not_missing(self):
        for status in (401, 403, 404, 429, 500):
            with self.subTest(status=status), self.assertRaises(publish.RegistryError):
                self.manifest(publish.RegistryError(status))

    def test_network_failure_refuses_publication(self):
        with self.assertRaisesRegex(RuntimeError, "offline"):
            self.manifest(RuntimeError("offline"))

    def test_returned_manifest_digest_is_verified(self):
        body = json.dumps({"config": {"digest": IMAGE_ID}}).encode()
        digest = "sha256:" + hashlib.sha256(body).hexdigest()
        self.assertEqual(self.manifest((200, {"Docker-Content-Digest": digest}, body)),
                         {"digest": digest, "image_id": IMAGE_ID})
        with self.assertRaisesRegex(RuntimeError, "digest mismatch"):
            self.manifest((200, {"Docker-Content-Digest": "sha256:" + "0" * 64}, body))

    def test_scope_probe_requires_actual_authorization_denial(self):
        for outcome in (publish.RegistryError(401, ["UNAUTHORIZED"]), publish.RegistryError(403, ["DENIED"])):
            with patch.object(self.registry, "token", return_value="fake"), patch.object(self.registry, "request", side_effect=outcome):
                self.registry.prove_denied_write()
        for outcome in (publish.RegistryError(404, ["NAME_UNKNOWN"]), publish.RegistryError(503), RuntimeError("offline")):
            with patch.object(self.registry, "token", return_value="fake"), patch.object(self.registry, "request", side_effect=outcome), self.assertRaises(RuntimeError):
                self.registry.prove_denied_write()

    def test_unexpected_scope_write_is_cancelled_and_fails(self):
        with patch.object(self.registry, "token", return_value="fake"), patch.object(self.registry, "request", side_effect=[
            (202, {"Location": "/v2/notekeeper-scope-probe/blobs/uploads/test?_state=opaque"}, b""),
            (204, {}, b""),
        ]) as request, self.assertRaisesRegex(RuntimeError, "scope is too broad"):
            self.registry.prove_denied_write()
        self.assertEqual(request.call_args.args[1], "DELETE")

    def test_scope_probe_never_forwards_token_to_another_host(self):
        with patch.object(self.registry, "token", return_value="fake"), patch.object(self.registry, "request", return_value=(
            202, {"Location": "https://untrusted.invalid/upload"}, b""
        )) as request, self.assertRaisesRegex(RuntimeError, "safely cancel"):
            self.registry.prove_denied_write()
        self.assertEqual(request.call_count, 1)

    def test_same_image_can_resume_but_different_image_cannot_overwrite(self):
        publish.ensure_same_image(None, {"image_id": IMAGE_ID})
        publish.ensure_same_image({"image_id": IMAGE_ID}, {"image_id": IMAGE_ID})
        with self.assertRaisesRegex(RuntimeError, "different image"):
            publish.ensure_same_image({"image_id": "sha256:" + "c" * 64}, {"image_id": IMAGE_ID})


class CandidateTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.metadata = {"commit": COMMIT, "source": release_candidate.SOURCE, "build_inputs": release_candidate.INPUTS,
                         "workflow_run_id": "1234", "images": {"backend": {}, "frontend": {}}}
        self.write_metadata()

    def write_metadata(self):
        (self.folder / "candidate.json").write_text(json.dumps(self.metadata))
        self.candidate_digest = sha256(self.folder / "candidate.json")

    def verify(self):
        with patch.dict(os.environ, {"GITHUB_RUN_ID": "1234"}):
            return release_candidate.verify(self.folder, COMMIT, self.candidate_digest)

    def test_matching_metadata_is_accepted(self):
        self.assertEqual(self.verify(), self.metadata)

    def test_modified_candidate_is_rejected(self):
        (self.folder / "candidate.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            self.verify()

    def test_other_commit_run_or_missing_component_is_rejected(self):
        for key, value in (("commit", "d" * 40), ("workflow_run_id", "other"), ("images", {"backend": {}})):
            previous = self.metadata[key]
            self.metadata[key] = value
            self.write_metadata()
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.verify()
            self.metadata[key] = previous

    def test_unpinned_or_malformed_commit_is_rejected(self):
        for value in ("latest", "a" * 7, "a" * 40 + ";bad"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                release_candidate.valid_sha(value)


if __name__ == "__main__":
    unittest.main()
