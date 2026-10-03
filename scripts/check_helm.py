"""Lint/render both bootstrap and runtime charts with a verified Helm client."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import urllib.request

with tempfile.TemporaryDirectory() as directory:
    url = "https://get.helm.sh/helm-v3.21.4-linux-amd64.tar.gz"
    with urllib.request.urlopen(url, timeout=120) as response:
        archive = response.read()
    with urllib.request.urlopen(url + ".sha256sum", timeout=60) as response:
        expected = response.read().decode().split()[0]
    if hashlib.sha256(archive).hexdigest() != expected:
        raise ValueError("Helm checksum mismatch")
    helm = Path(directory) / "helm"
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as files:
        helm.write_bytes(files.extractfile("linux-amd64/helm").read())
    helm.chmod(0o755)
    values = {"releaseSha": "a" * 40, "backendImage": "acrnk81c108fc.azurecr.io/notekeeper-backend@sha256:" + "b" * 64,
        "frontendImage": "acrnk81c108fc.azurecr.io/notekeeper-frontend@sha256:" + "c" * 64,
        "tenantId": "133815cf-acdc-4089-a1e7-fce0de2fe1b4", "runtimeClientId": "cdcf7697-e3df-44f3-8147-63f2c5981906",
        "migrationClientId": "59e16ef2-6589-47c9-9806-4e695baaca83", "runtimeRole": "id-nk-dev-api", "migrationRole": "id-nk-dev-migration",
        "postgresFqdn": "pg-nk-nonprod-261e097d.postgres.database.azure.com", "database": "notekeeper_dev", "vaultName": "kv-nk-dev-261e097d", "ingressEnabled": True, "originHost": "origin.dev.example.com"}
    config = Path(directory) / "values.json"
    config.write_text(json.dumps(values))
    for bootstrap in ("true", "false"):
        arguments = ["charts/notekeeper", "--values", str(config), "--set", "bootstrapOnly=" + bootstrap]
        subprocess.run([str(helm), "lint", *arguments, "--strict"], check=True)
        rendered = subprocess.check_output([str(helm), "template", "notekeeper", *arguments, "--namespace", "notekeeper-dev"], text=True)
        if "imagePullSecrets" in rendered or "DB_PASSWORD" in rendered or "NodePort" in rendered or "LoadBalancer" in rendered:
            raise ValueError("Unexpected application credential or public service")
        if ("kind: Deployment" in rendered) != (bootstrap == "false"):
            raise ValueError("Bootstrap must run migrations before starting the API")
    obs=Path(directory)/"observability.json"
    obs.write_text(json.dumps({"cert_manager_client_id":values["runtimeClientId"]}))
    subprocess.run(["python3","scripts/bootstrap_platform.py","--observability",str(obs),"--render-only","--helm",str(helm)],check=True)
print("PASS: bootstrap, runtime and platform Helm charts lint and render.")
