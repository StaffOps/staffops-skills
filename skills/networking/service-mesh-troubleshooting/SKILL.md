---
name: service-mesh-troubleshooting
description: Use when debugging service mesh issues — mTLS failures, sidecar injection problems, traffic policy misroutes, proxy latency overhead, or config sync delays. Covers Istio, Linkerd, and Consul Connect. Decision tree to isolate mesh vs application problems.
---

# Service Mesh Troubleshooting

## When to use

- Requests fail ONLY when mesh sidecar is injected (work fine without it)
- mTLS handshake errors between services
- Sidecar not injecting into pods
- Traffic routing not matching VirtualService/TrafficSplit rules
- Unexpected latency introduced after mesh enrollment
- 503 errors with `upstream connect error or disconnect/reset before headers`
- Certificate expiry or rotation failures in mesh PKI

## When NOT to use

- Application-level bugs unrelated to networking (debug the app)
- DNS resolution failures (check CoreDNS)
- Load balancer or ingress issues outside the mesh (use load-balancer-troubleshooting)
- Container image pull failures or OOMKills (K8s workload issue)

---

## Step 1: Isolate — Is it the mesh or the application?

### Quick bypass test

```bash
# Temporarily disable sidecar for a single pod (Istio)
kubectl annotate pod <pod> sidecar.istio.io/inject="false" --overwrite
kubectl delete pod <pod>  # recreate without sidecar

# Linkerd — remove injection annotation
kubectl annotate pod <pod> linkerd.io/inject="disabled" --overwrite
kubectl delete pod <pod>
```

If the problem **disappears** without the sidecar → mesh issue.
If the problem **persists** → application issue (stop here, debug the app).

### Check proxy logs

```bash
# Istio — envoy access logs
kubectl logs <pod> -c istio-proxy --tail=100

# Linkerd — proxy logs
kubectl logs <pod> -c linkerd-proxy --tail=100

# Consul Connect — envoy sidecar
kubectl logs <pod> -c envoy-sidecar --tail=100
```

Key envoy response flags:
- `NR` — no route configured for request
- `UF` — upstream connection failure
- `UC` — upstream connection termination
- `UO` — upstream overflow (circuit breaker)
- `DPE` — downstream protocol error

---

## Step 2: Sidecar injection failures

```bash
# Check namespace label (Istio)
kubectl get namespace <ns> -o jsonpath='{.metadata.labels.istio\.io/dataplane-mode}'
kubectl get namespace <ns> -o jsonpath='{.metadata.labels.istio-injection}'

# Verify webhook exists and is active
kubectl get mutatingwebhookconfiguration | grep -i istio

# Check webhook endpoint is reachable
kubectl get endpoints -n istio-system istiod

# Check for explicit opt-out annotations
kubectl get pod <pod> -o jsonpath='{.metadata.annotations}' | grep -i inject
```

| Cause | Fix |
|-------|-----|
| Namespace missing injection label | `kubectl label ns <ns> istio-injection=enabled` |
| Pod has `sidecar.istio.io/inject: "false"` | Remove the annotation |
| Webhook certificate expired | Restart istiod / injector pod |
| Webhook failurePolicy=Ignore | Errors silently skipped — check webhook logs |
| Resource limits prevent sidecar scheduling | Increase pod resource requests |

---

## Step 3: mTLS and certificate issues

```bash
# Istio — check mTLS status between services
istioctl authn tls-check <pod>.<ns> <dest-svc>.<dest-ns>.svc.cluster.local

# Check cert expiry inside proxy
istioctl proxy-config secret <pod> -n <ns>

# Linkerd — check identity
linkerd identity <pod> -n <ns>

# Manual cert inspection
kubectl exec <pod> -c istio-proxy -- \
  openssl s_client -connect <dest-svc>:443 -showcerts 2>/dev/null | \
  openssl x509 -noout -dates -subject
```

| Error | Cause | Fix |
|-------|-------|-----|
| `CERTIFICATE_VERIFY_FAILED` | CA mismatch between services | Verify same trust domain |
| `certificate expired` | Cert rotation failed | Restart istiod, check cert-manager |
| `connection reset` on port 15012 | istiod unreachable | Check istiod health + network policies |
| Plaintext to mTLS port | Client not in mesh | Use PeerAuthentication PERMISSIVE |

---

## Step 4: Traffic policy misroutes

```bash
# Istio — dump routing config for a proxy
istioctl proxy-config routes <pod> -n <ns> -o json

# Check which VirtualService applies
istioctl analyze -n <ns>

# Verify destination rule exists
kubectl get destinationrules -n <ns>

# Linkerd — check traffic split
kubectl get trafficsplit -n <ns> -o yaml
```

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| All traffic to v1 despite canary | VirtualService not bound to gateway | Check `hosts` and `gateways` fields |
| 404 on existing path | Route prefix mismatch (trailing slash) | Compare route `match.uri` with request |
| Timeout despite healthy backend | Aggressive timeout/retry config | Check VirtualService timeout value |
| Traffic not splitting by weight | Subset labels mismatch | Verify DestinationRule subsets match pods |

---

## Step 5: Latency overhead diagnosis

```bash
# Measure through mesh
kubectl exec <client-pod> -c app -- \
  curl -o /dev/null -s -w "time_total: %{time_total}s\n" http://<service>:<port>/health

# Measure bypassing mesh (direct pod IP)
POD_IP=$(kubectl get pod <target> -o jsonpath='{.status.podIP}')
kubectl exec <client-pod> -c app -- \
  curl -o /dev/null -s -w "time_total: %{time_total}s\n" http://$POD_IP:<port>/health
```

If mesh adds >10ms consistently:

| Overhead source | Fix |
|----------------|-----|
| Access logging on every request | Disable or sample access logs |
| Complex AuthorizationPolicy evaluation | Simplify rules, reduce policy count |
| Proxy CPU starved | Increase sidecar CPU requests |
| Too many active connections per proxy | Tune `maxConnections` in DestinationRule |

---

## Decision tree

```
Request failing?
├── Remove sidecar → still fails? → APP ISSUE (not mesh)
├── Remove sidecar → works? → MESH ISSUE
│   ├── Proxy logs show NR (no route)?
│   │   └── Check VirtualService/DestinationRule config
│   ├── Proxy logs show UF (upstream failure)?
│   │   └── Check target pod health + port
│   ├── TLS handshake error?
│   │   └── Check mTLS mode + cert expiry
│   ├── 503 with "no healthy upstream"?
│   │   └── Check endpoint discovery + health checks
│   └── Timeout (no response)?
│       └── Check timeout/retry config + proxy resources
└── Sidecar not present at all?
    └── Check injection webhook + namespace labels
```

---

## Anti-patterns

- ❌ Disabling mTLS globally "because it's easier" — use PERMISSIVE per-service
- ❌ Setting retries to 10+ without considering amplification during outages
- ❌ Adding mesh to every namespace including batch/cron jobs that don't need it
- ❌ Debugging app code when proxy logs clearly show routing failure
- ❌ Ignoring `istioctl analyze` warnings as "informational"
- ❌ Running mesh control plane without resource limits (OOM under load)

---

## Related skills

- `load-balancer-troubleshooting` — issue at ingress/LB layer, not mesh
- `istio-ambient-debugging` — Istio Ambient-specific (ztunnel, waypoint)
- `root-cause-analysis` — structured RCA after isolating the component
- `alerting-strategy` — designing mesh-aware alerts
