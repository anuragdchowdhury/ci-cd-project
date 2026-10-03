# Step 7 — run drills, interpret evidence and recover

Finish Step 6 first: ready API, trusted origin/public TLS, working Grafana, real metric/log/trace ingestion and configured action group. Run one case at a time. These are training faults in Dev, not production load tests. No test grants subscription-wide workload access, adds nodes or exposes public fault endpoints. Terraform drift uses a resource-group tag only.

## Start a private operator session

Start the VM and SSH using Step 6. In the checked-out repository, open a subshell with disposable operator Azure login/kubeconfig; use Step 6's credential cleanup trap and `az aks get-credentials`/`kubelogin` commands. Operator authority is needed for the isolated scenario namespace and ingress; the ordinary CD identity remains Dev-namespace scoped.

For traffic drills, forward directly to the backend **pod** so readiness/DB faults do not reroute requests away from the diagnostic workload:

```bash
kubectl -n notekeeper-dev port-forward deployment/notekeeper-api 8080:8080 --address 127.0.0.1 > "$HOME/notekeeper-forward.log" 2>&1 &
FORWARD_PID=$!
```

A fault/sampling change causes a rollout and kills that pod's forwarding session. For normal HTTP drills use `service/frontend` forwarding instead, which also needs restarting after its selected pod changes. The simplest repeatable option is to generate traffic through the public URL from your **laptop's allowed IP**, while executing the fault change on the VM. For the self-contained script, use frontend forwarding on the VM and inspect/restart if requests become network errors. Network errors are not proof of API HTTP 500/latency.

**Recommended self-contained local drill:** use a stable local Service proxy that survives backend rollout:

```bash
kill "$FORWARD_PID" 2>/dev/null || true
kubectl -n notekeeper-dev port-forward service/frontend 8080:8080 --address 127.0.0.1 > "$HOME/notekeeper-forward.log" 2>&1 &
FORWARD_PID=$!
python3 scripts/lab_scenarios.py --scenario baseline --seconds 180 --rate 5
```

The frontend pod is unchanged by backend fault/sampling rollouts, and Nginx proxies to the backend Service. Wait for the forwarding listener before generating traffic. For the SQL lock drill specifically, use a direct backend pod forward after sampling is already set; database-readiness changes can remove backend Service endpoints. Kill the forwarding PID at session end. Do not run CD concurrently with a drill.

## Automated drills

The script accepts at most 300 seconds, 20 total requests/second and eight workers. It performs read-only note listing, captures status counts/client p95 and up to ten **actual** X-Trace-Id/X-Request-Id pairs, and writes ignored `reports/scenario-*.json`. Application fault scenarios temporarily set 100% Java trace sampling, wait for rollout and restore original settings in `finally`. Fixtures are deleted in `finally`. Ctrl+C invokes cleanup; a killed VM/process cannot, so the recovery commands below remain necessary.

```bash
python3 scripts/lab_scenarios.py --scenario error --seconds 180 --rate 5
python3 scripts/lab_scenarios.py --scenario latency --seconds 180 --rate 5
python3 scripts/lab_scenarios.py --scenario cpu --seconds 300 --rate 20 --workers 8
python3 scripts/lab_scenarios.py --scenario crashloop --seconds 240
python3 scripts/lab_scenarios.py --scenario oom --seconds 240
python3 scripts/lab_scenarios.py --scenario pending --seconds 180
python3 scripts/lab_scenarios.py --scenario db-auth --seconds 180
python3 scripts/lab_scenarios.py --scenario db-latency \
  --platform "$HOME/dev-platform.json" --seconds 30 --rate 5 --workers 8
python3 scripts/lab_scenarios.py --scenario readiness --seconds 180
python3 scripts/lab_scenarios.py --scenario api-down --seconds 180
python3 scripts/lab_scenarios.py --scenario origin-down --seconds 300
```

Run these sequentially with recovery/evidence review between cases, not pasted as an unattended batch. The SQL lock is bounded to 15 seconds with a 20-second statement timeout and is released on session termination; it cannot prove a sustained two-minute pool alert. Use a disposable longer lock only after confirming the first drill and manually reviewing a bounded query; do not extend locks blindly on a shared database. `db-auth` copies the image/runtime configuration into a differently labeled isolated pod with an unregistered DB username; it does not revoke the working API's SQL grants. It strips trace ingestion from that fixture to avoid noisy startup telemetry.

| Drill | Evidence / implemented alert | Interpretation |
|---|---|---|
| Baseline | Request rate, normal p95, successful AppRequests and SQL dependencies | Establish normal values first; no fault alert expected |
| Error | ApiErrors: >5% HTTP 5xx for two minutes; container error alert ≥5 errors/5 minutes | HTTP 500 is emitted before SQL, so this request need not have a DB dependency |
| Latency | ApiLatency: histogram p95 >1 second for two minutes | 1.5-second application delay: long server span, normal SQL child duration |
| CPU | CpuSaturation: API >0.8 CPU core for two minutes | Workload limit, actual available CPU and five-minute rate window matter; a bounded run may show pressure without crossing threshold |
| Crashloop | PodRestarts: >2 restarts within ten minutes, held one minute | Separate fixture; repeated start/exit and BackOff events; no HTTP trace is expected |
| OOM | Restart panel, previous termination OOMKilled; PodRestarts after enough repeats | Kernel may kill before a final application log/trace; inspect termination reason |
| Pending | PodPending: one lab fixture Pending for two minutes | Nonexistent node label, not quota exhaustion; scheduler FailedScheduling event |
| DB authentication | Startup/auth error in isolated fixture; restart evidence | Entra authentication + SQL role registration are separate; normal app keeps working |
| DB latency/pool | SQL child duration rises; Hikari pending/timeout can rise; DbPoolWait requires two minutes | Compare this actual dependency bottleneck with application-only latency; the 15-second drill does not guarantee an email |
| Readiness | ApiNotReady: API pod readiness zero for two minutes | New unready pod can coexist with an old healthy replica; availability may be preserved by rollout |
| API down | ApiDown: failed/absent scrape for two minutes; frontend API errors | Zero replicas gives no target; restored count triggers recovery |
| Origin down | Front Door OriginHealthPercentage <80%/five minutes | Traefik zero replicas; public probe/requests fail, app may remain healthy behind the origin |

Thresholds and rule IDs are defined in `infra/modules/platform/observability.tf` and `infra/edge/main.tf`. Alert evaluation runs every minute (container query every five minutes), with range windows/hold periods and ingestion latency. A short drill need not satisfy them. Every implemented rule routes to `ag-nk-dev-lab` email `anuragdchowdhury.mail@gmail.com`; Prometheus alerts auto-resolve after their configured recovery period. Capture Azure Monitor → Alerts Fired/Resolved, the rule resource ID, measured query, time window and email timestamps. The table describes **expected evidence**, not already-executed Azure results.

NodeNotReady and PostgreSQL CPU >80%/five minutes are also configured. Do not kill a shared system node or burn database CPU just to force mail. Test the action group with Portal → Action groups → Test, then separately verify those rules' actual healthy series/metric criteria. A notification test validates delivery, not a real NodeNotReady/PostgreSQL threshold firing. Cordoning a node makes it unschedulable, not NotReady. Node autoscaling/HPA saturation are intentionally absent in this fixed-node lab; do not fabricate their outputs. Any destructive node/restore exercise needs its own maintenance plan and quota check.

## Read RED correctly

In Grafana's NoteKeeper RED dashboard:

```promql
sum(rate(http_server_requests_seconds_count{job="notekeeper-api"}[5m]))
sum(rate(http_server_requests_seconds_count{job="notekeeper-api",status=~"5.."}[5m]))
  / clamp_min(sum(rate(http_server_requests_seconds_count{job="notekeeper-api"}[5m])),0.001)
histogram_quantile(0.95,sum by(le)(rate(http_server_requests_seconds_bucket{job="notekeeper-api"}[5m])))
sum(hikaricp_connections_pending{job="notekeeper-api"})
```

Rate is requests/second, errors are a ratio, duration is server-side seconds. Client p95 includes proxies/network; it need not equal server histogram p95. Compare request volume and time windows before concluding that latency or errors regressed. CPU includes container execution and is different from throttling. Use Grafana Explore for `container_cpu_cfs_throttled_seconds_total` if present in the default managed minimal collection; do not assume every cAdvisor metric is retained. Heap/GC/Hikari charts use the one management scrape; agent metric export remains disabled.

## Trace → logs → SQL correlation

Enable drill INFO logs through Step 6's reviewed DCR transform update. Use a trace ID captured by the script or a real browser response. Find AppRequests.OperationId in the backend resource, then inspect its AppDependencies with matching OperationId and parent IDs. Browser dependency and backend request should share W3C context; the browser's separate resource does not mean a separate trace.

```kusto
let trace_id = "PASTE_ACTUAL_32_HEX_TRACE_ID";
union AppRequests, AppDependencies
| where OperationId == trace_id
| project TimeGenerated, Type, OperationId, ParentId, Name, DurationMs, Success
| order by TimeGenerated asc
```

```kusto
ContainerLogV2
| where PodNamespace == "notekeeper-dev"
| extend p=parse_json(tostring(LogMessage))
| where tostring(p.traceId) == "PASTE_ACTUAL_32_HEX_TRACE_ID"
| project TimeGenerated, PodName, level=tostring(p.level), requestId=tostring(p.requestId), LogMessage
```

Query the shared LAW or Grafana correlation dashboard. Do not paste `X-Request-Id` into an OperationId filter: request IDs and trace IDs differ. Head sampling at 10% deliberately omits most normal traces; restart to 100% for a bounded manual SQL/browser exercise, then restore. WAF blocks, Pending pods and pre-start failures legitimately have no backend trace. The agent's log exporter is disabled: normal successful correlation requires temporary INFO log collection, whereas error logs survive the normal filter.

If tables or rows are absent, verify time range, workspace, sampling, ingestion delay, Java agent activation/egress and daily quota before drawing conclusions. Do not invent trace IDs or sample screenshots. Save sanitized real results and identify expected versus observed outcomes.

## WAF and scoped-access training

From a network outside the allowed operator IP, make one request to your Dev host: expect a WAF 403 and a FrontDoorWebApplicationFirewallLog entry. A VPN changes source IP; avoid accidentally locking yourself out. Restore your ordinary network or update the edge IP through a reviewed plan. This exercises the explicit OperatorOnly rule without attack traffic. Inspect Front Door → Metrics and LAW dedicated Front Door tables for origin health, access status and block evidence. No backend trace is expected for a request rejected at WAF.

For Key Vault, inspect runtime CSI mount success and Azure role scope. To demonstrate denial, execute from an isolated pod with no federated service account/identity and attempt obtaining a vault token: token exchange must fail; that is **identity failure**, not a Key Vault audit denial. For a real vault RBAC denial, use an authenticated lab identity that has no Secrets User role on this vault and make one read of the nonsecret lab-message; inspect AZKVAuditLogs. Do not revoke the working runtime role or request production secrets. DNS certificate renewal uses cert-manager Events/Certificate status; inspect the issued NotAfter and renewalTime rather than expiring the active origin certificate.

Image-vulnerability training already exists in CI's scanner unsafe-fixture self-test; it rejects the fixture rather than publishing it. No GitHub build metrics are collected. ACR Basic registry audit capabilities differ from higher SKUs; this bundle does not claim a registry audit alert or silently upgrade ACR. Full expiry automation/Event Grid, active heap pressure, destructive node/PV failures, isolated database restore and sustained pool/DB CPU load are advanced extensions, not falsely reported completed exercises. The working lab's core request/error/latency/load/crash/OOM/Pending/auth/drift/edge scenarios are ready in this PR.

## Terraform drift

On the VM with operator login, or laptop:

```bash
python3 scripts/lab_scenarios.py --scenario drift --platform infra/.generated/dev-platform.json
```

On the VM the platform path is `$HOME/dev-platform.json`. Then on the laptop:

```bash
terraform -chdir=infra/nonprod plan \
  -var-file=../.generated/nonprod.auto.tfvars.json \
  -var-file=../.generated/access.auto.tfvars.json \
  -var-file=../.generated/lab.auto.tfvars.json -out=drift.tfplan
terraform -chdir=infra/nonprod show -no-color drift.tfplan
terraform -chdir=infra/nonprod apply drift.tfplan
```

Expected: an in-place resource-group tag correction only, no resource resize/replacement. Do not apply if the plan proposes unrelated changes. A subsequent plan with the same inputs must return No changes. Terraform plan is the drift evidence; Grafana does not automatically alert on arbitrary Terraform drift.

## Recovery after interruption

```bash
kubectl -n notekeeper-dev set env deployment/notekeeper-api \
  LAB_FAULT_MODE=none APPLICATIONINSIGHTS_SAMPLING_PERCENTAGE=10
kubectl -n notekeeper-dev scale deployment/notekeeper-api --replicas=1
kubectl -n ingress-system scale deployment/traefik --replicas=1
kubectl -n lab-scenarios delete deployment lab-crashloop lab-oom lab-pending --ignore-not-found
kubectl -n notekeeper-dev delete deployment lab-db-auth --ignore-not-found
kubectl -n notekeeper-dev rollout status deployment/notekeeper-api --timeout=180s
```

A readiness patch interruption is restored by redeploying the same successful SHA through Deploy Dev (Helm reasserts the chart's readiness probe and original config); do not guess the probe from memory. If a SQL session survived, identify **only** the marked lock session in pg_stat_activity and terminate that session as operator, rather than killing unrelated connections. Stop local forwards, restore normal DCR filtering through its saved plan, remove drift through Terraform, verify `/` + `/api`, and wait for alerts to resolve. Keep the VM credential-cleanup trap and deallocate it after the session.

For each exercise save: trigger/time, actual metric/query, real trace/request IDs if applicable, relevant container/event evidence, rule ID + Fired/Resolved/email or explicit reason it did not fire, recovery confirmation and cleanup. A script completing alone does not prove every downstream signal arrived.
