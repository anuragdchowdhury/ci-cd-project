#!/usr/bin/env python3
"""Record tested image IDs; publish those images on this same runner."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from ci_tools import ROOT, INPUTS, sha256

COMPONENTS = ("backend", "frontend")
SOURCE = "https://github.com/anuragdchowdhury/ci-cd-project"


def valid_sha(commit):
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("A full, lowercase Git commit SHA is required")


def inspect_image(component, commit):
    image = f"notekeeper-{component}:{commit}"
    value = json.loads(subprocess.check_output(["docker", "image", "inspect", image], text=True))[0]
    if value["Os"] != "linux" or value["Architecture"] != "amd64":
        raise ValueError("The AKS lab release must target linux/amd64")
    labels = value["Config"].get("Labels") or {}
    if labels.get("org.opencontainers.image.revision") != commit or labels.get("org.opencontainers.image.source") != SOURCE:
        raise ValueError(f"Unexpected revision/source labels on {component}")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", value["Id"]):
        raise ValueError("Invalid Docker image ID")
    return {"local_tag": image, "image_id": value["Id"], "platform": "linux/amd64"}


def record(commit):
    valid_sha(commit)
    images = {component: inspect_image(component, commit) for component in COMPONENTS}
    folder = ROOT / "tested-images"
    folder.mkdir(exist_ok=True)
    metadata = {"commit": commit, "source": SOURCE, "images": images,
                "build_inputs": INPUTS,
                "workflow_run_id": os.environ["GITHUB_RUN_ID"]}
    candidate = folder / "candidate.json"
    candidate.write_text(json.dumps(metadata, indent=2) + "\n")
    with Path(os.environ["GITHUB_ENV"]).open("a") as output:
        output.write(f'EXPECTED_CANDIDATE_SHA256={sha256(candidate)}\n')


def verify(folder, commit, candidate_digest):
    valid_sha(commit)
    folder = Path(folder)
    if not re.fullmatch(r"[0-9a-f]{64}", candidate_digest):
        raise ValueError("Missing or malformed candidate checksum")
    if sha256(folder / "candidate.json") != candidate_digest:
        raise ValueError("Release candidate checksum mismatch")
    metadata = json.loads((folder / "candidate.json").read_text())
    if metadata["commit"] != commit or metadata["source"] != SOURCE or metadata["build_inputs"] != INPUTS:
        raise ValueError("Release candidate source/checksum mismatch")
    if str(metadata["workflow_run_id"]) != os.environ["GITHUB_RUN_ID"] or set(metadata["images"]) != set(COMPONENTS):
        raise ValueError("Candidate must belong to this run and include both images")
    return metadata


if __name__ == "__main__":
    if sys.argv[1] == "record":
        record(os.environ["COMMIT_SHA"])
    else:
        raise SystemExit("Usage: release_candidate.py record")
