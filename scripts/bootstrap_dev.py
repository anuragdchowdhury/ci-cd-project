"""One-time operator setup: Entra SQL roles, namespace, Key Vault and migrations."""
import argparse
import json
import os
from pathlib import Path
import subprocess

from deployment_config import UUID, match


def run(*args, **kwargs):
    return subprocess.run(list(args), check=True, **kwargs)


def literal(value):
    return "'" + value.replace("'", "''") + "'"


def identifier(value):
    return '"' + value.replace('"', '""') + '"'


def normalize_principal(row):
    principal = {k.lower(): v for k, v in row.items()}
    # Azure PostgreSQL returns rolname on some servers; documentation also
    # describes rolename. Require a consistent name and the security fields.
    if "rolname" in principal:
        if "rolename" in principal and principal["rolename"] != principal["rolname"]:
            raise ValueError("Conflicting SQL principal role names")
        principal["rolename"] = principal["rolname"]
    if not {"rolename", "objectid", "isadmin"}.issubset(principal):
        raise ValueError("SQL principal response lacks required identity fields")
    return principal


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", required=True, type=Path)
    parser.add_argument("--values", required=True, type=Path)
    args = parser.parse_args()
    platform = json.loads(args.platform.read_text())
    dev = platform["environments"]["dev"]
    if dev["namespace"] != "notekeeper-dev" or dev["database"] != "notekeeper_dev":
        raise ValueError("Only Dev is supported")
    account = json.loads(subprocess.check_output(["az", "account", "show", "-o", "json"], text=True))
    if account["id"] != platform["subscription_id"] or account["tenantId"] != platform["tenant_id"]:
        raise ValueError("Wrong subscription or tenant")

    def sql(database, statement):
        # Token is in the child environment only, never argv, files or logs.
        token = subprocess.check_output(["az", "account", "get-access-token", "--resource",
            "https://ossrdbms-aad.database.windows.net", "--query", "accessToken", "-o", "tsv"], text=True).strip()
        env = dict(os.environ, PGPASSWORD=token, PGSSLMODE="verify-full",
            PGSSLROOTCERT="/etc/ssl/certs/ca-certificates.crt", PGCONNECT_TIMEOUT="15")
        return subprocess.check_output(["psql", "-X", "-v", "ON_ERROR_STOP=1", "-At",
            "-h", platform["postgres_fqdn"], "-U", platform["postgres_admin"], "-d", database],
            input=statement, text=True, env=env)

    registered = [normalize_principal(json.loads(line)) for line in sql("postgres",
        "SELECT row_to_json(p) FROM pg_catalog.pgaadauth_list_principals(false) p;").splitlines() if line]
    for prefix in ("runtime", "migration"):
        role = match(r"[a-z0-9-]{1,63}", dev[prefix + "_identity_name"])
        oid = match(UUID, dev[prefix + "_principal_id"])
        existing = [row for row in registered if row["rolename"] == role]
        if existing:
            if len(existing) != 1 or existing[0]["objectid"] != oid or existing[0]["isadmin"] != 0:
                raise ValueError("Existing SQL role is bound to a different principal or is an admin")
        else:
            sql("postgres", "SELECT pg_catalog.pgaadauth_create_principal_with_oid(" +
                literal(role) + "," + literal(oid) + ",'service',false,false);")
    runtime = identifier(dev["runtime_identity_name"])
    migration = identifier(dev["migration_identity_name"])
    sql(dev["database"], f'''BEGIN;
REVOKE ALL ON DATABASE notekeeper_dev FROM PUBLIC;
GRANT CONNECT ON DATABASE notekeeper_dev TO {runtime}, {migration};
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO {runtime};
GRANT USAGE, CREATE ON SCHEMA public TO {migration};
COMMIT;''')

    run("az", "aks", "get-credentials", "-g", platform["resource_group"], "-n", platform["cluster_name"], "--overwrite-existing")
    run("kubelogin", "convert-kubeconfig", "-l", "azurecli")
    namespace = {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": dev["namespace"],
        "labels": {"pod-security.kubernetes.io/enforce": "restricted", "pod-security.kubernetes.io/enforce-version": "v1.36"}}}
    sa = {"apiVersion": "v1", "kind": "ServiceAccount", "metadata": {"name": "notekeeper-migration", "namespace": dev["namespace"],
        "annotations": {"azure.workload.identity/client-id": dev["migration_client_id"]}}, "automountServiceAccountToken": False}
    run("kubectl", "apply", "-f", "-", input=json.dumps({"apiVersion": "v1", "kind": "List", "items": [namespace, sa]}), text=True)
    # Explicitly nonsecret lab content, to prove private CSI access without exposing credentials.
    run("az", "keyvault", "secret", "set", "--vault-name", dev["vault_name"], "--name", "lab-message",
        "--value", "NoteKeeper private Key Vault lab", "--output", "none")
    run("python3", "scripts/deploy_vm.py", "--platform", str(args.platform), "--values", str(args.values), "--bootstrap-only", "--operator")
    sql(dev["database"], f'''BEGIN;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.notes TO {runtime};
REVOKE ALL ON TABLE public.flyway_schema_history FROM {runtime};
COMMIT;''')
    role = literal(dev["runtime_identity_name"])
    checks = sql(dev["database"], f'''SELECT
has_schema_privilege({role}, 'public', 'CREATE'),
has_table_privilege({role}, 'public.notes', 'SELECT'),
has_table_privilege({role}, 'public.notes', 'INSERT'),
has_table_privilege({role}, 'public.notes', 'UPDATE'),
has_table_privilege({role}, 'public.notes', 'DELETE'),
has_table_privilege({role}, 'public.flyway_schema_history', 'SELECT');''').strip()
    if checks != "f|t|t|t|t|f":
        raise ValueError("Runtime SQL privilege check failed: " + checks)
    print("NOTEKEEPER_DB_READY: runtime CRUD only; migration owns schema objects. Run Deploy Dev next.")


if __name__ == "__main__":
    main()
