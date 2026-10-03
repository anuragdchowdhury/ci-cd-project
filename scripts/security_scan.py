#!/usr/bin/env python3
"""Fail-closed source/image scans and disposable scanner gate checks."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from ci_tools import INPUTS, ROOT

TRIVY = str(ROOT / ".ci-tools/trivy")
REPORTS = ROOT / "reports"
os.environ["TRIVY_CACHE_DIR"] = str(ROOT / ".ci-tools/trivy-cache")


def trivy_fs(target, scanners, output=None):
    command = [TRIVY, "fs", "--scanners", scanners, "--severity", "HIGH,CRITICAL",
               "--exit-code", "1", "--ignorefile", "/dev/null",
               "--skip-dirs", ".git,.ci-tools,reports,tested-images,scripts/__pycache__,frontend/node_modules"]
    if scanners == "secret":
        # Secrets are scanned in all source files. Disable library package
        # resolution here: it is unnecessary and can contact Maven Central.
        command += ["--pkg-types", "os", "--secret-config", ""]
    else:
        command += ["--include-dev-deps"]
    if output:
        command += ["--format", "json", "--output", str(output)]
    return command + [str(target)]


def semgrep(target, output, mount=None):
    mounts = ["-v", f"{ROOT}:/src:ro", "-v", f"{REPORTS}:/reports"]
    if mount:
        mounts += ["-v", f"{mount}:/fixtures:ro"]
    return ["docker", "run", "--rm", "--user", f"{os.getuid()}:{os.getgid()}",
            "-e", "HOME=/tmp", "-e", "SEMGREP_SEND_METRICS=off", *mounts,
            INPUTS["semgrep"]["reference"], "semgrep", "scan", "--config", "/src/security/semgrep.yml",
            "--error", "--strict", "--metrics", "off", "--disable-version-check", "--no-git-ignore",
            "--json", "--output", f"/reports/{output}", *target]


def require_gate_failure(command, report, section, expected):
    result = subprocess.run(command, check=False)
    if result.returncode != 1 or not report.exists():
        raise RuntimeError("Scanner gate self-test did not produce a confirmed finding")
    data = json.loads(report.read_text())
    values = []
    if section == "semgrep":
        if data.get("errors"):
            raise RuntimeError("Semgrep self-test produced a scanner error")
        values = [x["check_id"] for x in data.get("results", [])]
    else:
        key = "Secrets" if section == "secret" else "Vulnerabilities"
        id_key = "RuleID" if section == "secret" else "VulnerabilityID"
        values = [x[id_key] for item in data.get("Results", []) for x in item.get(key, []) or []]
    expected_ids = (expected,) if isinstance(expected, str) else expected
    if not all(any(value.endswith(rule) for value in values) for rule in expected_ids):
        raise RuntimeError(f"Gate did not detect the expected {section} fixture")
    report.unlink()  # Fixture reports, especially secret matches, are not artifacts.
    print(f"Confirmed blocked {section} fixture: {expected}", flush=True)


def self_test():
    # Generate fake unsafe inputs outside the repo. No application, image or Azure mutation.
    with tempfile.TemporaryDirectory(prefix="notekeeper-security-") as folder:
        fixture = Path(folder)
        (fixture / "Unsafe.java").write_text(
            'class Unsafe { void run(String input) throws Exception { Runtime.getRuntime().exec(input); } }\n')
        (fixture / "unsafe.js").write_text('function run(input) { return eval(input); }\n')
        require_gate_failure(semgrep(["/fixtures"], "sast-fixture.json", fixture),
                             REPORTS / "sast-fixture.json", "semgrep", ("java-process-execution", "javascript-dynamic-code"))
        (fixture / "credentials.txt").write_text('aws_access_key_id = "' + 'AKIA' + 'Q7M2A9N5T8V3W6X1' + '"\n')
        report = REPORTS / "secret-fixture.json"
        require_gate_failure(trivy_fs(fixture, "secret", report), report, "secret", "aws-access-key-id")
        (fixture / "package-lock.json").write_text(json.dumps({
            "name": "scanner-fixture", "version": "1.0.0", "lockfileVersion": 3,
            "packages": {"": {"name": "scanner-fixture", "version": "1.0.0", "dependencies": {"lodash": "4.17.20"}},
                         "node_modules/lodash": {"version": "4.17.20"}},
        }))
        report = REPORTS / "dependency-fixture.json"
        require_gate_failure(trivy_fs(fixture, "vuln", report), report, "vuln", "CVE-2021-23337")


def source_scan():
    results = [subprocess.run(command, check=False).returncode for command in (
        trivy_fs(ROOT / "frontend", "vuln", REPORTS / "dependencies.json"),
        trivy_fs(ROOT, "secret"),  # Console report; no secret JSON artifact.
        semgrep(["/src/backend/src/main/java", "/src/frontend/src"], "sast.json"),
    )]
    if any(results):
        raise RuntimeError("Source security gate failed; inspect findings or scanner errors")


def image_scan(commit):
    from release_candidate import valid_sha
    valid_sha(commit)
    failed = False
    for component in ("backend", "frontend"):
        image = f"notekeeper-{component}:{commit}"
        command = [TRIVY, "image", "--image-src", "docker", "--scanners", "vuln",
                   "--severity", "HIGH,CRITICAL", "--exit-code", "1", "--ignorefile", "/dev/null",
                   "--format", "json", "--output", str(REPORTS / f"{component}-image.json"), image]
        failed |= subprocess.run(command, check=False).returncode != 0
        subprocess.run([TRIVY, "image", "--image-src", "docker", "--scanners", "vuln", "--format", "cyclonedx",
                        "--output", str(REPORTS / f"{component}-sbom.cdx.json"), image], check=True)
    if failed:
        raise RuntimeError("Container security gate failed; neither image will be published")


if __name__ == "__main__":
    REPORTS.mkdir(exist_ok=True)
    if sys.argv[1] == "self-test":
        self_test()
    elif sys.argv[1] == "source":
        source_scan()
    elif sys.argv[1] == "images":
        image_scan(sys.argv[2])
    else:
        raise SystemExit("Usage: security_scan.py self-test|source|images COMMIT_SHA")
