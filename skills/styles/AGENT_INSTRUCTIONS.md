# DvizhGo UI — Agent Instructions

These instructions are persistent constraints for all UI work in this repository.

## Goal

Preserve a single recognizable DvizhGo visual language across public pages, teacher pages, room/lobby screens, quiz screens, live activities and future features.

Do not independently modernize the interface into a generic SaaS design.

---

## Non-negotiable rules

1. Do not use purple/blue SaaS gradients as the base visual identity.
2. Do not use glassmorphism.
3. Do not build pages as grids of rounded cards by default.
4. Do not add explanatory text when a clear label/action is enough.
5. Prefer hard borders, large typography and large clickable regions.
6. Use the existing core palette before adding new colors.
7. Keep `GO` visually emphasized in the DvizhGO wordmark.
8. Public room creation should remain one-click unless requirements explicitly change.
9. Room mode/settings belong inside the room, not in a creation wizard.
10. Student join flow should stay minimal: room code + name.
11. The live room center should behave as a stage whose content changes with the activity.
12. Teacher details/settings should be placed in drawers or secondary layers, not permanently occupying the stage.
13. Animations should be short reaction/game events. Avoid constant ambient motion.
14. Emoji/reaction animation is an approved signature pattern.
15. Projector readability has priority over information density.

---

## Approved base colors

```css
--paper: #eee7d9;
--ink: #171714;
--signal: #ff5a36;
--petrol: #164d4b;
--chalk: #f8f3e9;
--faded: #746e63;
```

Do not change the global palette casually.

---

## Preferred visual hierarchy

Use:

- one dominant action/state;
- oversized heading;
- strong border divisions;
- secondary monospace metadata;
- sparse supporting text;
- temporary drawers for detail.

Avoid:

- many equally important panels;
- permanent analytics blocks;
- nested cards.

---

## Component guidance

### Logo

Use `DvizhGO`.

`GO` should have a contrasting block treatment based on `--ink` / `--paper` with `--signal` as a hard offset accent.

### Primary CTA

Physical button feeling:

- strong border;
- hard shadow;
- no glow;
- clear press/hover movement.

### Forms

Prefer flat inputs with strong underline/border.

Avoid generic soft rounded form cards.

### Navigation

Keep public links compact and secondary.

### Room actions

Join/Create should be large interactive regions.

### Live room

Treat central area as a stage, not dashboard.

---

## Activity states

Every activity should answer visually:

- What is happening now?
- What must the student do?
- What can the teacher do next?

Examples:

### Lobby
room code + participants + start/controls.

### Duel
two names / answers + VS + live vote state.

### Question
one question + answers + progress.

### Break
one playful central event.

### Reflection
one reflection prompt / aggregate result.

Do not show unrelated controls inside the main student-facing stage.

---

## Animation rules

Approved:
- emoji peek;
- emoji pop;
- hard slide;
- quick overshoot;
- blinking live state;
- short reveal;
- state transition.

Avoid:
- floating glass blobs;
- continuous card bobbing;
- particles everywhere;
- unnecessary parallax;
- large background motion competing with content.

---

## Before changing UI

Read:

- `STYLE_GUIDE.md`
- this file

Then inspect nearby existing components and reuse established visual patterns.

Do not rewrite the design system because one screen is easier to implement in another style.

---

## Before submitting UI work

Run this checklist:

- [ ] Does it still look like DvizhGo with the logo hidden?
- [ ] Is there one obvious primary state/action?
- [ ] Did I avoid generic SaaS cards?
- [ ] Did I avoid unnecessary text?
- [ ] Did I use the approved palette?
- [ ] Are borders/geometric divisions doing most of the layout work?
- [ ] Is the main content readable from a projector?
- [ ] Are decorative animations temporary and non-blocking?
- [ ] Is mobile still usable?
- [ ] Did I keep room creation/join flow minimal?
- [ ] Did I keep room settings inside the room?
- [ ] Did I avoid introducing a new visual pattern without a reason?

If several answers are "no", revise the UI before considering the task complete.
