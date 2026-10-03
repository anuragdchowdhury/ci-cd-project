#!/usr/bin/env bash
set -euo pipefail
# Ubuntu 24.04, amd64. Azure CLI's signed Microsoft package repository.
curl --fail --silent --show-error https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > /etc/apt/keyrings/microsoft.gpg
chmod 644 /etc/apt/keyrings/microsoft.gpg
printf '%s\n' 'deb [arch=amd64 signed-by=/etc/apt/keyrings/microsoft.gpg] https://packages.microsoft.com/repos/azure-cli/ noble main' > /etc/apt/sources.list.d/azure-cli.list
apt-get update
apt-get install -y azure-cli
# Explicit client versions, with official release checksums.
python3 - <<'PYTOOLS'
import hashlib
import io
from pathlib import Path
import tarfile
import urllib.request
import zipfile

def download(url):
    with urllib.request.urlopen(url, timeout=120) as response:
        return response.read()

def verified(url, checksum_url):
    data = download(url)
    expected = download(checksum_url).decode().split()[0]
    if hashlib.sha256(data).hexdigest() != expected:
        raise SystemExit("Tool checksum mismatch")
    return data

url = "https://dl.k8s.io/release/v1.36.4/bin/linux/amd64/kubectl"
Path("/usr/local/bin/kubectl").write_bytes(verified(url, url + ".sha256"))
url = "https://get.helm.sh/helm-v3.21.4-linux-amd64.tar.gz"
with tarfile.open(fileobj=io.BytesIO(verified(url, url + ".sha256sum")), mode="r:gz") as archive:
    Path("/usr/local/bin/helm").write_bytes(archive.extractfile("linux-amd64/helm").read())
url = "https://github.com/Azure/kubelogin/releases/download/v0.2.18/kubelogin-linux-amd64.zip"
with zipfile.ZipFile(io.BytesIO(verified(url, url + ".sha256"))) as archive:
    Path("/usr/local/bin/kubelogin").write_bytes(archive.read("bin/linux_amd64/kubelogin"))
for tool in ("kubectl", "helm", "kubelogin"):
    Path("/usr/local/bin", tool).chmod(0o755)
PYTOOLS
printf 'NOTEKEEPER_TOOLS_READY\n'
