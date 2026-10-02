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

Open your repository → Actions → **Test, build and publish**. The workflow executes backend tests and frontend tests independently, then builds the two container images and uses real PostgreSQL for the smoke test.

Without Docker Hub settings, tests/builds still run and publishing reports a notice. The workflow performs no Azure login and sends no CI metrics or CI application telemetry to Azure.

## 6. Configure Docker Hub publication

Create these repositories under your actual Docker Hub username/organization:

- `notekeeper-backend`
- `notekeeper-frontend`

Public repositories keep this dummy lab simple. Azure deployments will eventually pull an ACR mirror using the AKS kubelet identity, so we do not put a Docker Hub pull password in pods.

Create a Docker Hub access token with the minimum repository write access available for your account. Use a token instead of your account password. Configure immutable SHA tags where your Docker Hub plan supports it. We will enforce immutability in the release checks as well.

In GitHub → Settings → Secrets and variables → Actions:

| Kind | Name | Value |
|---|---|---|
| Repository variable | `DOCKERHUB_USERNAME` | Your Docker Hub namespace, not your GitHub username unless identical |
| Repository secret | `DOCKERHUB_TOKEN` | Docker Hub access token |

Do not put Azure subscription secrets, DB passwords or Key Vault runtime secrets here. Docker Hub publishing is the CI-specific credential exception; Azure access later uses GitHub OIDC.

Rerun the main-branch workflow to publish, provided these SHA tags have not already been published. If an immutable tag already exists, preserve it; make a new commit for a new build. A release should not silently replace artifacts under an existing SHA.

Expected tags:

```text
YOUR_DOCKERHUB_USERNAME/notekeeper-backend:<full-40-character-Git-SHA>
YOUR_DOCKERHUB_USERNAME/notekeeper-frontend:<full-40-character-Git-SHA>
```

The Actions run also has a `release-<SHA>` artifact containing release.json and two digest references. These are actual registry digests, not Git SHAs and not Docker image IDs.

## 7. Protect main after the initial bootstrap commit

GitHub → Settings → Rules/Rulesets (or Branches) → protect `main`: require pull requests, passing backend-test, frontend-test and images checks, and block force pushes. Use feature branches afterward. Configure dev, staging and prod GitHub Environments during CD setup, with production reviewers and deployment branch restrictions; verify which protection features your GitHub plan offers.

## Step 1 exit criteria

- UI CRUD works at localhost:8080 and refresh/restart preserves notes.
- Backend/frontend tests and real PostgreSQL smoke test pass.
- A response exposes X-Request-Id; API validation rejects invalid input.
- Main CI can publish full-SHA tags and release.json records both digests.
- No `.env` or credentials are committed.

Next: security scanning/image hardening, then Azure subscription/bootstrap and Terraform state/OIDC. We will check quotas and costs before creating Front Door Premium or the two clusters.
