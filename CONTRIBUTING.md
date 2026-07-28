# Contributing

Thanks for considering a contribution. This catalog is useful in proportion to
how specific and accurate its skills are, so the bar is about grounding rather
than volume.

## Adding a skill

1. Pick a category under `skills/`, or propose a new one in your pull request.
2. Create `skills/<category>/<name>/SKILL.md`.
3. Write the frontmatter:

```yaml
---
name: my-skill
description: "One sentence, 60 characters maximum, ends with a period."
version: 1.0.0
author: Your Name
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [my, skill, category]
    category: <category>
    related_skills: []
---
```

4. Structure the body:

```markdown
# My Skill

Two or three sentences on what this covers and what it deliberately does not.

## When to Use

The trigger conditions — the symptoms or tasks that should make an agent
reach for this skill.

## ...substance...

## Anti-patterns

What not to do, and why.
```

5. Run the validator and open a pull request:

```bash
python3 tools/validate_skills.py
```

## Requirements

**Description under 60 characters.** Agents hold every skill's description in
context permanently and expand only the body on demand. State the capability,
skip marketing words, and do not restate the skill name.

**English only.** All prose, code comments, and examples. The validator rejects
accented Latin characters.

**No organization-specific data.** Use the placeholder vocabulary:

| Placeholder | Stands for |
| --- | --- |
| `<org>` | Organization or resource-name prefix |
| `<org-domain>` | Public DNS zone |
| `<ACCOUNT_ID>` | AWS account id |
| `<workspace>` | Local checkout root |

Never commit real hostnames, account ids, ARNs, bucket names, internal URLs,
usernames, or local filesystem paths.

**Ground your claims.** State the chart version, release, or environment a
behavior was observed in. "Grounded on Helm chart `argo/argo-rollouts 2.40.9`"
is worth more than an unattributed assertion. When a metric is absent in
practice despite being documented upstream, say so — that is exactly the kind
of knowledge agents lack.

**Prefer specificity over completeness.** A skill covering five failure modes in
depth beats one listing forty metrics without interpretation.

## Editing an existing skill

Keep `version` meaningful: bump the patch for corrections, the minor for new
sections, the major for a restructure that changes how the skill is used.

## Pull requests

- One skill (or one coherent group) per pull request.
- Explain how you verified the content — a cluster, a chart version, upstream
  documentation, or a source-code reference.
- The validator must pass.

## License

By contributing you agree that your work is licensed under the
[MIT License](LICENSE).
