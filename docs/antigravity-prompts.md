# Optional Antigravity master prompts

The starter already includes backend and frontend code. Use these prompts to regenerate or extend it if you prefer that workflow. Work in a feature branch and review the diff; do not replace working code blindly. Run the backend prompt first, verify its API contract, then run the frontend prompt against that contract.

## Prompt 1 — Backend

```text
You are implementing the backend of a hands-on NoteKeeper CI/CD lab. Work only
in backend/ unless I explicitly approve another path. Read README.md and the
docs/00-lab-plan.md contract first. Preserve the same API as the existing starter.

Use Java 21, the pinned stable Spring Boot 4.1.x dependency set already present,
Maven, Spring MVC, Bean Validation, Spring Data JPA, PostgreSQL 17, Flyway,
Actuator and Micrometer Prometheus. Do not downgrade to an unsupported release,
use a milestone/SNAPSHOT, or choose unverified future versions.

Implement shared dummy notes with UUID id, title max160 nonblank, content max10000,
createdAt and updatedAt. Provide GET /api/notes?page=0&size=20 returning
{items,total,page,size}; cap size100. GET /api/notes/{id}; POST returns201 and
Location; PUT updates; DELETE returns204; missing valid UUID returns404;
malformed JSON/UUID and invalid inputs return400. Use sanitized error JSON with
timestamp,status,message,requestId,traceId. Never log note content or secrets.

The local profile connects to PostgreSQL with disposable environment-provided
credentials and executes Flyway. The azure profile uses the Azure JDBC identity
plugin and AKS projected Workload Identity tokens, TLS hostname verification
with an explicit CA bundle, and no DB password. Runtime cannot create schema:
Flyway is off in azure; ddl-auto is validate. Azure migrations later use a
distinct identity/job. Do not assume Azure RBAC creates database SQL principals.

Keep management endpoints on9090 separate from application8080. Expose internal
health liveness/readiness and prometheus only. Readiness includes DB connectivity;
liveness does not. Enable HTTP latency histograms and low-cardinality note
counters; no note IDs/titles/user IDs as metric labels.

Attach exactly one pinned Azure Application Insights Java agent based on OTel
in the Docker runtime only when configured. Do not add a competing OTel SDK,
exporter or Spring instrumentation starter. Prometheus owns metrics and
Container Insights will own severity-filtered stdout logs: disable agent logging
export and Micrometer export; explicitly filter remaining duplicate agent
metrics. Keep sampled request/dependency spans and sanitized exception events.
Use real Span.current() trace/span context and MDC for JSON logs and response
correlation headers. Never fabricate trace IDs when no agent/context exists.
Don't claim every error survives head sampling. For future deterministic drills
sampling will temporarily be100% in the affected environment.

Create a multi-stage non-root Dockerfile, use Java21 runtime, allow read-only
root filesystem with writable/tmp, use memory-aware JVM configuration and
ExitOnOutOfMemoryError. Keep build/runtime configuration separate; no secrets
in images. Keep the established entrypoint and OCI revision label contract.

Write meaningful API tests for CRUD, validation, pagination limits, missing
notes and request IDs. Use the real-PostgreSQL smoke test for migration/container
integration. Build and run tests, report exact results and any unavailable
checks. Do not add public fault/kill/oom endpoints. Do not create Terraform,
cloud resources, GitHub workflows, Key Vault secret values or CI telemetry.
Explain each changed file and required environment variable. Stop after the
backend contract is verified so the frontend can be generated against it.
```

## Prompt 2 — Frontend, after backend contract passes

```text
Implement the frontend of this NoteKeeper lab in frontend/. Read README.md,
docs/00-lab-plan.md, and the backend controller before writing code. Preserve
the established API contract and same-origin /api routing.

Use the pinned React/Vite versions in package.json, a committed lockfile and
npm ci. Build a responsive accessible notebook UI with paginated note list,
new/edit form, save, confirmed delete, empty/loading/error states and duplicate
submission prevention. Use no HTML rendering of note content; React escaping
must remain enabled. Validate title/content lengths and show backend errors
without leaking server internals. Display requestId/real traceId on failures.

The API is /api/notes on the same origin. Read window.__APP_CONFIG__ from
/runtime-config.js containing public apiBase=/api, environment and a browser
Application Insights connection string. Load it before the compiled app.
Helm later mounts this public file via ConfigMap so the identical image digest
is promoted through dev,staging,prod. Do not hardcode environment domains or
use environment-specific VITE builds. No Azure credentials/DB secrets/browser
client secrets may enter source, bundle or public runtime configuration.

Integrate Application Insights JavaScript SDK in the browser with W3C trace
propagation for same-origin requests. This is browser instrumentation, not a
Java agent or a daemon in Nginx. Do not enable a second browser exporter or Java
agent browser injection. Collect page views, request failures and browser
exceptions; never attach note contents, tokens or personal identifiers;
sanitize URLs/query strings and disable cookies. Disable local telemetry when
the connection string is absent. The browser has its own Application Insights
resource because the SDK cannot use Entra-authenticated ingestion.

Provide a multi-stage Dockerfile and non-root Nginx static server on8080 with
read-only compatibility and writable/tmp. In local Compose, reverse proxy
/api to backend:8080 preserving the /api prefix. In AKS, Ingress routes directly
to the backend. Runtime config and index.html must not be cached; hashed assets
may be cached. Provide /healthz for the frontend probe. API retries must not
duplicate non-idempotent POST requests.

Add tests for API input serialization, create/update method/path selection,
204 deletion and failed-request correlation IDs. Build and verify core UI
flows. Explain file changes, commands and observed results. Do not create cloud
infrastructure, CI build metrics, production simulation endpoints or secrets.
```

The generation tool is optional: infrastructure sequencing, IAM, promotion, telemetry ownership and acceptance tests remain our responsibility even when an assistant generates application code.
