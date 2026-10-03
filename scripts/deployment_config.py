"""Validate a CI digest pair and generate nonsecret Dev Helm values."""
import argparse
import json
from pathlib import Path
import re

SOURCE = "https://github.com/anuragdchowdhury/ci-cd-project"
UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"


def match(pattern, value):
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise ValueError("Invalid deployment identifier or image reference")
    return value


def validate_release(release, commit, registry, run_id=None):
    match(r"[0-9a-f]{40}", commit)
    match(r"[a-z0-9]{5,50}\.azurecr\.io", registry)
    if release.get("commit") != commit or release.get("source") != SOURCE or release.get("platform") != "linux/amd64":
        raise ValueError("Release source, commit or platform mismatch")
    if run_id is not None and str(release.get("workflow_run_id")) != str(run_id):
        raise ValueError("Release workflow run mismatch")
    if set(release.get("images", {})) != {"backend", "frontend"}:
        raise ValueError("An exact backend/frontend digest pair is required")
    for component, image in release["images"].items():
        repository = registry + "/notekeeper-" + component
        if image.get("tag") != repository + ":" + commit:
            raise ValueError("Release tag mismatch")
        match(re.escape(repository) + r"@sha256:[0-9a-f]{64}", image.get("reference"))
    return release


def values(platform, release, registry):
    validate_release(release, release["commit"], registry)
    dev = platform["environments"]["dev"]
    if dev["namespace"] != "notekeeper-dev" or dev["database"] != "notekeeper_dev":
        raise ValueError("Only the Dev lab is active")
    return {
        "bootstrapOnly": False, "releaseSha": release["commit"],
        "backendImage": release["images"]["backend"]["reference"],
        "frontendImage": release["images"]["frontend"]["reference"],
        "tenantId": match(UUID, platform["tenant_id"]),
        "runtimeClientId": match(UUID, dev["runtime_client_id"]),
        "migrationClientId": match(UUID, dev["migration_client_id"]),
        "runtimeRole": match(r"[a-z0-9-]{1,63}", dev["runtime_identity_name"]),
        "migrationRole": match(r"[a-z0-9-]{1,63}", dev["migration_identity_name"]),
        "postgresFqdn": match(r"[a-z0-9-]+\.postgres\.database\.azure\.com", platform["postgres_fqdn"]),
        "database": dev["database"], "vaultName": match(r"[a-z0-9-]+", dev["vault_name"]),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", required=True, type=Path)
    parser.add_argument("--release", required=True, type=Path)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = values(json.loads(args.platform.read_text()), json.loads(args.release.read_text()), args.registry)
    args.output.write_text(json.dumps(output, indent=2) + "\n")
    print("Generated nonsecret Helm values pinned to both CI image digests.")


if __name__ == "__main__":
    main()
