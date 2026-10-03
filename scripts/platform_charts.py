"""Download reviewed, checksum-pinned platform Helm charts."""
import hashlib
import json
from pathlib import Path
import urllib.request


def download(directory):
    specifications = json.loads(Path("deploy/platform-charts.json").read_text())
    paths = {}
    for name, spec in specifications.items():
        with urllib.request.urlopen(urllib.request.Request(spec["url"], headers={"User-Agent": "Mozilla/5.0"}), timeout=120) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != spec["sha256"]:
            raise ValueError("Platform chart checksum mismatch: " + name)
        path = Path(directory) / (name + ".tgz")
        path.write_bytes(data)
        paths[name] = path
    return paths
