#!/usr/bin/env python3
"""Reviewed build inputs and a checksum-verified Linux CI scanner."""
import hashlib
import json
import re
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUTS = json.loads((ROOT / "ci/build-inputs.json").read_text())


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def check_inputs():
    for name in ("maven", "java", "node", "nginx", "postgres", "semgrep"):
        if not re.fullmatch(r"[a-z0-9./:_-]+@sha256:[0-9a-f]{64}", INPUTS[name]["reference"]):
            raise ValueError(f"Unpinned image: {name}")
    for filename in ("backend/Dockerfile", "frontend/Dockerfile"):
        for line in (ROOT / filename).read_text().splitlines():
            if line.startswith("FROM ") and line.split()[1] not in {
                INPUTS[k]["reference"] for k in ("maven", "java", "node", "nginx")
            }:
                raise ValueError(f"Unexpected/unpinned FROM in {filename}")
    backend = (ROOT / "backend/Dockerfile").read_text()
    agent = INPUTS["agent"]
    if f'ARG AI_AGENT_VERSION={agent["version"]}' not in backend or f'ARG AI_AGENT_SHA256={agent["sha256"]}' not in backend:
        raise ValueError("Agent Dockerfile and build input lock disagree")
    pcre2 = INPUTS["nginx_runtime_packages"]["pcre2"]
    if f'ARG PCRE2_VERSION={pcre2}' not in (ROOT / "frontend/Dockerfile").read_text():
        raise ValueError("Nginx PCRE2 version and build input lock disagree")
    if INPUTS["postgres"]["reference"] not in (ROOT / "compose.yaml").read_text():
        raise ValueError("Compose database is not pinned to the reviewed input")


def install_trivy():
    config = INPUTS["trivy_binary"]
    destination = ROOT / ".ci-tools"
    destination.mkdir(exist_ok=True)
    archive = destination / "trivy.tar.gz"
    with urllib.request.urlopen(config["url"], timeout=60) as response, archive.open("wb") as output:
        while block := response.read(1024 * 1024):
            output.write(block)
    if sha256(archive) != config["sha256"]:
        raise ValueError("Trivy archive checksum mismatch; refusing execution")
    with tarfile.open(archive) as bundle:
        member = bundle.getmember("trivy")
        if not member.isfile():
            raise ValueError("Unexpected Trivy archive entry")
        # Extract only this fixed, regular file; never unpack arbitrary paths.
        (destination / "trivy").write_bytes(bundle.extractfile(member).read())
    (destination / "trivy").chmod(0o755)
    archive.unlink()


if __name__ == "__main__":
    command = sys.argv[1]
    if command == "check":
        check_inputs()
    elif command == "install-trivy":
        install_trivy()
    elif command == "reference":
        print(INPUTS[sys.argv[2]]["reference"])
    else:
        raise SystemExit("Usage: ci_tools.py check|install-trivy|reference NAME")
