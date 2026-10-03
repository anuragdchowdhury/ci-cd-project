"""Generate a separate ignored, nonsecret Terraform input file for private access."""
import argparse
import ipaddress
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--operator-ip", required=True)
parser.add_argument("--ssh-public-key", required=True, type=Path)
args = parser.parse_args()
ip = ipaddress.ip_address(args.operator_ip)
if ip.version != 4:
    parser.error("Supply an IPv4 address")
key = args.ssh_public_key.expanduser().read_text().strip()
if not key.startswith("ssh-ed25519 ") or "PRIVATE KEY" in key:
    parser.error("Supply an Ed25519 PUBLIC key")
path = Path(__file__).resolve().parents[1] / "infra/.generated/access.auto.tfvars.json"
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps({"deployment_vm_enabled": True, "operator_ipv4": str(ip), "ssh_public_key": key}, indent=2) + "\n")
path.chmod(0o600)
print("Generated ignored access inputs. Nothing was provisioned.")
