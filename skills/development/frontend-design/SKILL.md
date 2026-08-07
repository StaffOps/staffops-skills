---
name: frontend-design
description: "Use when building or restyling a UI that needs a distinct identity — choosing color palettes, typeface pairings, layout concepts, and avoiding generic AI-generated clichés. Covers the brainstorm-critique process, accessibility contrast floor, token system, and mechanical self-check."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [frontend, ui, visual-design, typography, accessibility]
    category: development
    related_skills: []
---
# Frontend Design

Visual and interaction design judgment for building or reshaping a UI: how
to choose a color palette, a typeface pairing, a layout concept, and one
signature element that reads as made-for-this-brief rather than templated.
It covers the brainstorm-then-critique process that produces those choices,
a hard accessibility contrast floor, and a mechanical self-check for
whether the output actually avoided the defaults it was trying to avoid.

It deliberately does not cover component libraries, CSS frameworks, or
state management -- pair it with your framework's own docs for those. It
also is not a full accessibility compliance program: the contrast checklist
below is a floor, not a substitute for a real audit on a regulated product.

## When to Use

- Building new UI from a design brief that does not already dictate a
  design system or component library
- Restyling an existing UI that a reviewer describes as generic, templated,
  or "looks AI-made"
- Any request shaped like "make it look good" or "give this a distinct
  identity" without further visual constraint
- **Not** when a design system, brand guideline, or component library
  already owns these decisions -- defer to it and use this skill only for
  gaps it leaves open

## When NOT to Use

- Project already has a complete design system (Material, Ant, Chakra) → follow it
- Pure backend service with no UI
- Data visualization / charting → use D3/Vega/Plotly patterns instead
- Accessibility audit on a regulated product → engage a real auditor, not just this contrast floor

## The two-pass process: brainstorm, critique, then build

Work in two passes, in order. Do not start writing markup or CSS until both
passes are done.

**Pass 1 -- brainstorm a token system.** Produce a compact, structured set
of choices: 4-6 named colors with hex values and roles, typefaces for at
least two roles (display and body, plus a utility/mono face only if the
content has captions, data, or code), a one-sentence layout concept backed
by an ASCII wireframe, and a single signature element the page will be
remembered by. Use `references/token-system.json` as the schema -- fill
every field, do not skip straight to prose. A forced schema makes it
possible to diff choices across iterations instead of losing them in
freeform paragraphs.

**Pass 2 -- self-critique against the brief, before writing code.** For
each part of the plan, ask: *would I arrive here for any similarly-scoped
brief, or is this specific to this subject?* If a choice would survive
being pasted into an unrelated brief unchanged, it is a default, not a
decision -- revise it and write down what changed and why in the
`self_critique` block of the token file. Only after this gate passes do you
start writing code, and the code should derive every color and type choice
from the (possibly revised) plan -- not reintroduce a color or face that
was never in the token file.

If the brief itself pins down a visual direction -- including one of the
cliches named below -- follow the brief exactly. The cliche list constrains
what you default to on the axes the brief leaves open, not what the brief
explicitly asked for.

## Named cliches to avoid (unless the brief calls for them)

These are recognizable fingerprints, not permanently forbidden choices.
Landing on one by default, for a brief that gave no reason to, is the
problem.

### From the original catalog of AI-generated-design tells

| # | Fingerprint | Recognizable by |
| --- | --- | --- |
| 1 | Cream-and-serif | Warm cream background (around `#F4F1EA`) with a high-contrast serif display face and a terracotta accent |
| 2 | Near-black neon accent | Near-black background with exactly one saturated accent color (an acid green or a vermilion/red-orange) and nothing else |
| 3 | Broadsheet layout | Hairline rules, zero border-radius anywhere, dense multi-column text blocks styled like newsprint |

### Additional fingerprints (this catalog's own additions)

| # | Fingerprint | Recognizable by |
| --- | --- | --- |
| 4 | Default shadcn/Tailwind look | Inter (or the current Tailwind default), a slate-900-on-slate-50 grayscale scale, one indigo-600-style primary button color, and every card at `rounded-lg` with the same soft drop shadow -- the exact defaults the framework ships with, unmodified |
| 5 | Generic purple-to-blue gradient hero | A violet-to-blue (or violet-to-pink) gradient background behind the hero, usually paired with soft blurred "blob" shapes -- ubiquitous enough to read as a placeholder rather than a choice |
| 6 | Uniform stock icon set | The same outline icon library (Heroicons/Feather-style glyphs) at identical size in every feature card, with no custom iconography, illustration, or photography specific to the subject |

`scripts/lint-tokens.py` flags the exact hex values from fingerprints 1 and
4-5 if they survive unchanged into the built output (see the objective
lint pass below). Fingerprints 2, 3, and 6 are structural rather than a
fixed color and need a look, not a grep.

## Contrast is a checklist item, not a vibe

Compute or estimate contrast for every foreground/background pairing that
carries text or a UI component, before finalizing the palette -- not after
a reviewer flags illegible text.

WCAG AA minimums:

| Content | Minimum ratio |
| --- | --- |
| Normal text (under 18pt, or under 14pt bold) | 4.5:1 |
| Large text (18pt+, or 14pt+ bold) and UI components / graphical objects | 3:1 |

To compute a ratio: convert each hex color to linear sRGB (gamma-correct
each channel), take the relative luminance `L = 0.2126R + 0.7152G +
0.0722B`, then `ratio = (L_lighter + 0.05) / (L_darker + 0.05)`. Run it
directly instead of eyeballing it:

```bash
python3 scripts/contrast-check.py "#1B1B1F" "#FAF9F6"
python3 scripts/contrast-check.py "#1B1B1F" "#FAF9F6" --large
```

Record every pairing's result in the `contrast_checks` array of the token
file. A palette with an accent color that fails 4.5:1 against its intended
text is not finished, regardless of how the rest of the plan reads.

## Self-critique via screenshot

A described layout and a rendered one diverge in ways prose does not catch
-- spacing that reads fine in CSS and collapses at a real viewport width,
a signature element that is invisible once real content replaces the
placeholder text. Take an actual screenshot before calling a pass done.

Use a headless browser as the concrete mechanism, not "if the environment
happens to support it": Playwright's CLI needs no project setup beyond a
one-time browser install.

```bash
npx --yes playwright install chromium   # one-time
npx --yes playwright screenshot --viewport-size=390,844 http://localhost:3000 mobile.png
npx --yes playwright screenshot --viewport-size=1440,900 http://localhost:3000 desktop.png
```

Look at both, then run the same questions from Pass 2 against the rendered
result, not just the plan: does the signature element still read as the
one memorable thing, or did it get lost under real content? Does any named
cliche show up in the render even though the token file avoided it in
name? Is there a spacing or contrast problem invisible in the source but
obvious in the screenshot?

## Objective lint pass

Subjective judgment misses the same three things reliably: too many font
families creeping in, an accent palette that quietly grew past "small and
deliberate," and a cliche hex value that got pasted back in during a later
edit. Run a mechanical check for these against the built CSS (or any text
output) after the render looks right:

```bash
python3 scripts/lint-tokens.py dist/styles.css
```

It reports the distinct font-family count (warns above 2 -- a third face is
sometimes justified, a fourth rarely is), the distinct hex-color count
(warns above 6, since a 4-6 color token system should not produce many more
literals than that in the output), and flags any exact match against the
named-cliche hex values above. Treat a warning as "look closer," not as an
automatic failure -- a real brief can justify three type families or a
color that happens to coincide with a cliche hex.

## Restraint doctrine

Pick exactly one place to be bold -- the signature element -- and let the
rest of the layout stay out of its way. A brief with three "look at me"
moments reads as noisy rather than confident, because none of them gets to
land; a brief with zero is often just fear of commitment wearing the
costume of minimalism. Hit this quality floor without narrating that you
did:

- Responsive down to a real mobile width (390px is a reasonable floor, not
  just "flexible in theory")
- Every interactive element has a visible keyboard focus state -- never
  `outline: none` without a replacement indicator
- `prefers-reduced-motion` is respected for any animation beyond a simple
  opacity/color transition:

```css
@media (prefers-reduced-motion: reduce) {
  * {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

- The contrast checklist above passes for every real text/background pairing

## Copy as design material

Words are part of the interface, not decoration on top of it -- write them
with the same intent as spacing and color.

- **Keep verb-noun pairing consistent through a flow.** A control that
  starts an action keeps that exact word through confirmation and result:
  a "Delete environment" button leads to a "delete this environment?"
  confirmation and an "Environment deleted" result, not a generic "Are you
  sure?" and "Done."
- **Name things by what the person controls, not by the underlying
  mechanism.** Someone invites a teammate to a workspace; they do not
  generate an invitation token, even if that is the literal API call
  underneath the button.
- **Errors state what happened and what to do next, without apologizing
  or hedging.** "This file is too large -- keep it under 10 MB" beats "Oops,
  something went wrong."
- **An empty state is an invitation, not a dead end.** "No projects yet --
  create your first one" beats a bare "No data."

## Anti-patterns

- Writing markup or CSS before both the brainstorm and self-critique
  passes are complete
- Landing on any of the six named cliches above on an axis the brief left
  open, with no brief-specific reason for the choice
- Reaching for numbered markers (01 / 02 / 03) as default structure when
  the content is not actually an ordered sequence
- Scattering small animations across the page instead of one deliberate,
  orchestrated moment -- or adding motion at all where the brief's register
  calls for stillness
- Finalizing a palette without running the contrast check on every real
  text/background pairing, or shipping a pairing that fails its threshold
- Skipping the screenshot step because the CSS "should" look right
- Ignoring `lint-tokens.py` warnings without checking whether they are
  justified for this specific brief
- More than one accent color competing for attention, or a signature
  element buried among several other "bold" choices
- Apologetic or vague error copy, and empty states with no path forward
- Treating this skill as a substitute for a project's existing design
  system, component library, or a real accessibility audit

## Reference

- `references/token-system.json` -- the forced schema for Pass 1: colors,
  typefaces, layout concept, signature element, self-critique, and contrast
  checks
- `scripts/contrast-check.py` -- computes WCAG contrast ratio between two
  hex colors (stdlib only, no dependencies)
- `scripts/lint-tokens.py` -- objective lint pass over built CSS: font
  family count, distinct hex-color count, named-cliche hex detection
- The two-pass brainstorm/self-critique structure and the practice of
  naming specific AI-generated-design fingerprints to avoid are adapted
  from concepts in Anthropic's public `frontend-design` skill (Apache 2.0);
  the token-system schema, contrast-check script, lint script, and screenshot
  workflow here are new work for this catalog, written independently rather
  than ported from that skill's implementation (it has none of these as
  runnable artifacts -- it is prose-only)
- WCAG 2.x contrast formulas: https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html
- Playwright CLI screenshots: https://playwright.dev/docs/cli#take-screenshots

## Related Skills

- `python-cli-tools` — CLI with rich/textual TUI if the "frontend" is terminal-based
- `diagram-patterns` — when the UI includes architecture or flow diagrams
