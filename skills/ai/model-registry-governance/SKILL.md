---
name: model-registry-governance
description: "Track model provenance, eval results, and approval status."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [ai, model-registry, governance, provenance, lifecycle, approval, supply-chain]
    category: ai
    related_skills: [agent-evals, ai-red-teaming, cosign-image-signing, sbom-vulnerability-management, llmops-platform-engineering]
---
# Model Registry Governance

What a team needs to track about every model it depends on -- self-hosted
checkpoint, fine-tuned derivative, or a specific version of a third-party
API model -- so that "which model is this, where did it come from, has it
been evaluated, and is it still allowed" has one answer instead of tribal
knowledge scattered across config files and Slack threads. It covers the
metadata a registry entry actually needs, an honest read of how far the
container-supply-chain analogy this catalog already uses (`cosign-image-signing`,
`sbom-vulnerability-management`) extends to a model artifact and where it
stops, the lifecycle states a model moves through, and what "banned" has to
mean mechanically for it to matter. It deliberately does not cover training
pipelines, feature stores, or hyperparameter tuning -- this is a governance
and enforcement layer over models that already exist, not an MLOps skill.

## When to Use

- Standing up a registry (a database, a structured file, or a dedicated tool)
  to track which models are approved for which use cases, for a team that
  self-hosts, fine-tunes, or calls a third-party model API.
- Deciding what metadata a registry entry needs before the first entry gets
  written, so the schema doesn't grow ad hoc, one missing field at a time,
  after an incident.
- A team is about to bump a production config to a new model version --
  self-hosted or a third-party API identifier -- and there is no gate
  checking whether that specific version has been evaluated or approved.
- A safety or compliance finding (a red-team result, a provider recall, a
  license issue) means a model needs to stop being usable, and "banned"
  needs to actually block something, not just exist as an unread flag.
- Not for designing a training pipeline, a feature store, or an experiment-
  tracking system (MLflow-style run metadata) -- this skill is about
  governing which already-trained or already-available models are allowed
  into use, not about how a model gets built.

## What a registry entry actually needs to record

A registry entry that only records a name and a version number answers "what
is this" but not "should anyone be using it." Five fields carry the weight:

| Field | What it captures | Why it matters |
| --- | --- | --- |
| **Identity** | Model name, version, and either a provider + API model identifier (e.g., a dated snapshot string, not a floating alias) or, for a self-hosted checkpoint, a content hash of the weights file | A floating alias ("latest", "default") is not an identity -- it silently points at a different model over time. Pin the exact string or hash that was actually evaluated. |
| **Provenance** | For a self-hosted or fine-tuned model: what base checkpoint it derived from, what data went into training/fine-tuning, and any known PII or licensing concern in that data. For a third-party API model: which provider, and nothing more is knowable or needed -- the provider owns that provenance | This is the field most often skipped, and the one that matters most when a downstream question ("did this model see licensed or PII-bearing data?") has to be answered under time pressure, not reconstructed from memory. |
| **Eval results at registration time** | A link to (or embedded summary of) the eval run that qualified this version -- score, dimension breakdown, any `blocker: true` findings -- from whatever harness produced them, per `agent-evals` | An entry with no eval reference just asserts the model is fine. An entry with a linked score row lets the next person check the actual bar it cleared, not just trust the label. |
| **Intended use case and known limitations** | What this model version is approved for (e.g., internal summarization, not customer-facing generation) and any documented failure mode or scope boundary discovered during evaluation | Approval is not global -- a model fine for one use case can be wrong for another with a different risk profile, and the registry is where that scoping gets written down instead of assumed. |
| **Approval status** | One of the lifecycle states below, plus who approved it and when | This is the field the enforcement mechanism (see below) actually reads. Everything above this row is context; this row is the gate. |

None of this needs a bespoke platform to start. A version-controlled YAML or
JSON file with one entry per model, reviewed via the same pull-request
process as any other config change, is a completely legitimate registry for
a small number of models -- the fields above are what matter, not the
storage technology.

## The supply-chain-security parallel -- and where it actually stops

This catalog already treats a container image as an artifact whose
provenance and contents matter: `cosign-image-signing` covers proving where
an image came from and that it has not been tampered with since, and
`sbom-vulnerability-management` covers enumerating what is actually inside
it and matching that inventory against known vulnerabilities. A model
checkpoint is genuinely the same *kind* of thing -- a binary artifact
consumed by a pipeline, produced by a process someone else may not have
watched happen -- so the instinct to apply the same discipline is sound.
Two parts of the parallel hold literally, and one does not.

**Holds: signing the artifact.** `cosign` signs an arbitrary blob via
`cosign sign-blob`, not only an OCI image reference -- so recording and
signing a checkpoint file's digest is a direct reuse of the same tool this
catalog already uses for golden container images, not a strained analogy.
One operational difference: a signed container image attaches its signature
in the OCI registry alongside it (what `cosign-image-signing`'s Harbor
workflow relies on), while `cosign sign-blob` produces a standalone
signature file with no registry to auto-attach it to -- the registry entry
itself has to be where that signature file's location is recorded and
retrieved from at verification time. The practice `cosign-image-signing`
already states for images still applies unchanged: sign by digest, never by
a mutable path or filename, and verify the signature at the point the
artifact is loaded, not just at publish time.

**Holds: recording provenance as a build attestation.** What
`sbom-vulnerability-management`'s pipeline calls a component inventory has a
real (if partial) equivalent for a model: a record of the base checkpoint it
derived from, the fine-tuning dataset's source and license, and the training
job that produced it. Frameworks like Google's Model Cards and the ML
community's growing use of in-toto/SLSA-style build provenance for training
jobs are aiming at exactly this -- a verifiable "here is what went into this
artifact and how it was built" statement. Treat this as a provenance
attestation, the same category of thing a `cosign` signature or a build
attestation proves for a container image.

**Does not hold: a component inventory of what is inside the weights.** An
SBOM for a container image works because the image is made of named,
versioned, independently-tracked components (OS packages, language
dependencies) that can be enumerated and matched one-by-one against a CVE
database -- that is the entire mechanism `sbom-vulnerability-management`'s
Trivy-to-DependencyTrack pipeline depends on. A neural network's weights are
not composed of named, versioned sub-components in that sense. There is no
tooling today that opens a checkpoint file and produces a list of "what's
inside it" comparable to a package manifest, and no CVE-style database of
known-vulnerable weight patterns to match against. The nearest things that
exist -- model cards, dataset documentation, benchmark eval scores -- are
closer to a spec sheet and a test report than to a bill of materials, and
none of them let you ask "does this checkpoint contain component X at
version Y with known vulnerability Z" the way an SBOM does for a container.
Do not present a model's provenance documentation as "the SBOM for this
model" -- it invites exactly that expectation, and the tooling to back it up
does not exist yet.

## Lifecycle states and what triggers each transition

```
draft -> evaluated -> approved -> deployed -> deprecated
                                       |
                                       v  (from any state)
                                    banned
```

| State | Entered when | Typically triggered by |
| --- | --- | --- |
| `draft` | An entry is created for a model under consideration | A team registers a candidate before running anything against it |
| `evaluated` | An eval run has produced a score against this specific version | `agent-evals`'s harness run -- the entry links to the resulting score row, not just a claim that "it was tested" |
| `approved` | A human owner signs off, having read the eval result (correctness/safety within tolerance, no `blocker: true`) and the provenance fields | Not automatic from a passing eval alone -- someone accountable reviews the provenance and intended-use fields too, not only the score |
| `deployed` | The model identifier is actually referenced in a live configuration | This is an observed fact (something points at it), not a status anyone sets manually |
| `deprecated` | A newer approved version supersedes it, starting a sunset window | A replacement clears the same approval bar; the older entry is marked with a sunset date rather than deleted, so past deployments referencing it remain explainable |
| `banned` | A safety, legal, or provider-side issue means this version must stop being usable, from any prior state | Most often a finding surfaced by `ai-red-teaming` against this specific version (a bypass with no available fix), a provider-side recall or deprecation notice, or a licensing/compliance issue discovered after the fact |

`banned` is reachable from any state, including `deployed` -- an already-live
model can be banned the moment a disqualifying finding lands, and that is
the state transition the next section's enforcement point exists to make
consequential.

## Enforcing "banned" mechanically, not as an unread flag

A `banned` status that only lives in a registry entry nobody re-checks after
the initial rollout is not governance, it is documentation of a decision
that has no effect. The registry needs exactly one enforcement point: a
check, in CI or at the promotion boundary, that reads the registry and
refuses to let a banned (or unapproved) model identifier ship. This is the
same shape as the two mechanical gates this catalog already has for other
artifact types:

- `cosign-image-signing`'s Kyverno `ClusterPolicy` verifies a golden image's
  signature at admission -- an unsigned image is rejected by the cluster,
  not merely flagged in a dashboard.
- `agent-evals`'s `score` command's release gate rejects a candidate with
  `blocker: true` outright, regardless of its weighted average -- the gate
  is a hard `no`, not an advisory number a reviewer might skip past.

Apply the same pattern here: a CI step that greps the deploy configuration
(or reads a structured field naming the model identifier) for every model
reference, looks each one up in the registry, and fails the pipeline if any
resolves to `banned`, or to an identifier with no registry entry at all.
Whether the check lives as a pre-merge CI job, a pre-deploy gate in the same
pipeline stage that already runs `agent-evals`'s regression suite, or a
policy check analogous to the Kyverno admission rule is an implementation
choice -- what is not optional is that some mechanical step reads the
registry before the change ships. A `banned` field that only a human might
notice on the next unrelated registry review is not an enforcement point,
it is a hope.

## Third-party API models: the registry is an approved-identifiers list

A team calling a provider's API directly -- Anthropic, OpenAI, or any hosted
model -- has no checkpoint to hash, no training data to document, and no
weights to sign. All five metadata fields above still apply, they just
collapse to something much smaller: identity is the exact, dated model
identifier string (not a floating "latest" alias, which several providers
offer specifically for convenience and which is exactly the wrong thing to
pin in a production config, because it means the model actually running
changes without anyone editing anything); provenance is "this provider, this
identifier," full stop; eval results, intended use case, and approval status
apply exactly as written above.

The governance need this simplification does not remove: nothing should let
a team silently start calling a new model version in production because a
"latest" alias moved, or because someone edited a version string in a config
file without going through the same promotion process a self-hosted model
upgrade would require. Treat a version bump the same way `agent-evals`
treats any other change under review -- the currently-approved identifier is
`baseline`, the proposed new identifier is `candidate`, and the same paired
eval run decides whether the bump clears the bar before the config change
merges. A config diff that changes a model identifier string is exactly the
kind of change the CI enforcement point above should recognize and gate on,
the same as it would for a self-hosted model's registry entry.

## What this does not cover

- **Training pipelines, feature stores, and hyperparameter tuning** -- this
  is a governance layer over models that already exist by the time they
  reach a registry entry, not an MLOps build-pipeline skill.
- **Eval methodology and the release-gate mechanics** -- `agent-evals` owns
  golden-dataset design, the five-dimension rubric, and how `score` decides
  a candidate is safe to ship. This skill only says an entry must link to
  that result, not how the result is produced.
- **Adversarial testing that produces a ban-worthy finding** -- `ai-red-teaming`
  owns the attack catalog and scoring posture that surfaces a safety
  bypass in the first place. This skill only says what happens to the
  registry entry once that finding exists.
- **Full container supply-chain mechanics** -- signing workflow details,
  key rotation, and Harbor-specific signature visibility belong to
  `cosign-image-signing`; SBOM generation, CVE matching, and finding SLAs
  belong to `sbom-vulnerability-management`. This skill borrows the pattern
  from both, honestly bounded above, rather than re-teaching either.
- **The CI/CD pipeline that promotes a model or prompt change through
  dev/staging/prod** -- that is `llmops-platform-engineering`'s job. This
  skill governs what a registry entry must record and what state it's in;
  that skill governs the deploy mechanics and the eval-gated promotion flow
  that checks this registry along the way.

## Anti-patterns

- Recording a model's name and version number with no linked eval result and
  no provenance notes -- an entry that only names the artifact answers "what
  is this," not "should anyone be using it."
- Pinning a floating model alias ("latest", "default") in a production
  config instead of a dated, exact identifier -- the model running changes
  without anyone editing anything, and the registry entry silently stops
  describing what is actually deployed.
- Calling a model's provenance documentation "the SBOM for this model" --
  there is no tooling today that enumerates a checkpoint's contents the way
  an SBOM enumerates a container's packages; overselling the parallel sets
  an expectation the tooling cannot meet.
- A `banned` state that exists only as a registry field with no CI or
  admission-time check reading it before deploy -- indistinguishable from
  never having banned the model at all.
- Treating a passing `agent-evals` score as sufficient for `approved` on its
  own, with no human review of the provenance and intended-use fields --
  a model can clear a quality bar and still be wrong for a use case its eval
  suite never exercised.
- Approving a model for one use case and assuming that approval extends to
  every other use case it gets pointed at later -- approval is scoped, not
  global.
- Deleting a deprecated entry instead of marking it with a sunset date --
  past deployments that referenced it become unexplainable once the entry
  is gone.
- Bumping a third-party API model version in production the same way a
  trivial config edit would be made, without the same eval-gated promotion
  process a self-hosted model upgrade would require.
- Building a bespoke registry platform before a version-controlled file
  reviewed via pull request has been outgrown -- the fields matter, not the
  storage technology.
