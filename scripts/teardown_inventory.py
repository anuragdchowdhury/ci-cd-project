"""Read-only inventory for the future NoteKeeper teardown; never deletes resources."""
import json
import subprocess

SUBSCRIPTION = "b4207b90-6a00-470a-aa95-b154c688bb74"
GROUPS = {"rg-nk-bootstrap-ci", "rg-nk-registry-ci", "rg-nk-nonprod", "rg-nk-nonprod-nodes"}
AKS = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-nk-nonprod/providers/Microsoft.ContainerService/managedClusters/aks-notekeeper-nonprod"
AMW = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-nk-nonprod/providers/Microsoft.Monitor/accounts/amw-nk-dev-261e097d"


def az(*args):
    return json.loads(subprocess.check_output(
        ["az", *args, "--subscription", SUBSCRIPTION, "--output", "json"], text=True))


def main():
    groups = az("group", "list")
    owners = {AKS.lower(), AMW.lower()}
    selected = [g for g in groups if g["name"] in GROUPS
                or (g.get("managedBy") or "").lower() in owners]
    result = {"subscription": SUBSCRIPTION, "read_only": True, "groups": []}
    for group in selected:
        resources = az("resource", "list", "--resource-group", group["name"])
        result["groups"].append({
            "name": group["name"], "id": group["id"],
            "managedBy": group.get("managedBy"), "tags": group.get("tags"),
            "resources": [{k: r.get(k) for k in ("id", "name", "type", "tags")}
                          for r in resources],
        })
    result["review"] = (
        "Compare every resource with the four Terraform states before deleting a group. "
        "Tags and group membership alone do not prove ownership. Subscription-scoped IAM "
        "and soft-deleted resources are not enumerated here. Also inspect the Monitor "
        "workspace's managed resource group if its managedBy field is absent.")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
