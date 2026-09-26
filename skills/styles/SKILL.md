---
name: dvizhgo-ui
description: Preserve and extend the DvizhGo visual language when creating or modifying frontend pages, components, activities, room/lobby interfaces, teacher controls, forms, animations, and responsive layouts.
---

# DvizhGo UI Skill

Use this skill for every task that changes visible DvizhGo UI.

## Purpose

Maintain a consistent visual identity:

**playful editorial game interface + printed poster geometry + live classroom control system**

The product must not drift toward generic SaaS/dashboard aesthetics as features are added.

---

## Required context

Before making UI changes:

1. Read `STYLE_GUIDE.md`.
2. Read `AGENT_INSTRUCTIONS.md`.
3. Inspect the existing page/component being modified.
4. Reuse existing CSS variables and interaction patterns.
5. Identify whether the screen is:
   - public;
   - teacher-only;
   - student;
   - projector/live stage.

Projector/live-stage screens require the lowest information density.

---

## Design process

### Step 1 — Define the screen's single purpose

Write internally:

```text
Primary user:
Primary action:
Current live state:
Secondary actions:
```

If there are several equally important primary actions, simplify.

---

### Step 2 — Choose the layout pattern

Prefer one of these:

#### Split action page

For public navigation / entry:

```text
brand / visual area | giant action area
```

#### Stage page

For room/lobby/live lesson:

```text
header
stage
teacher controls
```

#### Drawer detail

For:
- participants;
- room settings;
- teacher-only metadata;
- secondary controls.

Do not convert these into permanent dashboard cards.

---

### Step 3 — Apply DvizhGo tokens

Default palette:

```css
--paper: #eee7d9;
--ink: #171714;
--signal: #ff5a36;
--petrol: #164d4b;
--chalk: #f8f3e9;
--faded: #746e63;
```

Use thick dark borders and hard color blocks.

---

### Step 4 — Typography

For primary state/action:

- very large;
- bold;
- compressed line height;
- negative letter spacing.

For utility labels:

- monospace;
- uppercase;
- small;
- tracked.

Reduce paragraph text aggressively.

---

### Step 5 — Interaction

Every action should feel direct.

Examples:

```text
Create Room
→ immediate room creation
```

not:

```text
Create Room
→ setup wizard
→ mode
→ name
→ theme
→ settings
→ create
```

Do not add extra configuration steps unless the feature genuinely requires them.

---

### Step 6 — Animation

If the screen needs life, first consider a temporary reaction.

Preferred signature:

```text
emoji hidden
→ peek/pop
→ short hold
→ disappear
```

Use one memorable motion rather than many ambient effects.

---

### Step 7 — Responsive check

Desktop must work well on:
- teacher laptop;
- classroom projector.

Mobile must work for:
- student joining;
- answering;
- reactions.

Do not shrink desktop density blindly. Recompose if needed.

---

## Activity-specific guidance

### Lobby

Keep:
- room code available;
- compact participant presence;
- clear teacher start/control;
- minimal settings visible.

### Duel

Prefer:
- split composition;
- participant names;
- strong VS moment;
- answer/vote state.

Avoid:
- two soft cards in a generic dashboard.

### Quiz

Prefer:
- large central question;
- large answer regions;
- visible progress;
- minimal peripheral controls.

### Reflection

Keep calmer but retain hard geometry and DvizhGo typography.

### Assessment

Disable/reduce playful effects rather than changing to a separate generic design system.

---

## Hard prohibitions

Do not introduce as default:

- glassmorphism;
- purple SaaS gradients;
- soft rounded dashboard cards;
- random glow;
- generic stat widgets;
- decorative badges with no function;
- long marketing copy inside product screens;
- decorative stamps/seals;
- marquee/ticker strips on the public menu;
- permanent emoji decoration;
- account/login requirements for students unless explicitly requested.

---

## Review heuristic

A DvizhGo screen should feel closer to:

- a multiplayer game menu;
- an event poster;
- a live control panel;
- a classroom projection screen;

than to:

- Notion;
- Linear;
- Stripe dashboard;
- a generic LMS;
- a generic AI startup landing page.

Do not copy any specific external product.

---

## Completion checklist

Before finishing a UI task, verify:

1. One primary visual focus.
2. Minimal copy.
3. Existing palette preserved.
4. Strong geometry/borders.
5. No accidental SaaS drift.
6. Projector readability.
7. Mobile usability.
8. Temporary, purposeful animation only.
9. `DvizhGO` wordmark treatment preserved where branding appears.
10. New component can coexist visually with existing pages.

If a requested feature conflicts with these rules, preserve functionality first but adapt presentation to the closest compatible DvizhGo pattern.
