"""Generate final-lab inputs, preserving existing platform/access configuration."""
import argparse
import json
from pathlib import Path
import re

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--dev-zone", required=True, help="Dedicated child zone: dev.your-domain.com")
parser.add_argument("--drill-logs", action="store_true")
parser.add_argument("--archive", action=argparse.BooleanOptionalAction, default=None)
args = parser.parse_args()
if not re.fullmatch(r"dev\.[a-z0-9.-]+\.[a-z]{2,}", args.dev_zone):
    parser.error("Supply a dedicated Dev child DNS zone")
root = Path(__file__).resolve().parents[1]
path = root / "infra/.generated/lab.auto.tfvars.json"
if not (root / "infra/.generated/access.auto.tfvars.json").exists():
    parser.error("Existing access inputs are required")
previous=json.loads(path.read_text()) if path.exists() else {}
archive=previous.get("archive_enabled",False) if args.archive is None else args.archive
path.write_text(json.dumps({"lab_enabled": True, "dev_dns_zone": args.dev_zone, "logs_drill_mode": args.drill_logs, "archive_enabled": archive}, indent=2)+"\n")
path.chmod(0o600)
print("Generated lab inputs; review a saved Terraform plan before applying.")
