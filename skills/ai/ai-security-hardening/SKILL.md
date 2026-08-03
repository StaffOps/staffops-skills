---
name: ai-security-hardening
description: "Harden the inference host: weight theft, DoS, CIS baseline."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [ai, security, hardening, infrastructure, inference, exfiltration, denial-of-service, cis]
    category: ai
    related_skills: [prompt-injection-defense, ai-agent-security, mcp-server-security, model-registry-governance, golden-ami-creation, llm-cost-optimization, llm-app-security]
---
# AI Security Hardening

Infrastructure- and deployment-layer hardening for the systems an LLM or
agent runs on top of, distinct from the application-layer concerns three
siblings already own: **`prompt-injection-defense`** owns defending against
manipulated instructions arriving inside content the model reads,
**`ai-agent-security`** owns bounding what an agent's tools/permissions let
it do once it acts (including exfiltration *through* an agent's own read+write
capability), and **`mcp-server-security`** owns the MCP wire protocol --
transport, tool authorization, tool-output injection. None of the three says
anything about the host, network, or filesystem the model process itself
runs on -- that gap, specifically for a self-hosted or agent-serving
inference deployment, is this skill's entire scope. If the question is "can
this agent be tricked" or "can this tool call do too much," go to one of
those three; if it is "can someone steal the weights off this box" or
"can a crafted request take the inference server down for everyone," it is
this one.

## When to Use

- Standing up or reviewing a self-hosted model-serving deployment (an
  inference host, a GPU node pool, a serving framework instance) and asking
  what infrastructure controls belong around it, as opposed to what the
  application calling it should do.
- A team proposes exposing an inference endpoint beyond a single trusted
  network segment and needs to reason about network- and host-level blast
  radius, not prompt-level risk.
- Reviewing whether an inference host's network egress, filesystem
  permissions, or patch posture would actually stop someone with host
  access from copying the model weights out.
- An inference service has had, or could plausibly have, an availability
  incident caused by a small number of oversized or malformed requests
  rather than by traffic volume in the ordinary sense.
- Not for reviewing prompt content, agent tool scope, or MCP transport --
  see the three siblings named above for those.

## 1. Model weight exfiltration: the threat is host access, not clever prompts

Every AI security conversation defaults to output-side concerns -- can the
model be tricked into saying something it shouldn't, can an agent be tricked
into acting on bad input. Weight exfiltration is a different attacker with a
different goal entirely: someone who already has (or gains) access to the
box a self-hosted model runs on, and who wants the checkpoint file itself,
not anything the model says in response to a prompt. Query-based model
extraction -- reconstructing a model's behavior by hammering its API with
inputs and studying outputs -- is a real but separate problem that lives
closer to `ai-agent-security`'s output-path thinking; this section is about
someone with shell, storage, or network access to the serving host reading
or copying the weights file directly.

**Filesystem permissions on checkpoint files.** The model file should be
readable only by the UID/service account the serving process runs as, never
world-readable, and never sitting on a volume mounted into other workloads
on the same node "for convenience." A checkpoint is functionally a secret
the same way a private key is -- the fact that it is many gigabytes instead
of a few kilobytes does not change the permission model it deserves.

**Egress controls on the inference host itself.** A model checkpoint is
large -- gigabytes to tens of gigabytes -- and a sustained large outbound
transfer from an inference node is not a shape of traffic that node should
ever produce during normal operation (normal operation is small requests
in, small-to-medium generated text out). Deny-by-default egress from the
inference host, scoped to only the destinations serving actually needs (the
model artifact store to pull the checkpoint at startup, the telemetry
collector, nothing else broad), turns "copy the weights to an external
host" from a single `scp`/`curl` into something that has to first defeat a
network control. Alert on egress volume from inference nodes specifically --
a multi-gigabyte outbound transfer is anomalous there in a way it would not
be from, say, a general file-server host.

**No general-purpose interactive access.** An inference host is
infrastructure, not a developer sandbox -- no standing SSH access for
convenience, bastion-only with session recording if access is ever needed,
same principle `golden-ami-creation`'s hardened AMI already applies to any
production instance (`PermitRootLogin no`, key-only auth, audit rules on
`/etc/passwd`-class files). Apply it here for the same reason: every
additional principal with shell access to the box is one more path to the
checkpoint file that a purely network-level or filesystem-level control
cannot see.

**Detection, not prevention: tie back to `model-registry-governance`'s
signing.** None of the controls above are airtight -- a sufficiently
privileged insider or a sufficiently deep host compromise can still get the
bytes out. What closes the loop after the fact is provenance:
`model-registry-governance` already covers signing a self-hosted
checkpoint's digest with `cosign sign-blob` and recording that signature
alongside the registry entry. That signature does not stop a copy from
happening, but it gives a specific, verifiable fingerprint (the exact digest
that was signed and registered) to check against if a checkpoint file turns
up somewhere it has no business being -- a public bucket, an external host,
an unaffiliated repository. A signed weights file matching a registered
digest showing up outside its authorized deployment is evidence of
exfiltration, in exactly the way a signed container image appearing in an
unauthorized registry would be. Prevention lives in this section's host and
network controls; detection lives in that registry entry.

## 2. Resource-exhaustion / DoS hardening specific to LLM inference

A conventional stateless HTTP API has roughly uniform per-request cost --
one request is one row read, one row written, and rate-limiting by request
count alone is usually sufficient. An LLM inference server does not have
that property: a request's cost is a function of its **input context length
and requested output length**, not just its existence, and that cost curve
can be extremely steep. A handful of requests each carrying a near-maximum
context window, or each requesting a large `max_tokens` generation, can
consume enough GPU memory and compute time to stall the server's entire
batch for every other caller -- a volume of traffic that would be
completely unremarkable against a typical REST endpoint. This is an
availability problem with a shape unique to inference workloads, and it is
worth being explicit that it is **not** the same lever `llm-cost-optimization`
covers under token/context auditing -- that skill's framing is "this
context is bigger than it needs to be, and it costs more per call than it
should"; this section's framing is "an oversized request, regardless of who
is paying for it or whether the spend is even noticed, can take the service
down for every other caller." Same technical surface (context length,
request size), entirely different failure mode being defended against.

**Hard request-size and context-length caps at the gateway, ahead of the
model.** Reject a request whose input token count or requested `max_tokens`
exceeds a fixed ceiling before it ever reaches the serving process --
enforced at the ingress/gateway layer, not left to whatever ceiling the
model or serving framework happens to allow by default. The cap should be
set from what legitimate callers actually need, not from the model's
technical maximum context window.

**Per-caller rate limiting scoped by cost, not just request count.** A
token-bucket keyed on estimated token volume (input + requested output) per
caller/tenant, not merely requests-per-second, is what actually prevents one
caller from monopolizing batching capacity -- a caller sending ten
maximally-sized requests per minute can exhaust more capacity than another
sending a thousand tiny ones, and a request-count-only limiter treats them
as equivalent. This composes with, rather than replaces, `llm-app-security`'s
flat per-caller requests-per-second cap: that one bounds throughput
regardless of backend, this one additionally bounds what a single request
can do to a shared GPU-batched serving pool -- run both if the app in
front of this inference host is itself multi-tenant.

**Concurrency and queue-depth caps at the serving framework.** Most
self-hosted serving frameworks (vLLM, TGI, Triton, and similar) expose
configuration for maximum batch size, maximum concurrent sequences, and
queue depth -- set these deliberately rather than leaving framework
defaults in place, because the default is usually tuned for throughput on
trusted traffic, not for surviving an adversarial or simply buggy caller.

**Per-request generation timeouts.** Cap how long a single generation is
allowed to run before it is killed, independent of `max_tokens` -- a
pathological input that causes unusually slow generation (e.g., degenerate
repetition loops on some model/sampling configurations) should not be able
to hold a GPU slot indefinitely just because it never technically exceeded
the token cap.

## 3. Hardening the inference-serving host

This catalog has no dedicated GPU or model-serving-infrastructure skill yet
-- worth stating plainly rather than gesturing at one that does not exist.
What it does have is `golden-ami-creation`'s CIS Ubuntu Benchmark Level 1
tradition for hardened EC2 images, and that baseline applies to an inference
host exactly as it applies to any other production instance: SSH hardening
(key-only, no root login), disabled unused filesystems, kernel security
parameters, auditd rules on identity files, encrypted EBS volumes,
Trivy filesystem scanning post-build, and scheduled AMI rotation so patches
actually land. Do not re-derive that baseline here -- go build the
inference host's AMI from it and layer on what is different about an
inference workload specifically:

**GPU driver and CUDA userspace patching is a separate cadence from OS
package patching.** A standard OS vulnerability scan (the Trivy filesystem
scan `golden-ami-creation` already runs) does not typically cover the
NVIDIA driver or CUDA userspace stack, which are their own attack surface
with their own advisory feed and their own update cadence, independent of
the base OS's package manager. Track and patch these on a deliberate
schedule, not opportunistically whenever an unrelated AMI rebuild happens
to bump them.

**The serving framework's metrics/admin surface is not the model API and
needs its own exposure decision.** Serving frameworks commonly expose a
metrics endpoint (a `/metrics` scrape target) and sometimes an admin or
management API distinct from the inference endpoint itself. Treat exposure
of that surface as its own decision, not an afterthought of exposing the
model endpoint -- it should sit behind the same network boundary as any
other internal-only operational endpoint, reachable by the scrape/ops
tooling that needs it and nothing else.

**Network segmentation: the inference host is its own segment, not part of
general application address space.** Put inference hosts in their own
security group/subnet, with ingress limited to the gateway or load balancer
in front of them and egress locked down per §1, rather than co-locating them
with general application workloads that have broader, more permissive
network rules by default. This is the same private-subnet-plus-LB-only
principle applied to any production workload -- the reason to call it out
here is that a GPU host is expensive and often provisioned as a one-off
outside the normal fleet-provisioning path, which is exactly how it ends up
skipping the segmentation review a routine workload gets automatically.

## Anti-patterns

- Treating this skill's scope as covering prompt injection, agent tool
  permissions, or MCP transport/authorization -- those are
  `prompt-injection-defense`, `ai-agent-security`, and `mcp-server-security`
  respectively; duplicating them here is exactly the collision this skill
  exists to avoid.
- World-readable or shared-mount checkpoint files "because the serving
  process needs read access anyway" -- scope the permission to that one
  process's identity, not to anything on the node.
- No egress restriction on inference hosts, on the reasoning that "it's an
  internal service" -- internal-only ingress says nothing about what the
  host itself can send out once something with host access wants to.
- Relying solely on a signed checkpoint / registry entry as if it prevented
  exfiltration -- signing (`model-registry-governance`) gives you a
  fingerprint to detect misuse after the fact; it does not stop a copy from
  happening in the first place.
- Rate-limiting an inference endpoint purely by request count, ignoring
  that a request's actual cost is driven by context length and requested
  output length -- a request-count limiter is blind to the exact lever that
  can stall the server.
- Framing request-size/context-length caps purely as a cost control
  (`llm-cost-optimization`'s territory) and skipping the availability
  framing entirely -- the same cap serves both purposes, but sizing it only
  for spend can leave it too loose to prevent resource exhaustion.
- Leaving serving-framework defaults for batch size, concurrency, and queue
  depth untouched, on the assumption that defaults tuned for throughput on
  trusted traffic are safe defaults for any traffic.
- Patching the OS package set on schedule while never tracking GPU
  driver/CUDA userspace advisories on their own cadence.
- Co-locating an inference host in the same network segment as general
  application workloads because it was provisioned as a one-off outside the
  normal fleet path, skipping the segmentation review a routine workload
  would get automatically.
- Exposing a serving framework's metrics or admin endpoint on the same
  network path as the model's inference endpoint without a separate
  exposure decision.
