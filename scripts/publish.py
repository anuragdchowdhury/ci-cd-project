#!/usr/bin/env python3
"""Push existing, tested images to GHCR. Never rebuild during promotion."""
import base64
import json
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

MANIFEST_TYPES = ", ".join((
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
))


def ensure_tag_absent(repository, commit, username, credential):
    """Check authenticated registry status before publishing.

    A manifest 404 allows initial publication. Authentication/authorization and
    network errors fail closed. Tokens remain in headers/memory, never files.
    """
    path = repository.removeprefix("ghcr.io/")
    query = urllib.parse.urlencode({
        "service": "ghcr.io", "scope": f"repository:{path}:pull,push",
    })
    auth = base64.b64encode(f"{username}:{credential}".encode()).decode()
    token_request = urllib.request.Request(
        "https://ghcr.io/token?" + query, headers={"Authorization": "Basic " + auth},
    )
    try:
        with urllib.request.urlopen(token_request, timeout=30) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"GHCR authentication failed (HTTP {error.code}); check package access.") from None
    except urllib.error.URLError:
        raise RuntimeError("Cannot contact GHCR; refusing publication.") from None
    bearer = payload.get("token") or payload.get("access_token")
    if not bearer:
        raise RuntimeError("GHCR did not issue a registry token; refusing publication.")
    request = urllib.request.Request(
        f"https://ghcr.io/v2/{path}/manifests/{commit}", method="HEAD",
        headers={"Authorization": "Bearer " + bearer, "Accept": MANIFEST_TYPES},
    )
    try:
        with urllib.request.urlopen(request, timeout=30):
            pass
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return
        raise RuntimeError(f"Cannot check GHCR tag (HTTP {error.code}); refusing publication.") from None
    except urllib.error.URLError:
        raise RuntimeError("Cannot check GHCR tag; refusing publication.") from None
    raise RuntimeError("This SHA tag already exists. Preserve it and use a new release commit.")


def main():
    namespace = os.environ["GHCR_NAMESPACE"].lower()
    commit = os.environ["COMMIT_SHA"]
    username = os.environ["REGISTRY_USERNAME"]
    credential = os.environ["REGISTRY_TOKEN"]
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", namespace):
        raise ValueError("GHCR_NAMESPACE must be the GitHub repository owner")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("COMMIT_SHA must be a full Git commit SHA")
    if not username or not credential:
        raise ValueError("Registry authentication is required")
    repositories = {component: f"ghcr.io/{namespace}/notekeeper-{component}"
                    for component in ("backend", "frontend")}
    # Check both tags before pushing either. Main runs are serialized by workflow
    # concurrency; actual deployment identity remains the registry digest.
    for repository in repositories.values():
        ensure_tag_absent(repository, commit, username, credential)
    release = {"commit": commit, "images": {}}
    for component, repository in repositories.items():
        tag = f"{repository}:{commit}"
        subprocess.run(["docker", "tag", f"notekeeper-{component}:{commit}", tag], check=True)
        subprocess.run(["docker", "push", tag], check=True)
        output = subprocess.check_output(
            ["docker", "image", "inspect", tag, "--format", "{{json .RepoDigests}}"], text=True,
        )
        references = json.loads(output)
        reference = next(ref for ref in references if ref.startswith(repository + "@sha256:"))
        release["images"][component] = {"tag": tag, "reference": reference}
    Path("release.json").write_text(json.dumps(release, indent=2) + "\n")
    print("Published two tested images to GHCR; release.json records their immutable digests.")


if __name__ == "__main__":
    main()
