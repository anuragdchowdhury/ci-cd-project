"""Retrieve a release only from successful main-push CI, with artifact integrity."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import urllib.parse
import urllib.request
import zipfile

from deployment_config import validate_release

REPO = "anuragdchowdhury/ci-cd-project"


def api(path):
    request = urllib.request.Request("https://api.github.com/repos/" + REPO + path,
        headers={"Authorization": "Bearer " + os.environ["GH_TOKEN"],
                 "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("commit")
    parser.add_argument("--registry", required=True)
    parser.add_argument("--output", default="release.json", type=Path)
    args = parser.parse_args()
    # Validate before constructing any URL.
    from deployment_config import match
    match(r"[0-9a-f]{40}", args.commit)
    query = urllib.parse.urlencode({"branch": "main", "event": "push", "status": "success", "head_sha": args.commit})
    runs = api("/actions/workflows/ci.yml/runs?" + query)["workflow_runs"]
    for run in runs:
        if (run["head_sha"] != args.commit or run["head_branch"] != "main" or
                run["event"] != "push" or run["conclusion"] != "success" or run["path"] != ".github/workflows/ci.yml"):
            continue
        artifacts = api(f'/actions/runs/{run["id"]}/artifacts')["artifacts"]
        candidates = [a for a in artifacts if a["name"] == "release-" + args.commit and not a["expired"]]
        if len(candidates) != 1:
            continue
        artifact = candidates[0]
        request = urllib.request.Request(f"https://api.github.com/repos/{REPO}/actions/artifacts/{int(artifact['id'])}/zip",
            headers={"Accept": "application/vnd.github+json"})
        request.add_unredirected_header("Authorization", "Bearer " + os.environ["GH_TOKEN"])
        # Redirected GitHub artifact storage is handled by urllib. No VM receives this token.
        with urllib.request.urlopen(request, timeout=60) as response:
            archive = response.read()
        if artifact.get("digest") != "sha256:" + hashlib.sha256(archive).hexdigest():
            raise ValueError("Artifact archive digest mismatch")
        with zipfile.ZipFile(io.BytesIO(archive)) as files:
            if files.namelist() != ["release.json"] or files.getinfo("release.json").file_size > 65536:
                raise ValueError("Unexpected release artifact contents")
            release = json.loads(files.read("release.json"))
        validate_release(release, args.commit, args.registry, run["id"])
        args.output.write_text(json.dumps(release, indent=2) + "\n")
        print(f'Verified release from successful CI run {run["id"]}: {args.commit}')
        return
    raise SystemExit("No unexpired release from successful main-push CI exists for this SHA")


if __name__ == "__main__":
    main()
