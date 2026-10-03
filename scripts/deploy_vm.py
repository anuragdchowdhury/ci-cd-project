"""Deploy a verified digest pair from a VNet VM using its Dev managed identity."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.request


def run(*args, **kwargs):
    return subprocess.run(list(args), check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--values", required=True, type=Path)
    parser.add_argument("--platform", required=True, type=Path)
    parser.add_argument("--bootstrap-only", action="store_true")
    parser.add_argument("--operator", action="store_true", help="Use temporary operator login for initial bootstrap")
    args = parser.parse_args()
    platform = json.loads(args.platform.read_text())
    values = json.loads(args.values.read_text())
    namespace = platform["environments"]["dev"]["namespace"]
    if namespace != "notekeeper-dev":
        raise ValueError("Only Dev is supported")
    if args.bootstrap_only and not args.operator:
        raise ValueError("Initial bootstrap requires the operator")
    # Azure CLI and kubeconfig always live in a disposable directory.
    with tempfile.TemporaryDirectory(prefix="nk-deploy-") as directory:
        os.environ["KUBECONFIG"] = directory + "/kubeconfig"
        if not args.operator:
            os.environ["AZURE_CONFIG_DIR"] = directory + "/azure"
            run("az", "login", "--identity", "--client-id", platform["environments"]["dev"]["deployer_client_id"], "--output", "none")
            run("az", "account", "set", "--subscription", platform["subscription_id"])
        run("az", "aks", "get-credentials", "--resource-group", platform["resource_group"],
            "--name", platform["cluster_name"], "--file", os.environ["KUBECONFIG"], "--overwrite-existing")
        run("kubelogin", "convert-kubeconfig", "-l", "azurecli")
        values["bootstrapOnly"] = args.bootstrap_only
        generated = Path(directory) / "values.json"
        generated.write_text(json.dumps(values))
        try:
            run("helm", "upgrade", "--install", "notekeeper", "charts/notekeeper", "--namespace", namespace,
                "--values", str(generated), "--atomic", "--wait", "--timeout", "8m", "--history-max", "5")
            if not args.bootstrap_only:
                run("kubectl", "-n", namespace, "rollout", "status", "deployment/notekeeper-api", "--timeout=120s")
                run("kubectl", "-n", namespace, "rollout", "status", "deployment/notekeeper-web", "--timeout=120s")
                run("kubectl", "-n", namespace, "exec", "deployment/notekeeper-api", "--", "test", "-s", "/mnt/secrets-store/lab-message")
                # Verify live pod specs use the exact promoted digests; no pull secret.
                pods = json.loads(subprocess.check_output(["kubectl", "-n", namespace, "get", "pods", "-o", "json"], text=True))
                checked = set()
                for pod in pods["items"]:
                    app = pod["metadata"].get("labels", {}).get("app.kubernetes.io/name")
                    if app not in {"notekeeper-api", "notekeeper-web"} or pod["metadata"].get("deletionTimestamp"):
                        continue
                    spec = pod["spec"]
                    expected = values["backendImage" if app == "notekeeper-api" else "frontendImage"]
                    if spec.get("imagePullSecrets") or spec["containers"][0]["image"] != expected:
                        raise ValueError("Live digest mismatch or unexpected image pull secret")
                    checked.add(app)
                if checked != {"notekeeper-api", "notekeeper-web"}:
                    raise ValueError("Both workloads must be present")
                with open(Path(directory) / "port-forward.log", "w") as output:
                    forward = subprocess.Popen(["kubectl", "-n", namespace, "port-forward", "service/frontend", "8080:8080", "--address", "127.0.0.1"], stdout=output, stderr=output)
                    try:
                        # smoke.py waits for the forwarded endpoint to become ready.
                        run("python3", "scripts/smoke.py")
                    finally:
                        forward.terminate()
                        forward.wait(timeout=15)
            print("NOTEKEEPER_BOOTSTRAP_OK" if args.bootstrap_only else "NOTEKEEPER_DEPLOY_OK " + values["releaseSha"], flush=True)
        except Exception:
            # Events describe image, identity and mount errors without dumping secrets.
            subprocess.run(["kubectl", "-n", namespace, "get", "pods"], check=False)
            subprocess.run(["kubectl", "-n", namespace, "get", "events", "--sort-by=.lastTimestamp"], check=False)
            raise


if __name__ == "__main__":
    main()
