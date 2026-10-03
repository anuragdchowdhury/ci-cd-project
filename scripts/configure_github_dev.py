"""Set nonsecret Dev environment variables from actual Terraform outputs."""
import argparse
import json
from pathlib import Path
import subprocess

REPO = "anuragdchowdhury/ci-cd-project"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--platform", required=True, type=Path)
parser.add_argument("--vm", required=True, type=Path)
parser.add_argument("--registry", required=True)
args = parser.parse_args()
platform = json.loads(args.platform.read_text())
vm = json.loads(args.vm.read_text())
# Explicitly restrict this environment to the main branch.
payload = {"deployment_branch_policy": {"protected_branches": False, "custom_branch_policies": True}}
subprocess.run(["gh", "api", f"repos/{REPO}/environments/dev", "--method", "PUT", "--input", "-"],
               input=json.dumps(payload), text=True, check=True, stdout=subprocess.DEVNULL)
policies = json.loads(subprocess.check_output(["gh", "api", f"repos/{REPO}/environments/dev/deployment-branch-policies"], text=True))["branch_policies"]
if any(p["name"] != "main" or p.get("type", "branch") != "branch" for p in policies):
    raise SystemExit("Dev environment has other allowed branches/tags. Review and remove them in Settings first.")
if not policies:
    subprocess.run(["gh", "api", f"repos/{REPO}/environments/dev/deployment-branch-policies", "--method", "POST", "--input", "-"],
        input=json.dumps({"name": "main", "type": "branch"}), text=True, check=True, stdout=subprocess.DEVNULL)
variables = {
    "AZURE_SUBSCRIPTION_ID": platform["subscription_id"], "AZURE_TENANT_ID": platform["tenant_id"],
    "AZURE_DEV_DEPLOY_CLIENT_ID": platform["environments"]["dev"]["deployer_client_id"],
    "ACR_LOGIN_SERVER": args.registry, "DEV_PLATFORM_JSON": json.dumps(platform, separators=(",", ":")),
    "DEPLOY_VM_RESOURCE_GROUP": vm["resource_group"], "DEPLOY_VM_NAME": vm["name"],
}
for name, value in variables.items():
    subprocess.run(["gh", "variable", "set", name, "--repo", REPO, "--env", "dev"], input=value, text=True, check=True)
print("Configured Dev main-only branch policy and seven nonsecret variables. No client secret or PAT was stored.")
