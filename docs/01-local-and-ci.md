# Step 1: Run NoteKeeper locally, then publish tested images

No Azure resources are needed for this step. This establishes a working application before adding cloud networking and IAM, so failures remain easy to diagnose.

## 1. Get the code

If the starter has been pushed to your repository:

```bash
git clone https://github.com/anuragdchowdhury/ci-cd-project.git
cd ci-cd-project
```

If you received a ZIP instead, clone the empty repository first, then copy the ZIP's `ci-cd-project` contents **including `.github`, `.gitignore` and `.env.example`** into the clone. The ZIP excludes `.git`; preserve the clone's `.git` directory. Do not create an extra nested `ci-cd-project` folder.

```bash
git status
```

Expect backend, frontend, scripts, docs, compose.yaml and .github files.

## 2. Start the local database and both applications

```bash
docker version
docker compose version
cp .env.example .env
docker compose up --build -d
docker compose ps
```

The first build downloads dependencies. Open http://localhost:8080. PostgreSQL stores notes in a named Docker volume; Spring runs the versioned Flyway migration; Nginx serves React at `/` and proxies `/api/` to Spring **without stripping `/api`**. There is no browser CORS problem because the UI and API share an origin.

The local Nginx static server is unrelated to the retired Kubernetes ingress-nginx controller. AKS will use a maintained Traefik Ingress controller later.

Create a note, edit it, refresh the page and confirm it persists, then delete it. Also create another note and restart the stack to prove persistence:

```bash
docker compose restart
```

## 3. Run checks and examine logs

```bash
python3 scripts/smoke.py
docker run --rm -v "$PWD/backend:/workspace" -w /workspace maven:3.9.12-eclipse-temurin-21 mvn -B -ntp verify
docker run --rm -v "$PWD/frontend:/workspace" -w /workspace node:24-alpine sh -ec 'npm ci; npm test; npm run build'
docker compose logs --tail=100 backend
```

Expected smoke result:

```text
PASS: same-origin create, read, list, update, delete, and PostgreSQL persistence.
```

Use browser developer tools → Network → a `/api/notes` request → response headers to find `X-Request-Id`. Without a configured agent, there is no real distributed `X-Trace-Id`; we will verify that after Azure telemetry setup. We will never manufacture trace IDs to make a demonstration appear to work.

Management endpoint check, from inside the backend container:

```bash
docker compose exec backend sh -c 'wget -qO- http://localhost:9090/actuator/health/readiness'
docker compose exec backend sh -c 'wget -qO- http://localhost:9090/actuator/prometheus'
```

Prometheus output should contain JVM series, HTTP request histograms after traffic, Hikari pool series, and `notekeeper_notes_created_total`. Do not expose port 9090 to the public website.

If startup fails, inspect `docker compose logs db backend`. A changed `.env` password does not change the password in an already-initialized PostgreSQL volume. Keep its original password, or deliberately recreate the disposable local volume.

## 4. Commit the starter, if it has not already been pushed

Set your own Git author identity if Git asks for it, then:

```bash
git add .
git diff --cached --stat
git diff --cached
git commit -m "Add NoteKeeper application, containers and CI"
git push -u origin main
```

`.env`, Terraform state, private keys, node_modules and compiled outputs are ignored. Review the staged diff before committing. A login prompt belongs to your local Git credential flow; do not paste credentials into chat.

## 5. Observe the first GitHub Actions run

Open your repository → Actions → **Test and build**. The workflow executes backend tests and frontend tests independently, then builds the two container images and uses real PostgreSQL for the smoke test.

Publication is paused during the ACR transition. All application CI jobs have contents:read; no package-writing permission is needed. PR container checks run in a separate container-check job. Application CI performs no Azure login and sends no CI metrics or application telemetry to Azure.

## 6. Historical GHCR publication checkpoint

This section describes the completed previous checkpoint, not the active workflow.
Keep these packages private. New releases will go directly to one ACR; proceed to
[Azure bootstrap](02-azure-bootstrap.md). Do not change package visibility for a
pull test: private local GHCR pulls use authenticated access.

GHCR replaces Docker Hub for this project. No Docker Hub account, DOCKERHUB_USERNAME variable, DOCKERHUB_TOKEN secret, or manually created GitHub PAT is needed for Actions publication. GitHub creates the short-lived GITHUB_TOKEN automatically; do not try to create a repository secret with that name.

After tests and the PostgreSQL container smoke test pass on main, the same tested images are pushed to:

```text
ghcr.io/anuragdchowdhury/notekeeper-backend:<full-40-character-Git-SHA>
ghcr.io/anuragdchowdhury/notekeeper-frontend:<full-40-character-Git-SHA>
```

Names use the lowercased repository owner. Each image has org.opencontainers.image.source pointing to this repository. Packages published by its workflow are linked to the repository; existing packages created outside this workflow may require granting this repository access in the package settings.

First publication creates packages with private visibility. Publishing from a public repository does not make packages public automatically. The completed GHCR release is historical; no ongoing ACR mirror is planned and no GHCR pull token belongs in pods.

The workflow checks both remote SHA tags before publishing either. It uses authenticated registry status: a missing manifest (404) allows initial publication, while authentication/authorization/network failures stop publication. An existing SHA tag is preserved. This is a workflow safeguard, not a registry-enforced immutable-tag guarantee; always deploy the actual digest. Main publication jobs are serialized by workflow concurrency.

Do not rerun publication to replace a successfully published SHA. If either image exists (including a partially published pair after a failure), preserve it and make a new commit for a new release. The Actions run has a release-<SHA> artifact containing release.json with both ghcr.io/...@sha256:... references. These are actual registry digests, not Git SHAs and not Docker image IDs.

If publishing fails with a package permission error, verify that the main job has packages:write and that any existing package grants this repository Actions access. Keep PR tokens read-only. Do not solve it by adding a broad personal token or enabling writes globally.

## 7. Protect main after the initial bootstrap commit

GitHub → Settings → Rules/Rulesets (or Branches) → protect `main`: require pull requests, passing backend-test, frontend-test and container-check PR checks, and block force pushes. Use feature branches afterward. Configure dev, staging and prod GitHub Environments during CD setup, with production reviewers and deployment branch restrictions; verify which protection features your GitHub plan offers.

## Step 1 exit criteria

- UI CRUD works at localhost:8080 and refresh/restart preserves notes.
- Backend/frontend tests and real PostgreSQL smoke test pass.
- A response exposes X-Request-Id; API validation rejects invalid input.
- Main CI can publish full-SHA tags and release.json records both digests.
- No `.env` or credentials are committed.

Next: [Azure bootstrap and registry foundation](02-azure-bootstrap.md). Security scanning/image hardening must still pass before enabling cloud publication/deployment. Check quotas and costs before creating Front Door Premium or the two clusters.

## Registry checkpoint superseded by ACR

The GHCR instructions above describe the completed historical checkpoint. Current publishing is implemented in [Step 3](03-secure-acr-ci.md), uses ACR and Azure OIDC, and replaces the old publisher environment variables. Do not re-enable GHCR publication.
