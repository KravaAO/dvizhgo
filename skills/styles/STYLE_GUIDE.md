# DvizhGo Visual Style Guide

## 1. Core idea

DvizhGo must not look like a typical SaaS dashboard, LMS, startup landing page, or "AI product".

The visual language is:

**playful editorial game UI + printed poster + classroom control system**

The interface should feel energetic, slightly rebellious, tactile, and easy to understand from a distance.

The product is used during live lessons, often from a projector, so hierarchy and large actions matter more than information density.

The design should feel recognizable even if the DvizhGo logo is removed.

---

## 2. Main visual principles

### 2.1 Anti-SaaS

Avoid the standard modern SaaS formula:

- dark navy background;
- purple/blue glowing gradients;
- glassmorphism;
- many rounded cards;
- soft drop shadows everywhere;
- "dashboard" layouts with many widgets;
- generic startup illustrations;
- excessive explanatory copy;
- hero section with badge + heading + paragraph + CTA cards.

DvizhGo should look more like a live game interface or printed event poster than a productivity dashboard.

---

### 2.2 Hard geometry

Prefer:

- straight edges;
- clear borders;
- large rectangular interactive zones;
- hard divisions between sections;
- 2px dark borders;
- square or nearly square controls;
- oversized typography.

Rounded corners are not forbidden, but should be rare and functional.

Do not make every element a rounded card.

---

### 2.3 Low information density

One screen should have one dominant purpose.

Good:

- two giant actions;
- one active lesson state;
- one room code;
- one duel;
- one reflection result;
- one large question.

Bad:

- six statistic cards;
- sidebars full of metadata;
- multiple mini-panels;
- explanatory text everywhere.

The UI should remain understandable from a projector.

---

## 3. Color system

Current core palette:

```css
:root {
  --paper: #eee7d9;
  --ink: #171714;
  --signal: #ff5a36;
  --petrol: #164d4b;
  --chalk: #f8f3e9;
  --faded: #746e63;
}
```

### Roles

**Paper — `#eee7d9`**
- default public/background color;
- warm, physical, slightly retro;
- replaces white SaaS backgrounds.

**Ink — `#171714`**
- primary text;
- borders;
- large blocks;
- strong contrast;
- should feel almost printed.

**Signal — `#ff5a36`**
- high-energy accent;
- important actions;
- LIVE indicators;
- reactions;
- visual punctuation;
- use sparingly.

**Petrol — `#164d4b`**
- secondary strong surface;
- drawers;
- teacher-control areas;
- contrast against warm paper.

**Chalk — `#f8f3e9`**
- text on dark/petrol surfaces;
- slightly warmer than pure white.

### Color rule

Do not introduce random purple/blue gradients unless a future feature explicitly requires a temporary game-state color.

New colors must have a semantic role.

---

## 4. Brand treatment

Primary wordmark:

**DvizhGO**

The word `GO` is the visual accent.

Recommended pattern:

```css
.logo-go {
  background: var(--ink);
  color: var(--paper);
  transform: rotate(-2deg);
  box-shadow: 4px 4px 0 var(--signal);
}
```

The `GO` treatment can reappear in large display typography, but do not repeat it everywhere.

The wordmark should feel printed/stamped manually without becoming a literal stamp graphic.

Do not use decorative seals, certification stamps, or fake labels around the logo.

---

## 5. Typography

### Display typography

Use very large, heavy text with aggressive spacing.

Characteristics:

- `font-weight: 900–1000`;
- strong negative letter spacing;
- uppercase is acceptable for large action states;
- compact line height around `0.82–0.95`.

Examples:

- `УВІЙТИ В КІМНАТУ`
- `СТВОРИТИ КІМНАТУ`
- `DUEL`
- `BREAK`
- `REFLECTION`

Display text is part of the composition, not just content.

### Utility typography

For system labels, metadata and mode IDs, use a monospace feel:

```css
font-family: "Courier New", monospace;
text-transform: uppercase;
letter-spacing: .1em;
font-size: 10px–12px;
```

Examples:

- `01 / STUDENT`
- `ROOM LIVE`
- `12 ONLINE`
- `TEACHER ACCESS`

### Body copy

Use as little body copy as possible.

If the interface can communicate through layout and labels, remove the paragraph.

---

## 6. Layout language

### Public entry page

Preferred structure:

```text
┌────────────────────────────────────────────┐
│ DvizhGO      public links          LIVE    │
├──────────────────────┬─────────────────────┤
│                      │                     │
│  VISUAL / EMOJI      │  JOIN ROOM          │
│  BRAND SPACE         │                     │
│                      ├─────────────────────┤
│                      │  CREATE ROOM        │
│                      │                     │
├──────────────────────┴─────────────────────┤
│ small footer                               │
└────────────────────────────────────────────┘
```

The two room actions should feel like large zones, not cards.

### Room / lesson page

Preferred structure:

```text
header
────────────────────────────────

            ACTIVE STAGE

       current lesson activity

────────────────────────────────
 compact teacher controls / dock
```

The center is a **stage**.

Do not create a permanent dashboard of cards.

The same stage changes state:

```text
Lobby
→ Idle lesson
→ Question
→ Duel
→ Vote
→ Break
→ Reflection
```

---

## 7. Interactions

### Create Room

Creation should be instant.

Do not ask for:

- room title;
- session mode;
- theme;
- settings;
- quiz selection;

before creating the room.

Flow:

```text
Create Room
→ room created
→ lobby
→ settings can be changed inside room
```

### Join Room

Only ask for the minimum required:

- room code;
- student name.

No student registration in the main classroom flow.

---

## 8. Animation language

Animations should behave like reactions or game events, not ambient SaaS decoration.

Preferred:

- emoji peeking from edges;
- emoji pop/reveal;
- rigid slides;
- short overshoot;
- block transitions;
- text replacement;
- quick screen-state changes;
- blinking LIVE indicators.

Avoid:

- endless glowing gradients;
- slow floating glass cards;
- excessive particle backgrounds;
- continuous motion everywhere.

### Emoji rule

Emoji/reactions can become a signature visual pattern.

Examples:

- 🤨
- 😎
- 🗿
- 👀
- 🔥

They should appear unexpectedly and temporarily.

They should not permanently fill empty space.

A good animation:

```text
hidden
→ fast reveal
→ slight overshoot
→ hold
→ disappear
```

Rare events are funnier than constant events.

---

## 9. Buttons and controls

### Primary actions

Primary actions should be visually physical.

Good pattern:

```css
border: 2px solid var(--chalk);
background: var(--signal);
box-shadow: 6px 6px 0 var(--chalk);
```

Hover can shift the element and increase the hard shadow.

Avoid soft shadows and glow for normal buttons.

### Large navigation actions

Room entry actions should occupy substantial screen area.

Example:

```text
01 / STUDENT

УВІЙТИ
В КІМНАТУ      ↗
```

The entire zone is clickable.

---

## 10. Surfaces

Avoid nesting surfaces unnecessarily.

Preferred hierarchy:

1. page background;
2. one large split/section;
3. activity stage;
4. temporary drawer/modal only when needed.

Drawers can use `--petrol`.

Forms should often use simple underline inputs instead of rounded input boxes.

---

## 11. Public navigation

Public header may contain a small set of links such as:

- Головна
- Як це працює
- Для викладачів
- Про DvizhGo

Keep navigation visually secondary.

Do not let the header compete with the two primary room actions.

---

## 12. Classroom UI rules

During a live lesson:

- important information must be readable from a distance;
- no tiny charts;
- no dense tables on the projector-facing stage;
- teacher-only details can live in drawers;
- students should always know the current state;
- teacher controls should remain predictable;
- fun elements must never obscure an answer or block interaction.

---

## 13. Product-specific activity styling

Activity types may change the composition, but should remain inside the DvizhGo design system.

### Duel

Use:
- huge participant names;
- hard split;
- strong VS;
- short live animation.

Avoid two generic cards.

### Question

Use:
- large question;
- large answer zones;
- minimal chrome.

### Break

Can become more expressive and playful.

### Reflection

Can be calmer, but should still use the same geometry and typography.

### Assessment

Reduce reactions and animation, but do not switch to a generic corporate design.

---

## 14. Forbidden patterns

Do not introduce the following without an explicit product reason:

- purple SaaS gradients;
- glassmorphism;
- frosted glass cards;
- card grids as a default page structure;
- 20px rounded corners on every component;
- generic dashboard statistic cards;
- huge amounts of explanatory copy;
- meaningless badges;
- decorative "AI" sparkles everywhere;
- illustrations of people using laptops;
- random gradient text;
- floating cards in the background;
- decorative stamps/seals;
- ticker/marquee elements on the public home page unless specifically re-approved;
- permanent decorative emoji fields.

---

## 15. Decision rule

Before adding any visual element, ask:

1. Does this help the user act?
2. Does it clarify the current live state?
3. Does it strengthen the DvizhGo identity?
4. Is it still readable on a projector?
5. Could the same thing be done with less UI?

If the answer is no, remove it.

---

## 16. Short definition

When uncertain, design DvizhGo as:

> **A playful live classroom control system designed like a bold printed game interface, not a SaaS dashboard.**
