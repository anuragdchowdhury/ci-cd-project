#!/usr/bin/env python3
"""Push existing, tested images. Never build during promotion."""
import json
import os
import re
import subprocess
from pathlib import Path

def run(*args):
    return subprocess.check_output(args, text=True).strip()

username = os.environ["DOCKERHUB_USERNAME"]
commit = os.environ["COMMIT_SHA"]
if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", username):
    raise ValueError("Set DOCKERHUB_USERNAME to your lowercase Docker Hub namespace")
if not re.fullmatch(r"[0-9a-f]{40}", commit):
    raise ValueError("COMMIT_SHA must be a full Git commit SHA")
# Fail closed on network/auth errors; check both tags before publishing either.
for component in ("backend", "frontend"):
    existing = subprocess.run(["docker", "manifest", "inspect", f"{username}/notekeeper-{component}:{commit}"], capture_output=True, text=True)
    if existing.returncode == 0:
        raise RuntimeError("This commit already has a published image. Preserve it and create a new release commit.")
    message = existing.stderr.lower()
    if not any(text in message for text in ("no such manifest", "manifest unknown", "manifest_unknown")):
        raise RuntimeError("Cannot verify that the SHA tag is absent; check registry access before publishing.")
release = {"commit": commit, "images": {}}
for component in ("backend", "frontend"):
    repository = f"{username}/notekeeper-{component}"
    tag = f"{repository}:{commit}"
    # Configure Docker Hub immutable SHA tags before enabling publication.
    subprocess.run(["docker", "tag", f"notekeeper-{component}:{commit}", tag], check=True)
    subprocess.run(["docker", "push", tag], check=True)
    references = json.loads(run("docker", "image", "inspect", tag, "--format", "{{json .RepoDigests}}"))
    reference = next(ref for ref in references if ref.startswith(repository + "@sha256:"))
    release["images"][component] = {"tag": tag, "reference": reference}
Path("release.json").write_text(json.dumps(release, indent=2) + "\n")
print("Published two tested images; release.json records their immutable digests.")
