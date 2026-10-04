"""Generate edge inputs only after Kubernetes has provisioned its internal LB."""
import argparse
import json
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--platform", required=True, type=Path)
parser.add_argument("--observability", required=True, type=Path)
args = parser.parse_args()
platform = json.loads(args.platform.read_text())
obs = json.loads(args.observability.read_text())
access=json.loads((Path(__file__).resolve().parents[1]/"infra/.generated/access.auto.tfvars.json").read_text())
lbs=json.loads(subprocess.check_output(["az","network","lb","list","--resource-group","rg-nk-nonprod-nodes","-o","json"],text=True))
frontends=[config for lb in lbs for config in lb.get("frontendIPConfigurations",[]) if config.get("privateIPAddress")=="10.20.19.10"]
if len(frontends)!=1:
    raise SystemExit("Expected one internal ingress LB frontend at 10.20.19.10; install Traefik first.")
values={"subscription_id":platform["subscription_id"],"tenant_id":platform["tenant_id"],"resource_group":platform["resource_group"],
 "operator_ipv4":access["operator_ipv4"],"location":"centralindia","ingress_subnet_id":platform["ingress_subnet_id"],"load_balancer_frontend_id":frontends[0]["id"],
 "dev_dns_zone":obs["dev_dns_zone"],"law_id":obs["law_id"],"action_group_id":obs["action_group_id"]}
path=Path(__file__).resolve().parents[1]/"infra/.generated/edge.auto.tfvars.json"
path.write_text(json.dumps(values,indent=2)+"\n")
print("Generated ignored edge inputs from actual internal LB configuration.")
