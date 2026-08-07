---
name: reviewer
description: "Use when reviewing a new or edited skill for quality, format compliance, and collision with existing skills."
---

# Skill Reviewer

Review skills for:
1. Correct frontmatter (name matches dir, description 100-1024 chars)
2. Standard sections present (When to use, When NOT to use, Steps, Related skills)
3. No org-specific content
4. Metric names are real (not invented)
5. No collision with sibling skills (description overlap)

Run `python3 tools/validate_skills.py` and report findings.
