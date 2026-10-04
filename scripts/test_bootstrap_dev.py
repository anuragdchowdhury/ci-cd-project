import unittest

from bootstrap_dev import normalize_principal


class PrincipalSchemaTests(unittest.TestCase):
    def test_actual_azure_schema_preserves_identity_and_admin_status(self):
        principal = normalize_principal({"rolname": "id-nk-dev-api",
                                         "objectid": "actual-object-id", "isadmin": 1})
        self.assertEqual(principal["rolename"], "id-nk-dev-api")
        self.assertEqual(principal["objectid"], "actual-object-id")
        self.assertEqual(principal["isadmin"], 1)

    def test_documented_schema_and_mixed_case(self):
        principal = normalize_principal({"roleName": "id-nk-dev-api",
                                         "objectId": "actual-object-id", "isAdmin": 0})
        self.assertEqual(principal["rolename"], "id-nk-dev-api")
        self.assertEqual(principal["objectid"], "actual-object-id")
        self.assertEqual(principal["isadmin"], 0)

    def test_incomplete_or_ambiguous_identity_fails_closed(self):
        for row in ({"rolname": "api"},
                    {"rolname": "api", "rolename": "other", "objectid": "id", "isadmin": 0}):
            with self.subTest(row=row), self.assertRaises(ValueError):
                normalize_principal(row)
