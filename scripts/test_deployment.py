"""Promotion guards must reject mixed, foreign or untrusted release metadata."""
import copy
import unittest

from deployment_config import SOURCE, validate_release


class PromotionTests(unittest.TestCase):
    def setUp(self):
        self.commit = "a" * 40
        self.registry = "acrnk81c108fc.azurecr.io"
        self.release = {"commit": self.commit, "source": SOURCE, "platform": "linux/amd64", "workflow_run_id": "123",
            "images": {component: {"tag": f"{self.registry}/notekeeper-{component}:{self.commit}",
                "reference": f"{self.registry}/notekeeper-{component}@sha256:" + "b" * 64} for component in ("backend", "frontend")}}

    def validate(self, release):
        return validate_release(release, self.commit, self.registry, 123)

    def test_accepts_paired_ci_release(self):
        self.validate(self.release)

    def test_rejects_wrong_ci_run(self):
        self.release["workflow_run_id"] = "124"
        with self.assertRaises(ValueError):
            self.validate(self.release)

    def test_rejects_mixed_tags(self):
        self.release["images"]["frontend"]["tag"] = self.release["images"]["frontend"]["tag"].replace(self.commit, "c" * 40)
        with self.assertRaises(ValueError):
            self.validate(self.release)

    def test_rejects_tag_instead_of_digest(self):
        self.release["images"]["backend"]["reference"] = self.release["images"]["backend"]["tag"]
        with self.assertRaises(ValueError):
            self.validate(self.release)

    def test_rejects_foreign_registry(self):
        self.release["images"]["backend"]["reference"] = "evil.example/notekeeper-backend@sha256:" + "b" * 64
        with self.assertRaises(ValueError):
            self.validate(self.release)

    def test_rejects_foreign_source(self):
        self.release["source"] = "https://github.com/other/repo"
        with self.assertRaises(ValueError):
            self.validate(self.release)

    def test_rejects_extra_component(self):
        self.release["images"]["extra"] = self.release["images"]["backend"]
        with self.assertRaises(ValueError):
            self.validate(self.release)


if __name__ == "__main__":
    unittest.main()
