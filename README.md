# NoteKeeper: GitHub Actions → Azure hands-on lab

Repository: https://github.com/anuragdchowdhury/ci-cd-project

Start with [Step 1](docs/01-local-and-ci.md). The complete implementation order and acceptance criteria are in [the lab plan](docs/00-lab-plan.md). Optional Antigravity prompts are in [the generation guide](docs/antigravity-prompts.md).

Follow [Azure bootstrap](docs/02-azure-bootstrap.md), then [secure ACR publication](docs/03-secure-acr-ci.md). The operator has completed bootstrap/ACR and the diagnostic OIDC check. The main workflow has successfully tested, scanned and published both SHA-tagged images to ACR. Next follow [AKS foundation](docs/04-aks-foundation.md). There is one application registry: ACR.

## What is implemented in this starter

- Spring Boot 4.1.1 / Java 21 REST API: create, list with pagination, read, update, delete, validation and sanitized errors.
- React frontend, with a public runtime configuration file rather than environment-specific builds.
- Local PostgreSQL 17 and Flyway schema migration. Azure profile prepares Entra JDBC authentication; Azure identity, database principal and schema permissions still need provisioning.
- Non-root Dockerfiles, a read-only local runtime, and a same-origin `/api` reverse proxy.
- Prometheus endpoint on internal port 9090, HTTP histograms, JVM/pool metrics and low-cardinality business counters.
- Pinned Application Insights Java agent; starts only when a connection string is supplied. Log export is OFF, Micrometer export is OFF, and a documented metric filter excludes Java-agent metrics.
- Browser Application Insights SDK. It runs in the browser, not as a second process in the frontend container. It is disabled locally until configured.
- Request IDs on every response; real W3C trace/span IDs when the Java agent supplies a span. A request ID alone is not a distributed trace.
- Backend API tests, frontend API tests, and a container/PostgreSQL smoke test used in GitHub Actions.
- CI tests → builds two images → tests the exact images. Main publishes the exact tested images to ACR through the existing OIDC publisher identity after security checks. PRs remain read-only. No GitHub CI metrics are exported to Azure.
- Terraform bootstrap/ACR plus reusable nonprod/prod platform roots: private AKS, Entra-only private PostgreSQL, private Key Vaults, workload/deploy identities, scoped ACR pulls and budget alerts. Step 4 explains provisioning and verification; code presence does not mean these resources have been applied.

## What is intentionally a later lab milestone

Azure bootstrap/ACR provisioning, diagnostic OIDC and main CI publication have been verified. Step 4 supplies AKS/network/database/vault foundation code for operator review and apply. Private runners, Helm, Front Door/custom domains, database SQL principals/migrations, runtime Key Vault access, Azure telemetry, dashboards, alerts and drills remain subsequent milestones. There is no ongoing GHCR/ACR mirror. Follow Step 2's account, permission, cost and plan checks before applying.

This application has shared notes and no end-user login. Use disposable sample notes. We will restrict the hosted lab to operator access at Front Door/WAF before exposing it; real multi-user notes require authentication and per-user authorization as a separate application feature.

## Local quick start

Install Git, Docker Engine/Desktop and the Docker Compose plugin. Commands below use Bash (Windows: WSL2 or Git Bash with Docker).

```bash
cp .env.example .env
docker compose up --build -d
python3 scripts/smoke.py
```

Open http://localhost:8080. The database and API are reachable only through the local Docker network. The browser calls `/api/notes` on the same origin.

```bash
docker compose logs --tail=100 backend
docker compose down
```

`down` preserves local database notes. Only `docker compose down --volumes` deletes the disposable local database volume.

## Application API contract

| Method | Path | Result |
|---|---|---|
| GET | `/api/notes?page=0&size=20` | `{items,total,page,size}`; maximum size 100 |
| GET | `/api/notes/{uuid}` | One note; 404 if absent |
| POST | `/api/notes` | 201 plus Location header |
| PUT | `/api/notes/{uuid}` | Updated note |
| DELETE | `/api/notes/{uuid}` | 204 |

Write body: `{"title":"First note","content":"Hello"}`. Title must be nonblank and at most 160 characters; content must be present and at most 10,000 characters. Each returned note includes `id`, `title`, `content`, `createdAt`, `updatedAt`.

Internal management endpoints use port 9090: `/actuator/health/liveness`, `/actuator/health/readiness`, `/actuator/prometheus`. Never create public Ingress paths for these endpoints. Readiness includes database connectivity; liveness does not depend on database health.

## Configuration and image promotion

| Configuration | Local | Azure |
|---|---|---|
| `SPRING_PROFILES_ACTIVE` | `local` | `azure` |
| `DB_URL` | Compose PostgreSQL | Private PostgreSQL FQDN; correct environment database |
| `DB_USERNAME` | Local user | Entra principal registered in PostgreSQL |
| `DB_PASSWORD` | Disposable `.env` value | Unset |
| `APP_ENVIRONMENT` | `local` | `dev`, `staging`, `prod` |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Unset | Public routing information for the backend telemetry resource |
| Workload Identity variables | Unset | Injected by AKS federation/webhook |
| `/runtime-config.js` | Included local default | Helm-mounted ConfigMap; same immutable frontend image |

`APPLICATIONINSIGHTS_CONNECTION_STRING` is not an Azure login credential. Backend authenticated ingestion must be separately configured and proven before disabling local authentication. The browser SDK does not support Entra-authenticated ingestion; use a separate browser Application Insights resource with local ingestion enabled and privacy/volume controls. Do not place Azure tokens or secrets in runtime-config.js.

Azure schema migration will run once per environment as a controlled job using a migration identity. The long-running API gets DML privileges only. `ddl-auto=validate` prevents application startup from silently creating or altering tables.

ACR publication emits `release.json` with the full Git SHA and both `repository@sha256:...` references. CD promotes that same pair through all three environments without rebuilding or copying between environment registries. SHA tags are human-readable pointers; **digests are deployment identity**. OCI labels contain the Git revision. Base images and CI tools are pinned; the downloaded agent checksum is verified; source and final-image gates precede publication. See Step 3 for scope, actual validation and remaining signing/admission work.

## Useful source documentation

- Spring Boot releases: https://spring.io/projects/spring-boot
- Structured logging: https://docs.spring.io/spring-boot/reference/features/logging.html
- Azure JDBC identity plugin: https://github.com/Azure/azure-sdk-for-java/blob/main/sdk/identity/azure-identity-extensions/Azure-Database-for-PostgreSQL-README.md
- Java agent settings, logging OFF and metric filters: https://learn.microsoft.com/azure/azure-monitor/app/java-standalone-config
- Application Insights Entra authentication and browser exception: https://learn.microsoft.com/azure/azure-monitor/app/azure-ad-authentication
