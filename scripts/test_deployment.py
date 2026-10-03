"""Promotion guards must reject mixed, foreign or untrusted release metadata."""
import copy
import unittest

from deployment_config import SOURCE, validate_release, values


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

    def test_telemetry_uses_separate_browser_and_backend_routes(self):
        platform={"tenant_id":"133815cf-acdc-4089-a1e7-fce0de2fe1b4","postgres_fqdn":"pg-lab.postgres.database.azure.com","environments":{"dev":{
            "namespace":"notekeeper-dev","database":"notekeeper_dev","runtime_client_id":"cdcf7697-e3df-44f3-8147-63f2c5981906",
            "migration_client_id":"59e16ef2-6589-47c9-9806-4e695baaca83","runtime_identity_name":"id-nk-dev-api","migration_identity_name":"id-nk-dev-migration","vault_name":"kv-nk-dev"}}}
        obs={"dev_dns_zone":"dev.example.com","backend_connection_string":"InstrumentationKey=backend;IngestionEndpoint=https://example.com/",
             "browser_connection_string":"InstrumentationKey=browser;IngestionEndpoint=https://example.com/"}
        configured=values(platform,self.release,self.registry,obs)
        self.assertNotEqual(configured['applicationInsightsConnectionString'],configured['browserInsightsConnectionString'])
        self.assertTrue(configured['ingressEnabled'])
        self.assertEqual(configured['originHost'],'origin.dev.example.com')
        private=values(platform,self.release,self.registry)
        self.assertNotIn('ingressEnabled',private)
        self.assertEqual(private['backendImage'],configured['backendImage'])
        obs['dev_dns_zone']='example.com'
        with self.assertRaises(ValueError):values(platform,self.release,self.registry,obs)

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
