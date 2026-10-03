"""Generate ignored backend files from NONSECRET bootstrap configuration only.

Usage: terraform -chdir=infra/bootstrap output -json configuration |
       python3 scripts/configure_azure_backend.py
Never pipe `terraform state pull` here or print/upload a complete state file.
"""
import json
from pathlib import Path
import sys


def main():
    config = json.load(sys.stdin)
    root = Path(__file__).resolve().parents[1]
    generated = root / "infra" / ".generated"
    generated.mkdir(mode=0o700, exist_ok=True)
    for stack in ("bootstrap", "registry", "nonprod", "edge"):
        values = {
            "storage_account_name": config["storage_account_name"],
            "container_name": "tfstate-nonprod" if stack == "edge" else "tfstate-" + stack,
            "key": "edge.tfstate" if stack == "edge" else "terraform.tfstate",
            "tenant_id": config["tenant_id"],
            "use_azuread_auth": True,
        }
        # OIDC/CLI authentication is selected via environment, not fixed in HCL.
        content = "\n".join(f"{key} = {json.dumps(value)}" for key, value in values.items()) + "\n"
        (generated / f"{stack}.backend.hcl").write_text(content)
    (generated / "registry.auto.tfvars.json").write_text(json.dumps({
        key: config[key] for key in (
            "subscription_id", "tenant_id", "location", "registry_resource_group", "registry_name"
        )
    }, indent=2) + "\n")
    backend = root / "infra" / "bootstrap" / "backend.local.tf"
    backend.write_text('terraform {\n  backend "azurerm" {}\n}\n')
    print("Generated backend configuration in infra/.generated and enabled the bootstrap backend.")
    print("First-time bootstrap: follow Step 2 to migrate state. An already-migrated backend needs no new migration.")
    print("GitHub variables (identifiers, not credentials):")
    print("AZURE_SUBSCRIPTION_ID=" + config["subscription_id"])
    print("AZURE_TENANT_ID=" + config["tenant_id"])
    print("AZURE_BOOTSTRAP_RESOURCE_GROUP=" + config["bootstrap_resource_group"])
    print("AZURE_REGISTRY_RESOURCE_GROUP=" + config["registry_resource_group"])
    for key, identity in config["github_identities"].items():
        print(f"AZURE_{key.upper()}_CLIENT_ID={identity['client_id']} (environment: {identity['environment']})")


if __name__ == "__main__":
    main()
