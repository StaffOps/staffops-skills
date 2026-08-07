---
name: load-balancer-troubleshooting
description: Use when debugging ALB/NLB/ingress controller target group issues — 502/503/504 errors, failing health checks, connection draining problems, cross-AZ traffic costs, sticky sessions, or TLS termination failures. Decision tree organized by HTTP error code.
---

# Load Balancer Troubleshooting

## When to use

- HTTP 502/503/504 errors originating from the load balancer (not the app)
- Target group health checks failing despite pods being healthy
- Connections dropping during deployments (rolling updates)
- Unexpected cross-AZ data transfer costs
- Sticky session not working (requests going to different backends)
- TLS/SSL handshake failures at the LB layer
- Ingress controller not routing correctly

## When NOT to use

- Application returns 5xx from its own code (check app logs first)
- DNS resolution failures (check Route53/CoreDNS)
- Service mesh routing issues (use service-mesh-troubleshooting)
- Pod scheduling failures or OOMKills (K8s workload issue)

---

## Step 1: Identify where the error originates

```bash
# Check if the LB itself generates the error (vs forwarding from backend)
# ALB access logs: elb_status_code vs target_status_code
# If elb_status_code=502 AND target_status_code=- → LB couldn't reach backend

# Check ingress controller logs
kubectl logs -l app.kubernetes.io/name=ingress-nginx -n ingress-nginx --tail=100

# Check ALB target group health
aws elbv2 describe-target-health \
  --target-group-arn <target-group-arn> \
  --query 'TargetHealthDescriptions[?TargetHealth.State!=`healthy`]'
```

---

## Step 2: Decision tree by HTTP error code

### 502 Bad Gateway

LB received an invalid response from the backend.

```bash
# 1. Backend pod crashed/restarting during request
kubectl get pods -n <ns> -o wide | grep -v Running

# 2. Keep-alive mismatch (backend timeout < LB timeout)
# ALB default idle timeout: 60s — backend must be > 60s

# 3. Response too large for buffer
kubectl logs <ingress-pod> | grep "upstream prematurely closed"

# 4. Backend returned malformed HTTP
kubectl exec <pod> -- curl -v http://localhost:<port>/health
```

| Cause | Fix |
|-------|-----|
| Pod restarting mid-request | Add preStop hook + increase terminationGracePeriod |
| Keep-alive mismatch | Set backend keep-alive timeout > LB idle timeout |
| Response body too large | Increase `proxy-body-size` in ingress annotation |
| Malformed response | Fix app (missing Content-Length, chunked encoding) |

### 503 Service Unavailable

No healthy targets to forward to.

```bash
# Check target group has healthy targets
aws elbv2 describe-target-health --target-group-arn <arn>

# Check health check path returns 200
kubectl exec <pod> -- curl -s -o /dev/null -w "%{http_code}" http://localhost:<port>/healthz

# Check if readiness probe failing (removes from endpoints)
kubectl describe pod <pod> | grep -A5 "Readiness"
kubectl get endpoints <service> -n <ns>
```

| Cause | Fix |
|-------|-----|
| All targets unhealthy | Fix health check path/port or fix the app |
| Security group blocks health check | Allow LB CIDR on health check port |
| Readiness probe failing | Fix probe or increase initialDelaySeconds |
| Target group empty | Check service selector matches pod labels |
| All targets draining | Reduce deregistration delay or increase replicas |

### 504 Gateway Timeout

Backend didn't respond within the timeout.

```bash
# Check LB idle timeout
aws elbv2 describe-load-balancer-attributes \
  --load-balancer-arn <arn> \
  --query 'Attributes[?Key==`idle_timeout.timeout_seconds`]'

# Check if backend is actually slow
kubectl exec <client-pod> -- curl -o /dev/null -s -w "time_total: %{time_total}\n" \
  http://<service>:<port>/slow-endpoint
```

| Cause | Fix |
|-------|-----|
| Backend genuinely slow | Optimize endpoint or increase timeout |
| LB timeout too low | Increase idle timeout (max 4000s ALB) |
| Connection pool exhausted | Scale backend or increase connection limits |
| Network partition (cross-AZ) | Check subnet routing, NACLs |

---

## Step 3: Health check failures

```bash
# Verify health check config matches app
aws elbv2 describe-target-groups --target-group-arns <arn> \
  --query 'TargetGroups[].{Path:HealthCheckPath,Port:HealthCheckPort,Protocol:HealthCheckProtocol}'

# Test health check from within the cluster
kubectl run hc-test --rm -i --restart=Never --image=curlimages/curl:latest -- \
  curl -v http://<pod-ip>:<health-check-port><health-check-path>
```

| Parameter | Aggressive (fast failover) | Conservative (stable) |
|-----------|---------------------------|----------------------|
| Interval | 5s | 30s |
| Timeout | 2s | 10s |
| Healthy threshold | 2 | 3 |
| Unhealthy threshold | 2 | 3 |

---

## Step 4: Connection draining during deployments

```bash
# Check deregistration delay
aws elbv2 describe-target-group-attributes \
  --target-group-arn <arn> \
  --query 'Attributes[?Key==`deregistration_delay.timeout_seconds`]'
```

Pod termination sequence:
1. Pod marked Terminating → removed from Endpoints
2. LB health check fails → stops sending NEW traffic
3. preStop hook runs → sleep gives in-flight requests time
4. SIGTERM sent → app gracefully shuts down

```yaml
spec:
  terminationGracePeriodSeconds: 60
  containers:
  - lifecycle:
      preStop:
        exec:
          command: ["sh", "-c", "sleep 15"]
```

**Rule**: `preStop sleep` ≥ LB health check interval × unhealthy threshold

---

## Step 5: Cross-AZ traffic and costs

```bash
# Check cross-zone load balancing setting
aws elbv2 describe-load-balancer-attributes \
  --load-balancer-arn <arn> \
  --query 'Attributes[?Key==`load_balancing.cross_zone.enabled`]'

# Check target distribution across AZs
aws elbv2 describe-target-health --target-group-arn <arn> \
  --query 'TargetHealthDescriptions[].{AZ:Target.AvailabilityZone,State:TargetHealth.State}'
```

| Setting | Behavior | Cost impact |
|---------|----------|-------------|
| Cross-zone enabled (ALB default) | Even distribution across all targets | Inter-AZ charges |
| Cross-zone disabled | Traffic stays in same AZ | Uneven load if fewer targets in AZ |

---

## Step 6: TLS termination issues

```bash
# Check certificate on ALB
aws elbv2 describe-listener-certificates --listener-arn <listener-arn>

# Test TLS handshake externally
openssl s_client -connect <lb-dns>:443 -servername <hostname> </dev/null 2>&1 | \
  grep -E "(subject|issuer|Verify)"
```

| Symptom | Cause | Fix |
|---------|-------|-----|
| `SSL_ERROR_HANDSHAKE_FAILURE` | No cert for SNI hostname | Add cert to listener |
| `ERR_CERT_DATE_INVALID` | Certificate expired | Renew (auto-renew if DNS validated) |
| Mixed content warnings | HTTP links on HTTPS | Handle `X-Forwarded-Proto` |
| 408 after TLS handshake | Client TLS version incompatible | Update security policy |

---

## Anti-patterns

- ❌ Setting LB idle timeout to 3600s "just in case" — hides real issues
- ❌ Health check on `/` (expensive page) — use lightweight `/healthz`
- ❌ No preStop hook — causes 502 during deployments
- ❌ Sticky sessions for stateless services — adds complexity without benefit
- ❌ Cross-zone enabled on high-throughput internal LBs — hidden inter-AZ costs
- ❌ TLS at BOTH LB and backend without reason — double CPU cost
- ❌ Health check timeout > interval — invalid configuration

---

## Related skills

- `service-mesh-troubleshooting` — routing issue inside the mesh, not at LB
- `eks-node-troubleshooting` — targets unhealthy due to node issues
- `ingress-nginx-metrics` — NGINX ingress controller metrics
- `aws-load-balancer-controller-metrics` — ALB controller health
- `incident-triage` — structured approach to production LB incidents
