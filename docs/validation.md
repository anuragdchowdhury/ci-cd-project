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
| Docker Hub push | Requires your username and publishing token | Never claim a published digest before an actual registry push |
| Azure/Helm/DNS/monitoring/alerts | Not provisioned in Phase 1 | Follow phased implementation and actual evidence gates |

The backend's structured JSON startup/request logs were observed during the API test. Real trace IDs, Grafana panels, DCR ingestion behavior and alert firing require the telemetry and drill phases; the guide labels future examples as illustrative.
