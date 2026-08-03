---
name: model-supply-chain-security
description: "Vet upstream model checkpoints and training data provenance."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [ai, model, supply-chain, checkpoint, pickle, data-poisoning, license, provenance]
    category: ai
    related_skills: [model-registry-governance, ai-red-teaming, sbom-vulnerability-management, cosign-image-signing]
---
# Model Supply Chain Security

What can go wrong in the inputs that produce a model -- a third-party
checkpoint pulled from a public hub, the fine-tuning data used to adapt it,
and the license terms attached to both -- before any of that ever reaches a
registry entry. **This is explicitly not `model-registry-governance`'s
territory**: that skill owns what a registry entry records once a model
exists (identity, provenance metadata, eval linkage, approval state,
lifecycle transitions), the honest signing-and-SBOM-parallel for a model
artifact, and how `banned` gets enforced mechanically. This skill is the step
before that -- the upstream supply chain a checkpoint or dataset travels
through on its way to becoming a candidate registry entry, and what to check
before trusting it that far.

## When to Use

- Downloading a pretrained model, checkpoint, or LoRA adapter from a public
  hub (Hugging Face, TensorFlow Hub, a community mirror) to self-host or
  fine-tune, before it is loaded into any process.
- Fine-tuning on external, user-contributed, or crowd-sourced data, or on
  any dataset whose full contents no one on the team has reviewed
  end-to-end.
- Before a checkpoint or dataset acquired from outside the organization is
  proposed for a `model-registry-governance` entry -- this skill is the
  vetting step that happens first, so the provenance fields that skill's
  registry records are actually true rather than assumed.
- Redistributing a fine-tuned derivative of an open-weight base model, or
  shipping a product built on one, where the base model's license terms
  might restrict exactly that.
- Not for deciding what a registry entry should record, how `approved`
  and `banned` states are enforced, or the signing/SBOM-parallel for a
  model artifact -- all of that is `model-registry-governance`. Not for
  defending against a prompt injected at inference time through a document
  or tool response -- that is `prompt-injection-defense`'s input-side
  problem, a different attack surface from a backdoor baked into the
  weights during training.

## Third-party checkpoint provenance: the pickle problem

A checkpoint pulled from a public hub is not a normal dependency download --
the file format itself can be a code-execution vector, independent of
whether the weights are any good.

**The concrete risk.** Legacy PyTorch checkpoints (a `.bin` or `.pt` file
saved with the default serializer) are Python `pickle` streams. Loading one
with `torch.load` does not just deserialize tensors -- `pickle` reconstructs
arbitrary Python objects by calling whatever constructor the file specifies,
which means a crafted checkpoint can execute arbitrary code the moment it is
loaded, with no separate "run this" step required. This is not a theoretical
concern specific to some rare misuse; it is the documented behavior of
`pickle.load` on untrusted input, and a checkpoint from a public hub is
untrusted input by definition -- nobody on the receiving end watched it get
produced.

**The concrete mitigation, in order of preference:**

1. **Prefer `safetensors`-format checkpoints.** The format stores only raw
   tensor data with a JSON header describing shapes and dtypes -- there is no
   code path that executes anything on load, by construction, not by policy.
   Most actively-maintained models on public hubs now ship a `safetensors`
   variant alongside (or instead of) the legacy pickle format; take that
   variant whenever it is offered.
2. **If a pickle-format checkpoint must be used** (an older model with no
   `safetensors` release, an internal artifact predating the migration),
   scan it before loading rather than loading it directly. Tools built for
   exactly this exist -- `picklescan` and similar static analyzers walk the
   pickle opcode stream looking for dangerous reducers (`__reduce__`,
   `eval`, `exec`, `os.system`, and similar) without executing the file.
   State the limitation honestly: a static scanner catches known-dangerous
   patterns, not every way a pickle stream can be made to do something bad --
   it narrows the risk, it does not eliminate it the way a safe format does.
   Treat a clean scan result as "no known-bad pattern found," not as a
   safety guarantee equivalent to a format that cannot execute code at all.
3. **Load in an isolated, network-restricted environment** for any
   checkpoint whose format or source leaves residual doubt after the above --
   the same "assume it can misbehave, bound the blast radius" posture this
   catalog already applies to untrusted container images.

## Training and fine-tuning data provenance: poisoning risk

Fine-tuning changes model weights based on whatever data feeds the process --
which means a subset of poisoned data mixed into an otherwise legitimate
training set can implant behavior nobody asked for.

**The concrete risk.** Data poisoning is a documented attack class distinct
from the inference-time problem `prompt-injection-defense` addresses: prompt
injection is untrusted *content the model reads at inference time* carrying
text crafted to be followed as an instruction; data poisoning is untrusted
*content baked into the weights during training* that implants a standing
behavior -- classically a backdoor, where a specific trigger phrase in a
future prompt causes the model to produce a specific attacker-chosen output,
with the model behaving normally on every input that does not contain the
trigger. The two are not the same failure mode with the same fix: hardening
how untrusted content is read at inference time (`prompt-injection-defense`'s
layered controls) does nothing to stop a bad example that was already
absorbed into the weights months earlier, because by the time inference
happens, the bad behavior is not injected content anymore -- it is the
model's own learned response.

**Concrete mitigations for the training-time side:**

- **Vet the data source before it enters the training set.** Know who
  contributed each subset of a fine-tuning corpus and whether that source is
  trusted, moderated, or fully open (unmoderated user submissions carry the
  highest poisoning risk, precisely because anyone can shape a subset of
  what the model learns).
- **Run anomaly detection on the training data distribution**, not just on
  model outputs after the fact -- a poisoned subset frequently looks
  statistically different from the rest of the corpus (an unusual
  label/text pairing frequency, a suspicious phrase repeated far more often
  than natural language would produce it) before it ever becomes a trained
  behavior.
- **Accept that prevention is not sufficient on its own.** Even careful
  source vetting and distribution checks can miss a subtle trigger, because
  the whole point of a backdoor is to look unremarkable in the training data
  and only misbehave on a specific, rare input. The practical detection
  mechanism for a backdoor that already made it into a fine-tuned model is
  `ai-red-teaming`'s adversarial testing -- specifically, testing the
  fine-tuned model against a battery of crafted trigger-phrase attempts
  designed to surface a planted behavior, the same way that skill's attack
  catalog surfaces a scope-escalation or tool-abuse bypass in an agent.
  Route a suspected backdoor finding through `ai-red-teaming`'s workflow
  (encode it as a case, score `blocker: true` on a confirmed trigger, do not
  average one working trigger into a passing rate) rather than treating
  "the training data looked fine" as proof the model is clean.

## License and provenance tracking: the check before registration

Open-weight models on public hubs frequently carry usage restrictions that
are easy to violate without noticing: commercial-use clauses that permit
research use but not a paid product, attribution requirements, restrictions
on what a derivative fine-tuned model may itself be licensed as, or
field-of-use limits (no use in a specific regulated domain, no use for a
specific application category). None of this is exotic legal territory --
it is printed in the model card or the repository's license file -- but it
is easy to skip when the checkpoint downloads in one command and fine-tuning
starts the same afternoon.

**Where this differs from `model-registry-governance`.** That skill's
provenance field records, among other things, "any known PII or licensing
concern" *once an entry exists* -- it assumes the licensing question has
already been answered by the time someone writes the registry entry. This
skill is the step that produces that answer: before a third-party
checkpoint or dataset is proposed for registration at all, read its actual
license, confirm it permits the intended use (commercial deployment,
redistribution, fine-tuning and re-releasing a derivative under a different
license), and treat a license that is unclear, missing, or restrictive as a
blocker to registration -- not as a footnote to fill in later. Getting this
backward -- registering first, checking the license after a model is already
in production -- turns a compliance question into a live incident instead of
a five-minute read.

## What this does not cover

- **Registry entry metadata, lifecycle states, approval enforcement, and the
  signing/SBOM-parallel for a model artifact** -- all `model-registry-governance`.
  This skill's job ends where a checkpoint or dataset becomes a well-vetted
  candidate for that registry; it does not define the registry itself.
- **Inference-time prompt injection** (a document, ticket, or tool response
  carrying text crafted to be followed as an instruction) -- that is
  `prompt-injection-defense`'s territory. Data poisoning above is a
  training-time attack on the weights; prompt injection is an inference-time
  attack on the context window. Different mechanism, different fix, both
  worth knowing apart.
- **Adversarial test design and scoring methodology in general** --
  `ai-red-teaming` owns the harness, the attack-category taxonomy, and the
  scoring posture (a single bypass is a finding, not an average). This skill
  only points to it as the practical way to surface a backdoor already
  trained into a model.
- **Container-image SBOM generation and CVE matching** -- unchanged,
  `sbom-vulnerability-management`'s territory, and it does not extend to a
  model's weights any more than `model-registry-governance` already explains
  in its own "does not hold" section.

## Anti-patterns

- Loading a pickle-format (`.bin`/`.pt`) checkpoint from a public hub
  directly with no scan, on the assumption that a model file cannot be a
  code-execution vector the way an executable can -- it can, by design of
  `pickle.load`.
- Treating a clean `picklescan` result as a safety guarantee rather than "no
  known-bad pattern found" -- prefer `safetensors` whenever it is available
  instead of relying on scanning a format that did not need to be scanned in
  the first place.
- Assuming `prompt-injection-defense`'s input-sanitization controls protect
  against a backdoor trained into the weights -- that skill defends what the
  model reads at inference time; a poisoned fine-tune is already a learned
  behavior by the time inference happens.
- Fine-tuning on an unmoderated, user-contributed dataset with no source
  vetting and no distribution-anomaly check, then treating a clean-looking
  eval score as proof no backdoor was planted -- a backdoor is designed to
  look unremarkable until its specific trigger appears.
- Skipping adversarial trigger-phrase testing on a freshly fine-tuned model
  because "the training data looked fine" -- source vetting reduces
  poisoning risk, it does not detect a backdoor that already landed;
  `ai-red-teaming`'s testing is what does.
- Fine-tuning on or redistributing a derivative of an open-weight model
  without reading its license terms first, then discovering a commercial-use
  or derivative-licensing restriction after the model is already in
  production.
- Registering a third-party checkpoint or dataset in a `model-registry-governance`
  entry with the license field left blank or marked "TBD," planning to fill
  it in later -- an unclear license is a blocker to registration, not a
  footnote.
- Calling this skill's checks "the SBOM for the model" or otherwise
  overclaiming completeness -- a clean pickle scan, a vetted data source, or
  a read license are each one narrow check against one specific risk, not a
  comprehensive inventory of everything that could be wrong with a
  checkpoint or dataset.
