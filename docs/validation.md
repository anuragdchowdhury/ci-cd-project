# Starter validation — 2026-10-02

| Check | Observed result | Limit |
|---|---|---|
| Frontend API tests | 4 passed, 0 failed | API transport tests, not browser end-to-end tests |
| React/Vite production build | Passed | Does not prove live browser/backend connectivity |
| Spring Boot API test | 1 integration test passed, containing create/read/list/update/delete, invalid input, pagination limit and malformed UUID assertions | Ran with available Java 17 and `-Djava.version=17`, using H2; source project and CI target Java 21 |
| Java compilation | Passed | Java 17 compatibility build; exact Java 21/container build still pending |
| YAML/JSON/POM/Python/shell syntax | Passed | Does not provision or validate cloud resources |
| GitHub Action pins | Checkout v4.2.2 and upload-artifact v4.6.2 verified against repository tag refs | Container base-image digests and agent checksum hardening remain Phase 2 |
| Docker Compose and real PostgreSQL smoke test | Not run in this execution environment; Docker unavailable | Included in CI and the local guide; must pass before Azure deployment |
| Browser visual verification | Not run; no installed browser executable | Frontend build and API tests passed, but visual/interactivity verification remains local |
| GHCR push | Configured to use the main Actions job GITHUB_TOKEN; live push not run here | Never claim a published digest before an actual registry push |
| Azure/Helm/DNS/monitoring/alerts | Not provisioned in Phase 1 | Follow phased implementation and actual evidence gates |

The backend's structured JSON startup/request logs were observed during the API test. Real trace IDs, Grafana panels, DCR ingestion behavior and alert firing require the telemetry and drill phases; the guide labels future examples as illustrative.

## GHCR change validation

Registry publication now targets GHCR, requests packages:write only on the main-only job, keeps PR container checks read-only, adds OCI repository-source labels, and preserves the digest-pair release manifest. Publisher regression tests cover initial missing manifests, existing tags, denied access, authentication failure and network failure. Actual GHCR authentication, image publication and Docker rebuild must be verified in GitHub Actions after applying the change.

All five GHCR preflight regression tests passed with mocked HTTP responses. Workflow/Compose YAML and Python syntax checks passed; permission checks confirmed that only the main-only images job requests package writes.

## Azure foundation patch — 2026-10-03

| Check | Result | Limit |
| --- | --- | --- |
| Terraform 1.16.5 download | Release checksum verified | Not an Azure authentication check |
| AzureRM 5.8.0 installation | HashiCorp-signed provider installed; Linux AMD64 / macOS ARM64 / macOS AMD64 hashes locked | Azure Policy and service availability still require account checks |
| Terraform formatting and HCL parsing | Passed | Does not replace provider schema validation |
| Resource arguments | Checked against pinned provider documentation, including v5 storage networking, container IDs and federation parent fields | Documentation checks do not execute Azure APIs |
| GitHub workflow lint | Passed with actionlint | Shellcheck was unavailable; script syntax and scope were reviewed separately |
| Backend configuration helper | Python compilation and isolated generation smoke check passed | Remote migration not executed |
| terraform validate | Blocked here: provider RPC local sockets are prohibited by the execution workspace | Must pass in the credential-free PR workflow and on the operator machine before apply |
| Azure plan/apply, OIDC and IAM denials | Not executed | The runbook and manual verification workflow provide the required cloud checkpoints |

No Azure session, state contents or live resources were accessed. GHCR publication
is paused in this patch; the previously completed release remains historical.


## ACR CI patch — 2026-10-03

- Twelve publisher/candidate security regressions passed: classified missing manifests versus auth/network errors, content-digest verification, SHA tag preservation, denied scope writes, safe cancellation, no credential forwarding, candidate tampering and wrong commit/run/component rejection.
- Workflow lint, Python compilation, build-input consistency and diff whitespace checks passed.
- Docker Hub manifest digests were resolved from authenticated registry responses; Linux AMD64 support was confirmed. Java agent and Trivy archive hashes were read from upstream GitHub release asset metadata; the downloaded Trivy archive matched its pinned checksum.
- Native Semgrep 1.179.0 scanned the Java/JS application with the four reviewed rules: zero findings. Both disposable unsafe Java/JS fixtures were detected and blocked.
- Native Trivy 0.75.0 current-source secret scanning passed. The fake AWS-key fixture was detected and blocked. A first known-vulnerable lodash fixture scan confirmed CVE-2021-23337; a frontend runtime-dependency scan found zero HIGH/CRITICAL findings.
- Repeated native vulnerability scans were limited by the execution filesystem's cached BoltDB memory-map failure. A full final scanner run including dev dependencies must pass in GitHub Actions; no successful full native run is claimed. Maven resolution was kept out of the secrets stage after encountering a shared-IP Maven Central rate limit.
- Docker builds, the pinned Semgrep Docker wrapper, image vulnerability/SBOM scans and Azure OIDC publication were not executed here: Docker and an authenticated Azure session are unavailable. PR/main workflows must validate these before deployment.
- GitHub plugin discovery reports it installed, but this session exposes no repository tools. Git push dry-run failed without authentication. The patch has not been pushed or opened as a PR.

No Terraform, federation subjects, Azure resources or GHCR packages were changed by this patch. Prior user-reported Azure provisioning/OIDC success is distinct from these local validation results. No Docker image archive is uploaded as a public-repository artifact.
