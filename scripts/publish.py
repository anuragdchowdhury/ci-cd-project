#!/usr/bin/env python3
"""Push tested images to ACR using the OIDC-authenticated Azure CLI session."""
import hashlib
import json
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from release_candidate import COMPONENTS, ROOT, SOURCE, inspect_image, valid_sha, verify

MANIFEST_TYPES = ", ".join(("application/vnd.oci.image.manifest.v1+json",
                            "application/vnd.docker.distribution.manifest.v2+json"))


class RegistryError(RuntimeError):
    def __init__(self, status, codes=()):
        self.status, self.codes = status, set(codes)
        super().__init__(f"ACR request failed (HTTP {status}); refusing publication")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Registry:
    def __init__(self, host, refresh_token):
        self.host, self.refresh_token = host, refresh_token
        self.opener = urllib.request.build_opener(NoRedirect())

    def request(self, path, method="GET", data=None, headers=None):
        request = urllib.request.Request(f"https://{self.host}{path}", data=data,
                                         method=method, headers=headers or {})
        try:
            with self.opener.open(request, timeout=60) as response:
                return response.status, response.headers, response.read()
        except urllib.error.HTTPError as error:
            try:
                payload = json.load(error)
                codes = [item["code"] for item in payload.get("errors", [])]
            except (ValueError, KeyError, TypeError):
                codes = []
            raise RegistryError(error.code, codes) from None
        except urllib.error.URLError:
            raise RuntimeError("Cannot contact ACR; refusing publication") from None

    def token(self, repository):
        form = urllib.parse.urlencode({"grant_type": "refresh_token", "service": self.host,
                                      "scope": f"repository:{repository}:pull,push",
                                      "refresh_token": self.refresh_token}).encode()
        _, _, body = self.request("/oauth2/token", "POST", form,
                                  {"Content-Type": "application/x-www-form-urlencoded"})
        payload = json.loads(body)
        token = payload.get("access_token") or payload.get("token")
        if not token:
            raise RuntimeError("ACR did not issue a scoped token")
        return token

    def manifest(self, repository, commit):
        token = self.token(repository)
        try:
            _, headers, body = self.request(f"/v2/{repository}/manifests/{commit}", headers={
                "Authorization": "Bearer " + token, "Accept": MANIFEST_TYPES,
            })
        except RegistryError as error:
            if error.status == 404 and error.codes & {"MANIFEST_UNKNOWN", "NAME_UNKNOWN"}:
                return None
            raise
        digest = "sha256:" + hashlib.sha256(body).hexdigest()
        if headers.get("Docker-Content-Digest") != digest:
            raise RuntimeError("Registry manifest content digest mismatch")
        config_digest = json.loads(body).get("config", {}).get("digest", "")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", config_digest):
            raise RuntimeError("Expected a single-platform schema-2/OCI image manifest")
        return {"digest": digest, "image_id": config_digest}

    def prove_denied_write(self):
        # Empty upload only: no blob data or image manifest is published.
        repository = "notekeeper-scope-probe"
        try:
            token = self.token(repository)
            status, headers, _ = self.request(f"/v2/{repository}/blobs/uploads/", "POST", b"", {
                "Authorization": "Bearer " + token,
            })
        except RegistryError as error:
            if error.status in (401, 403) and error.codes & {"UNAUTHORIZED", "DENIED"}:
                print("Confirmed: publisher cannot start an upload outside the two approved repositories.")
                return
            raise RuntimeError("Scope check failed without a confirmed authorization denial") from error
        if status == 202:
            location = urllib.parse.urlsplit(urllib.parse.urljoin(f"https://{self.host}", headers.get("Location", "")))
            if location.scheme != "https" or location.netloc != self.host or not location.path.startswith(f"/v2/{repository}/blobs/uploads/"):
                raise RuntimeError("Overbroad access; could not safely cancel the empty probe upload")
            path = location.path + ("?" + location.query if location.query else "")
            self.request(path, "DELETE", headers={"Authorization": "Bearer " + token})
        raise RuntimeError("Publisher scope is too broad: out-of-scope write was accepted; publication stopped")


def ensure_same_image(existing, local):
    if existing and existing["image_id"] != local["image_id"]:
        raise RuntimeError("SHA tag points to a different image. Preserve it; use a new release commit.")


def registry_config(name):
    if not re.fullmatch(r"[a-z0-9]{5,50}", name):
        raise ValueError("Invalid ACR name")
    config = json.loads(subprocess.check_output(["az", "acr", "show", "--name", name, "--output", "json"], text=True))
    if config["loginServer"] != name + ".azurecr.io" or config["adminUserEnabled"] is not False:
        raise RuntimeError("Unexpected ACR endpoint or admin authentication enabled")
    if config["sku"]["name"] != "Basic" or config.get("publicNetworkAccess") != "Enabled":
        raise RuntimeError("ACR differs from the agreed Basic/public-endpoint lab configuration")
    if config.get("roleAssignmentMode") != "AbacRepositoryPermissions":
        raise RuntimeError("ACR must use ABAC repository permissions")
    subscription = os.environ["AZURE_SUBSCRIPTION_ID"]
    if not config["id"].lower().startswith(f"/subscriptions/{subscription.lower()}/"):
        raise RuntimeError("ACR belongs to an unexpected subscription")
    return config["loginServer"]


def freeze(name, repository, commit, digest):
    # Tag and manifest attributes are independent; protect both.
    for image in (f"{repository}:{commit}", f"{repository}@{digest}"):
        subprocess.run(["az", "acr", "repository", "update", "--name", name, "--image", image,
                        "--write-enabled", "false", "--delete-enabled", "false", "--output", "none"], check=True)
        attributes = json.loads(subprocess.check_output(["az", "acr", "repository", "show", "--name", name,
                                                         "--image", image, "--output", "json"], text=True))["changeableAttributes"]
        if attributes["writeEnabled"] or attributes["deleteEnabled"] or not attributes["readEnabled"]:
            raise RuntimeError("Image protection verification failed")


def main():
    commit = os.environ["COMMIT_SHA"]
    valid_sha(commit)
    candidate = verify(ROOT / "tested-images", commit, os.environ["EXPECTED_CANDIDATE_SHA256"])
    local = {component: inspect_image(component, commit) for component in COMPONENTS}
    if local != candidate["images"]:
        raise RuntimeError("Local images differ from the tested candidate")
    name = os.environ["ACR_REGISTRY_NAME"]
    host = registry_config(name)
    credential = json.loads(subprocess.check_output(["az", "acr", "login", "--name", name,
                                                     "--expose-token", "--output", "json"], text=True))
    if credential["loginServer"] != host or not credential.get("accessToken"):
        raise RuntimeError("Unexpected registry login response")
    token = credential["accessToken"]
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print("::add-mask::" + token, flush=True)
    registry = Registry(host, token)
    existing = {}
    # Check both existing SHA tags before pushing either image.
    for component in COMPONENTS:
        existing[component] = registry.manifest(f"notekeeper-{component}", commit)
        ensure_same_image(existing[component], local[component])
    registry.prove_denied_write()
    release = {"commit": commit, "source": SOURCE, "workflow_run_id": candidate["workflow_run_id"],
               "platform": "linux/amd64", "build_inputs": candidate["build_inputs"], "images": {}}
    try:
        subprocess.run(["docker", "login", host, "--username", "00000000-0000-0000-0000-000000000000",
                        "--password-stdin"], input=token, text=True, check=True)
        for component in COMPONENTS:
            repository = f"notekeeper-{component}"
            tag = f"{host}/{repository}:{commit}"
            if not existing[component]:
                subprocess.run(["docker", "tag", local[component]["local_tag"], tag], check=True)
                subprocess.run(["docker", "push", tag], check=True)
            manifest = registry.manifest(repository, commit)
            if not manifest:
                raise RuntimeError("Pushed manifest cannot be read back")
            ensure_same_image(manifest, local[component])
            digest = manifest["digest"]
            freeze(name, repository, commit, digest)
            release["images"][component] = {"tag": tag, "reference": f"{host}/{repository}@{digest}"}
        Path("release.json").write_text(json.dumps(release, indent=2) + "\n")
        print(json.dumps({"commit": commit, "images": release["images"]}, indent=2))
    finally:
        subprocess.run(["docker", "logout", host], check=False)


if __name__ == "__main__":
    main()
