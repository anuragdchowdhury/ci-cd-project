"""Write ignored platform inputs from nonsecret identifiers, never state or tokens."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys


def azure(*args):
    return json.loads(subprocess.check_output(["az", *args, "--output", "json"], text=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kubernetes-version", required=True)
    parser.add_argument("--budget-amount", required=True, type=float)
    parser.add_argument("--alert-email", required=True)
    args = parser.parse_args()
    if args.budget_amount <= 0:
        parser.error("budget amount must be positive, in subscription billing currency")
    config = json.load(sys.stdin)
    account = azure("account", "show")
    if account["id"] != config["subscription_id"] or account["tenantId"] != config["tenant_id"]:
        raise SystemExit("Select the bootstrap subscription and tenant in Azure CLI first.")
    user = azure("ad", "signed-in-user", "show")
    generated = Path(__file__).resolve().parents[1] / "infra" / ".generated"
    generated.mkdir(mode=0o700, exist_ok=True)
    values = {key: config[key] for key in ["subscription_id", "tenant_id", "location", "name_prefix"]}
    base = f'/subscriptions/{config["subscription_id"]}/resourceGroups/'
    values.update({
        "registry_resource_id": base + config["registry_resource_group"] + "/providers/Microsoft.ContainerRegistry/registries/" + config["registry_name"],
        "state_storage_account_id": base + config["bootstrap_resource_group"] + "/providers/Microsoft.Storage/storageAccounts/" + config["storage_account_name"],
        "operator_object_id": user["id"],
        "operator_login": user["userPrincipalName"],
        "kubernetes_version": args.kubernetes_version,
        "node_vm_size": "Standard_D4s_v4",
        "postgres_sku": "B_Standard_B1ms",
        "monthly_budget_amount": args.budget_amount,
        "alert_email": args.alert_email,
        "budget_start_date": datetime.now(timezone.utc).strftime("%Y-%m-01T00:00:00Z"),
    })
    for boundary in ["nonprod"]:
        path = generated / f"{boundary}.auto.tfvars.json"
        # Do not silently change the date on an existing budget across month boundaries.
        if path.exists():
            previous = json.loads(path.read_text())
            values["budget_start_date"] = previous["budget_start_date"]
        path.write_text(json.dumps(values, indent=2) + "\n")
        path.chmod(0o600)
    print("Generated ignored Dev-only nonprod inputs. Review them before planning; nothing was provisioned.")


if __name__ == "__main__":
    main()
