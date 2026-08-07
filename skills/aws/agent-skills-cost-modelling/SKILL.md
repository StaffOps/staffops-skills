---
name: agent-skills-cost-modelling
description: "Estimate agent cost from observed duration, not guesses."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [cost, finops, agent, budgeting, triggers]
    category: aws
    related_skills: [agent-skills-harness-guide, agent-skills-adversarial-review, cost-explorer]
---
# Cost Modelling for Agent Operations

The AWS DevOps Agent bills per agent-second — $0.0083, roughly $0.50 a minute. Everything else follows from duration, and duration is the number people guess wrong.

This covers estimating and governing agent run cost. Cloud resource cost belongs elsewhere.

## When to Use

- Before creating a trigger, a webhook path, or anything that fires investigations repeatedly
- When writing a cost figure into a spec, a budget or a readme
- When an existing estimate needs checking

## Derive from duration, never from an assumed price

The failure that produced this skill:

> "The suite is 134 queries at about $0.25 each, so about $33."

At $0.0083 per agent-second, **$0.25 implies 30 agent-seconds**. Nothing in the project had ever completed in 30 seconds:

| Source | Observed |
|--------|----------|
| The harness results file — the only real measurement | **107.9 s** |
| The project's own decision record | 3 to 5 minutes |
| A design document for the same path | about 3 min including poll |

Corrected: **$0.65 to $0.90 per query, $87 to $120 for the suite** — wrong by three to four times.

The estimate was never checked against a measurement because $0.25 *sounded* plausible. The correct order is always:

```
1. Measure duration (or find the closest real measurement)
2. Multiply by the per-second rate
3. Multiply by run count
```

Never `assumed_price × count`.

## The wall-clock versus billed-seconds trap

A harness that computes `wall_seconds * rate` treats elapsed time as billable time. If the runner measures with a wall clock, that figure includes its own poll sleeps.

Consequences:

- The figures are **upper bounds** if the platform meters only active compute
- They are **accurate** if the platform meters the whole execution
- Which one applies may not be documented

When quoting a figure, say which assumption it carries. State a range rather than a point when the metering basis is unknown.

## Always-on cost falls outside every budget

A scheduled trigger, once created, fires forever. It is not validation spend, and it is usually not written into an operational budget either — so it lands in neither.

| Item | Frequency | Annual runs | At $2.50 to $6.00 each |
|------|-----------|-------------|------------------------|
| Daily trigger | 365/yr | 365 | $913 to $2,190 |
| Weekly trigger | 52/yr | 52 | $130 to $312 |
| **Two triggers** | — | **417** | **$1,043 to $2,502** |

In the real case that exceeded the entire validation budget those triggers were never counted in.

**Rule**: creating a trigger commits to indefinite spend. Compute the annual run-rate in the same change that creates it, and put it somewhere a budget review will find it.

## Event-driven paths are unbounded until you bound them

A webhook that turns qualifying alerts into investigations has a cost proportional to alert volume — which is not a number you control.

| Alerts/day after dedup | Runs/yr | Annual cost at $2.50 to $3.50 |
|-----------------------|---------|-------------------------------|
| 5 | 1,825 | $4,563 to $6,388 |
| 20 | 7,300 | $18,250 to $25,550 |

Before enabling such a path:

1. Measure current alert volume after deduplication
2. Publish the projected monthly cost
3. Implement severity tiering as a **prerequisite** — investigate the top tiers, log the rest
4. Cap concurrency so a mass-failure event cannot multiply spend

## Estimating before a measurement exists

When there is no observed duration, bound it instead of guessing a point:

| Operation shape | Reasonable range | Basis |
|----------------|-----------------|-------|
| Shallow chat answer | 30 to 90 s | Single tool call plus reasoning |
| Deep typed investigation | 3 to 7 min | 107 s observed minimum, 300 s or more when deep |
| Scheduled review agent | 5 to 12 min | Multiple backend queries plus synthesis |
| Refusal probe against a nonexistent target | 2 to 4 min | Refusal is fast but still reasons |

Then measure and replace the range with the real number. Mark estimates as estimates.

## Cheaper designs before bigger budgets

Cost questions often have a design answer rather than a budget answer:

| Instead of | Consider | Saving |
|-----------|----------|--------|
| A full sweep of every test query | Sample 30, report a confidence interval, run the full sweep only when the sample regresses | about 78% |
| Live invocation for every routing test | Screen locally against skill descriptions, reserve live runs for a calibration sample | about 85% |
| Investigating every alert | Tier by severity; log the low tiers | Proportional to the tier split |

Free layers should gate every commit; paid layers run on a cadence. A structural linter and a name-verification sweep cost nothing — there is no reason not to run them constantly.

## The return-on-investment trap

An agent cost figure is not a return. To claim a saving you need the denominator: engineer-hours displaced. Without it, "each investigation costs $2.50" is a spend number with nothing to compare against.

Industry averages such as "60% of engineering time goes to production operations" are context, not evidence for a local claim — particularly when the source is a vendor report. If return on investment is the argument, commit to measuring time-to-resolution with and without the agent. Otherwise present the work as capability rather than saving.

## Quotas that shape cost decisions

| Quota | Typical value | Cost implication |
|-------|--------------|------------------|
| Concurrent sessions | 10, shared with real users | Long batch runs occupy capacity. Off-peak only, sequential |
| Journal pagination | 100 records per page | A deep run's conclusion may be on page 2 — paginate or lose it |

## Anti-patterns

- Multiplying an assumed per-run price by a run count
- Quoting a point estimate when the metering basis is unknown
- Creating a scheduled trigger without computing its annual run-rate
- Enabling an event-driven path before measuring the event volume
- Presenting a spend figure as a saving with no displaced-hours denominator
- Running paid validation layers on every commit when a free linter would catch the same class of defect
