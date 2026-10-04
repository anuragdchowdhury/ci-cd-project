# Recover Dev CD custom-resource authorization

Helm can fail reading `SecretProviderClass/notekeeper-vault` because AKS RBAC Writer only covers enumerated standard resources. Add a supplementary custom role with `customresources/read`, `write`, and `delete`, assigned to the Dev deployer at the existing `notekeeper-dev` namespace scope. This covers all namespaced custom-resource kinds in Dev, not only SecretProviderClass. It does not grant cluster-scoped CRD-definition management, Kubernetes RBAC management, other namespaces, or additional Key Vault/ACR permissions. Kind filtering with Azure ABAC is currently preview and is intentionally not enabled for this lab.

References: [AKS authorization](https://learn.microsoft.com/en-us/azure/aks/entra-id-authorization) and [ContainerService permissions](https://learn.microsoft.com/en-us/azure/role-based-access-control/permissions/containers).

After merge, use the original Terraform operator checkout containing all three generated input files. A checkout with only exported deployment JSON files is insufficient: do not plan with missing inputs.

```bash
git switch main
git pull --ff-only
terraform -chdir=infra/nonprod plan \
  -var-file=../.generated/nonprod.auto.tfvars.json \
  -var-file=../.generated/access.auto.tfvars.json \
  -var-file=../.generated/lab.auto.tfvars.json \
  -out=dev-cr-access.tfplan
terraform -chdir=infra/nonprod show -no-color dev-cr-access.tfplan
```

Expected: two additions (custom role definition and Dev namespace assignment), no existing changes/destruction. Review the actual complete plan before applying:

```bash
terraform -chdir=infra/nonprod apply dev-cr-access.tfplan
```

Allow role propagation, then dispatch a new workflow on current main (rerunning an old run uses its old workflow commit). Preserve the already-verified application release and its image digests:

```bash
gh workflow run deploy-dev.yml --repo anuragdchowdhury/ci-cd-project \
  --ref main -f release_sha=b7b8ecebdcfc2bdbf07f279269c62873e73063bf
```

Require `NOTEKEEPER_DEPLOY_OK` with that SHA. Helm's first atomic rollback also encountered the same permission denial, so do not assume application health or a successful rollback from the failed run. If the retry reports a pending Helm operation, inspect release status/history before taking recovery action; do not delete the release or Helm state blindly. CD deallocates the executor VM after its attempt.
