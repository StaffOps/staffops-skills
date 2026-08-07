---
name: skill-share
description: "Scaffold, validate, package, and announce a catalog skill."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [skill, share, scaffold, package, distribute, workflows]
    category: workflows
    related_skills: [skill-authoring, skill-eval-harness]
---
# Skill Share

The mechanical packaging/distribution half of shipping a skill, once its
content is already written. `skill-authoring` covers whether a skill's
frontmatter and body are well-structured and worded to trigger correctly —
a content-quality question you answer by reading the file. This skill
covers a distinct, narrower concern: generating the scaffold in the first
place, running the real validator scoped to one skill plus a check it
doesn't perform, zipping the result, and formatting an announcement — none
of which say anything about whether the skill's instructions are good.

## When to Use

Use when starting a brand-new skill and you want the frontmatter and body
shape pre-filled instead of copy-pasting `CONTRIBUTING.md`'s template by
hand. Use when you want a per-skill validation pass instead of reading the
whole-catalog output of `tools/validate_skills.py` and hunting for the
lines about your skill. Use when you need a distributable archive of a
single skill directory — for a teammate, a different repo, or a bundle
outside this catalog's own git history. Use when you want a short,
copy-pasteable summary of a new skill to drop into whatever channel your
team actually uses (Slack, email, a PR description) without this tool
assuming which one that is.

Do not use this to judge whether a description will actually trigger on
the right prompts, whether a piece of prose belongs in `references/`, or
whether the body is well-formed prose — that is `skill-authoring`'s job,
and this tool assumes that pass already happened by the time you scaffold,
validate, or package.

## The four subcommands

```bash
python3 skills/workflows/skill-share/scripts/skill_share.py scaffold <category> <name>
python3 skills/workflows/skill-share/scripts/skill_share.py validate <path>
python3 skills/workflows/skill-share/scripts/skill_share.py package <path>
python3 skills/workflows/skill-share/scripts/skill_share.py announce <path>
```

`<path>` accepts either a skill directory or a direct path to its
`SKILL.md` in every subcommand below.

### `scaffold` — generate the frontmatter and body shape

```bash
python3 skills/workflows/skill-share/scripts/skill_share.py scaffold workflows my-new-skill \
  --author "Your Name"
```

Writes `skills/workflows/my-new-skill/SKILL.md` with `version: 1.0.0`,
`license: MIT`, `platforms: [linux, macos, windows]`, and
`metadata.hermes.category` already correct, `description` and `tags` left
as `TODO` placeholders, and a body following `CONTRIBUTING.md`'s exact
template (H1, intro, `## When to Use`, a substance placeholder,
`## Anti-patterns`). The file passes `tools/validate_skills.py` unedited —
replacing every `TODO` is still on you, but the structural shape never has
to be retyped from memory. `--skills-dir` overrides where it writes, which
is how this tool's own tests scaffold a throwaway skill under `/tmp`
instead of touching the real catalog.

### `validate` — the real validator, scoped to one skill, plus what it misses

```bash
python3 skills/workflows/skill-share/scripts/skill_share.py validate skills/workflows/my-new-skill
```

This does **not** re-implement `tools/validate_skills.py` — it shells out
to it, auto-scoped to the skill's own `skills/` directory so a single-skill
check doesn't require reading past every unrelated error in a 190+-skill
catalog, and filters the output to lines about the target skill. Pass
`--skills-dir` to point it at a different catalog root explicitly (the
default auto-detection assumes the skill sits two directories under a
`skills/`-named root, which holds for every skill in this catalog and for
a throwaway copy of the same shape under `/tmp`).

On top of that, it runs one check the real validator does not:
**dangling references**. Every inline-code span in the body shaped like a
bundled-resource path with an extension — e.g. a `references/` file, a
`scripts/` file, or an `examples/` file — is checked against the skill's
own directory, and anything mentioned but missing is reported by name.
`skill-authoring`'s own pre-flight text calls this out as a known gap in
the existing tooling — a body that points a reader at a `references/`
file for something nobody actually committed fails silently today, and
this closes that gap without touching `tools/validate_skills.py` itself.
The check deliberately ignores fenced code blocks and any inline span
without a file extension, so example shell commands and bare directory
mentions like `references/` don't produce false positives — this
paragraph describes the rule in prose rather than in inline-code spans
for exactly that reason: literal example paths here would otherwise trip
the same check they're explaining.

Every `validate` run also prints the exact `collision-check` command from
`skill-eval-harness` to run next — see that skill for what it checks and
why; this tool does not attempt a smaller version of it, because a
meaningful overlap score needs the whole catalog's descriptions and tags to
compare against, which a single-skill wrapper has no business
re-fetching or re-implementing.

### `package` — zip a skill, gated on validation

```bash
python3 skills/workflows/skill-share/scripts/skill_share.py package skills/workflows/my-new-skill \
  --output-dir dist/
```

Runs the exact same validation as the `validate` subcommand first, as a
**hard gate**: a skill with a frontmatter error or a dangling reference is
refused, not packaged with a warning. On success, zips the skill directory
into `<name>-<version>.zip`, rooted at `<name>/` inside the archive, and
excludes `__pycache__/`, `.pytest_cache/`, `.git/`, `.DS_Store`, and
`*.pyc`/`*.pyo` files — the kind of local build artifacts a `scripts/`
directory accumulates during authoring that have no business in a
distributed archive.

### `announce` — a vendor-agnostic summary, not an integration

```bash
python3 skills/workflows/skill-share/scripts/skill_share.py announce skills/workflows/my-new-skill
```

Formats the skill's name, version, description, and the first paragraph of
its body (the 2-3 sentence intro every skill in this catalog already has)
into a short plain-text block, printed to stdout or written to a file with
`--output`. It does not send this anywhere. Wiring it into Slack, Teams,
email, or a PR description is a copy-paste away, and stays that way on
purpose — hardcoding one commercial chat connector's API into a catalog
tool ties every contributor's workflow to that vendor, and the previous
version of this idea (see "Where this comes from" below) did exactly that.

## Where this comes from

Adapted from `skill-share` in ComposioHQ/awesome-claude-skills, which
described the same create → validate → package → announce lifecycle in
prose only — no scaffold template, no validator, no packaging script — and
hard-coupled the announce step to Slack via a specific commercial
connector ("Rube"/Composio). This version implements every step for real
against this catalog's own conventions and drops the vendor coupling
entirely; see "`announce` — a vendor-agnostic summary, not an integration"
above for why.

## Anti-patterns

- **Hand-writing a new `SKILL.md` from memory instead of `scaffold`.** The
  frontmatter shape is mechanical; typos in it (a missing `license: MIT`, a
  `category` that doesn't match the directory) are exactly what
  `tools/validate_skills.py` catches on the first run and `scaffold` avoids
  entirely.
- **Reading the full-catalog output of `tools/validate_skills.py` to find
  the three lines about your skill.** `validate` already scopes and filters
  that for you.
- **Treating `validate`'s PASS as equivalent to `skill-authoring`'s
  pre-flight checklist.** It confirms the file is structurally well-formed
  and has no dangling references — it says nothing about whether the
  description will trigger correctly or the body is well-written prose.
- **Packaging a skill without running `validate` first "because `package`
  will catch it anyway."** True, but reading the validation report before
  you also generate a zip saves a step when something fails.
- **Skipping the `collision-check` command `validate` prints** because the
  skill "obviously" doesn't overlap with anything else. `skill-authoring`
  makes the same point: overlap in a 190+-skill catalog is rarely obvious
  by inspection.
- **Bolting a specific chat API onto `announce`.** The whole point of
  formatting a plain-text block instead of calling a Slack/Teams SDK
  directly is that this tool works the same way regardless of which team
  uses which channel — do that wiring outside this script, not inside it.
- **Adding a fifth exclude pattern to `package` for a one-off file instead
  of just not committing it.** The exclude list covers build artifacts that
  `scripts/` directories reliably accumulate (`__pycache__`, `.pyc`,
  `.DS_Store`); it is not a general-purpose `.gitignore` replacement.

## When NOT to use

- **Private/org-specific knowledge** — don't share skills containing internal endpoints, secrets, or proprietary info.
- **Incomplete/draft skills** — share after validation via the eval harness.
- **Steering rules** — sharing steering requires different governance; skills are opt-in knowledge.

## Related skills

- [skill-authoring](../workflows/skill-authoring/SKILL.md) — writing skills ready for sharing.
- [skill-eval-harness](../workflows/skill-eval-harness/SKILL.md) — validating quality before sharing.
- [how-this-agent-works](../workflows/how-this-agent-works/SKILL.md) — understanding skill registry.
