"""Send nonsecret, validated deployment inputs to the single private-access VM."""
import base64
import json
import os
from pathlib import Path
import subprocess

from deployment_config import match, values

commit = match(r"[0-9a-f]{40}", os.environ["GITHUB_SHA"])
platform = json.loads(os.environ["DEV_PLATFORM_JSON"])
release = json.loads(Path("release.json").read_text())
observability = json.loads(os.environ["DEV_OBSERVABILITY_JSON"]) if os.environ.get("DEV_OBSERVABILITY_JSON", "").strip() else None
helm_values = values(platform, release, os.environ["ACR_LOGIN_SERVER"], observability)
resource_group = match(r"[a-zA-Z0-9_.()-]+", os.environ["DEPLOY_VM_RESOURCE_GROUP"])
vm = match(r"[a-zA-Z0-9-]+", os.environ["DEPLOY_VM_NAME"])
payload = base64.b64encode(json.dumps({"platform": platform, "values": helm_values}).encode()).decode()
# No shell interpolation from free-form workflow inputs. The only interpolated
# strings are validated full SHAs and generated base64 JSON.
script = f'''#!/usr/bin/env bash
set -euo pipefail
exec 9>/var/lock/notekeeper-deploy.lock
flock -n 9 || {{ echo "Another deployment is active"; exit 1; }}
cloud-init status --wait >/dev/null
work=$(mktemp -d /tmp/notekeeper.XXXXXX)
trap 'rm -rf "$work"' EXIT
cd "$work"
git init --quiet
git remote add origin https://github.com/anuragdchowdhury/ci-cd-project.git
git fetch --quiet --depth=1 origin {commit}
git checkout --quiet --detach FETCH_HEAD
test "$(git rev-parse HEAD)" = '{commit}'
python3 - <<'PAYLOAD'
import base64,json
from pathlib import Path
payload=json.loads(base64.b64decode('{payload}'))
Path('platform.json').write_text(json.dumps(payload['platform']))
Path('values.json').write_text(json.dumps(payload['values']))
PAYLOAD
python3 scripts/deploy_vm.py --platform platform.json --values values.json
'''
Path("run-command.sh").write_text(script)
result = json.loads(subprocess.check_output([
    "az", "vm", "run-command", "invoke", "--resource-group", resource_group, "--name", vm,
    "--command-id", "RunShellScript", "--scripts", "@run-command.sh", "--output", "json"
], text=True))
messages = "\n".join(item.get("message", "") for item in result.get("value", []))
print(messages)
# ARM operation success alone does not prove shell success; demand the sentinel
# printed only after rollout, Key Vault mount, image and CRUD checks all pass.
if "NOTEKEEPER_DEPLOY_OK " + release["commit"] not in messages:
    raise SystemExit("Deployment did not produce its verified success marker")
