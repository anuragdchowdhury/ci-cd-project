# Step 3: publish tested images to ACR

The bootstrap/registry checkpoint is already applied in your Azure account and
the read-only OIDC check has passed. This step changes CI, not Terraform or the
existing federation subjects. It replaces the historical GHCR publisher.

## 1. Confirm registry settings

Terraform's `registry` output contains identifiers, not the security settings.
Run this Azure CLI command while signed into the subscription:

```bash
az acr show \
  --name acrnk81c108fc \
  --resource-group rg-nk-registry-ci \
  --subscription b4207b90-6a00-470a-aa95-b154c688bb74 \
  --query '{name:name,loginServer:loginServer,sku:sku.name,adminUserEnabled:adminUserEnabled,publicNetworkAccess:publicNetworkAccess,roleAssignmentMode:roleAssignmentMode}' \
  --output json
```

Expected: `Basic`, `adminUserEnabled: false`, `publicNetworkAccess: Enabled`,
`roleAssignmentMode: AbacRepositoryPermissions`, and the login server
`acrnk81c108fc.azurecr.io`. If the settings differ, inspect the Terraform plan
before publishing. Do not enable the admin user or grant registry-wide AcrPush.

The authenticated public endpoint is the agreed Basic-SKU lab compromise.
OIDC does not provide private network connectivity. An ACR Private Link setup
would require Premium and a connected runner; that is not added here.

## 2. Configure the existing publisher environment

In GitHub, open Settings → Environments → **acr-publish**. Keep its deployment
branch rule restricted to `main`. Configure these **variables**, not secrets:

| Variable | Value |
| --- | --- |
| ACR_REGISTRY_NAME | `acrnk81c108fc` |
| AZURE_PUBLISHER_CLIENT_ID | The **publisher** managed identity's client ID |
| AZURE_TENANT_ID | `133815cf-acdc-4089-a1e7-fce0de2fe1b4` |
| AZURE_SUBSCRIPTION_ID | `b4207b90-6a00-470a-aa95-b154c688bb74` |

The existing repository tenant/subscription variables can be reused instead of
duplicated. Find the publisher client ID with:

```bash
terraform -chdir=infra/bootstrap output -json configuration
```

Read `github_identities.publisher.client_id`, not `check_reader.client_id`,
`registry_infra.client_id`, or the publisher's principal ID. These output
identifiers are nonsecret. Do not upload or commit the Terraform state.

The corrected environment federation subject is reused unchanged. No client
secret, ACR admin password, or GHCR token is needed. The diagnostic check used
a different identity; its success alone did not prove the publisher can push.

## 3. Apply the PR patch

Start with a clean working tree. Download `secure-acr-ci.patch`, then:

```bash
git switch main
git pull --ff-only
git status --short
git switch -c feat/secure-acr-ci
git apply --check "$HOME/Downloads/secure-acr-ci.patch"
git apply "$HOME/Downloads/secure-acr-ci.patch"

python3 scripts/ci_tools.py check
python3 -m unittest discover -s scripts -p 'test_*.py' -v

git add .github/workflows/ci.yml .gitignore README.md \
  backend/Dockerfile frontend/Dockerfile compose.yaml ci security scripts docs
git commit -m "Publish tested SHA images to ACR with OIDC and security gates"
git push -u origin feat/secure-acr-ci
```

Use the real download location if it differs. If `git status --short` shows
unrelated changes, preserve them before applying/staging this patch. If the
patch check fails, stop and reconcile the newer main commit; do not force it.

Open a PR into protected `main`. Required checks should include `backend-test`,
`frontend-test`, `security`, `container-check`, `terraform-check (bootstrap)` and
`terraform-check (registry)`. Select the actual check names shown after the PR
runs. Do not require `images` on PRs: that main-only job is intentionally skipped.

Merge only after those checks pass and the publisher variables are configured.
No Terraform apply is required for this patch.

## 4. Understand what the workflow does

| Stage | What happens | Why |
| --- | --- | --- |
| Source security | Checks build-input pins; runs publisher regressions, scanner fixtures, frontend dependency scanning, source secret scanning and four local Semgrep rules | Practical, inspectable baseline; no Azure identity |
| Application tests | Runs backend tests with Java 21 and frontend tests/build with Node 24 | Finds application errors before publication |
| PR container check | Builds two images, starts real PostgreSQL, runs CRUD/migration smoke test, scans images | PRs cannot publish or request Azure OIDC |
| Main images job | Builds once, smoke-tests, scans the final images and generates SBOMs | The exact tested images become the release |
| OIDC login | Only after tests/scans, Azure Login federates the existing publisher identity | No stored Azure credentials |
| Registry checks/push | Checks ACR settings, existing SHA tags, out-of-scope denial; pushes only the two approved names | Verifies the permission boundary in the live registry |
| Release | Protects tags/manifests and records both digests in `release.json` | CD will promote this exact pair without rebuilding |

GitHub grants `id-token: write` at job scope, not at individual step scope. It
is confined to the trusted, main-only `images` job using `acr-publish`; the login
step runs after image checks. No PR job receives it. Review changes to workflows,
Dockerfiles and scripts through protected main.

Your repository is currently public. GitHub artifacts are downloadable by
signed-in people with repository read access, so the workflow does **not** upload
Docker image archives. Build/test/scan/push share the same main runner. Only
nonsecret findings, SBOMs and release metadata are uploaded. Those metadata
artifacts are not private merely because ACR requires authentication.

Image and Java-agent inputs are pinned in `ci/build-inputs.json` and checked
against Dockerfiles/Compose. Digests identify reviewed multi-platform base
indexes; published application images target **linux/amd64** for the AKS lab.
The frontend Nginx base moves to a pinned current stable image. Changing base
pins requires updating the input record and rerunning tests/scans through a PR.
Pinned inputs do not make all Maven/npm/apk downloads a hermetic build.

Trivy scans the frontend lock including dev dependencies. The final backend
image scan covers resolved Java dependencies and the downloaded agent. Secrets
are scanned in current source, excluding generated tool/cache/report folders;
this is not a full Git-history secret audit. Semgrep checks process execution,
concatenated query calls, dynamic JavaScript and raw HTML. These four local rules
are a baseline, not a complete application security review.

HIGH/CRITICAL vulnerabilities, secrets, Semgrep findings and scanner errors
fail the workflow. No `continue-on-error`, vulnerability ignore list or
`ignore-unfixed` bypass is configured. Low/medium findings remain in image
SBOMs/reports where supported. A finding should be fixed or explicitly assessed;
do not lower the gate simply to obtain a green build.

The scanner self-test generates disposable Java/JS unsafe code, a fake AWS key
and a lock for known-vulnerable lodash outside the app. Each must produce its
expected finding and a failing exit code. No vulnerable fixture is deployed.
Semgrep metrics are disabled; no CI metrics are sent to Azure.

The registry denial probe attempts only an empty upload session in
`notekeeper-scope-probe`. It must be denied with an authorization error. If
unexpectedly accepted, it attempts to cancel that session and fails publication;
it never uploads image data or a manifest there. Correct IAM must remain scoped
to `notekeeper-backend` and `notekeeper-frontend`.

Tag and manifest protection are applied separately. Repository Writer can edit
metadata, including protection settings, so these locks protect against mistakes
and are not an independent boundary against a compromised publisher. Deployment
identity remains the immutable digest. Signing/provenance enforcement and AKS
admission policies remain a later deployment checkpoint.

## 5. Verify the first main release

After merging, open Actions → Test and build → the main run. Expect source,
application and image checks to pass, Azure login to succeed, the scope-denial
message, both pushes, and an artifact named `release-<full-commit-sha>`.

Download it and inspect `release.json`: both tags must use the same full commit
SHA and both references must start with `acrnk81c108fc.azurecr.io/` and end with
`@sha256:<64-hex-digest>`. The examples below use actual values from that file:

```bash
az acr login --name acrnk81c108fc
docker pull --platform linux/amd64 <backend-reference-from-release.json>
docker pull --platform linux/amd64 <frontend-reference-from-release.json>
```

The human operator already has scoped Repository Reader grants from bootstrap.
Do not add Catalog Lister solely to list repositories; inspect known names:

```bash
az acr repository show --name acrnk81c108fc --image notekeeper-backend:<full-sha>
az acr repository show --name acrnk81c108fc --image notekeeper-frontend:<full-sha>
```

Backend/frontend publication is not a registry transaction. If one push succeeds
and the other fails, no successful release artifact is emitted and CD must not
deploy the partial pair. A different rebuild under an existing SHA is refused.
Because image archives are not retained, use a new commit for a fresh release
if a failed main-job rerun would produce different image IDs; never delete or
overwrite a protected SHA merely to retry. Preserve successful release manifests.

Reports retain 14 days and release metadata 90 days in GitHub. ACR image lifecycle
is separate; there is no automatic purge of promoted releases in this step.
Private production release-record retention is addressed with CD.

## Next training checkpoint

Once the ACR release and authenticated digest pulls pass, provision the Azure
network/platform: shared dev/staging AKS, separate prod AKS, PostgreSQL, Key Vault,
scoped identities and private runner connectivity. Then Helm/CD, Front Door
Premium, ingress and DNS; telemetry/DCR/retention; alerts/drills; recovery/cleanup.

Sources: https://learn.microsoft.com/azure/container-registry/container-registry-rbac-abac-repository-permissions
and https://learn.microsoft.com/azure/container-registry/container-registry-image-lock;
https://docs.github.com/en/actions/how-tos/manage-workflow-runs/download-workflow-artifacts;
https://trivy.dev/docs/latest/ and https://docs.semgrep.dev/running-rules.
