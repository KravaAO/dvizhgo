# DvizhGo UI Agent Pack

This folder contains the current visual design rules for DvizhGo.

Files:

- `AGENT_INSTRUCTIONS.md` — short persistent constraints to place in repository/agent context.
- `STYLE_GUIDE.md` — detailed design system and visual philosophy.
- `SKILL.md` — workflow skill for UI tasks.

Recommended repository placement:

```text
/
├─ AGENT_INSTRUCTIONS.md
├─ docs/
│  └─ STYLE_GUIDE.md
└─ .agent/
   └─ skills/
      └─ dvizhgo-ui/
         └─ SKILL.md
```

If the coding agent supports project-level instruction files such as `AGENTS.md`, copy the contents of `AGENT_INSTRUCTIONS.md` into the UI/design section of that file or point it to the style guide.

The current reference direction is based on the approved DvizhGo menu:
- warm paper background;
- near-black ink;
- signal orange;
- petrol teacher surfaces;
- hard borders;
- huge actions;
- minimal text;
- `GO` wordmark accent;
- temporary emoji reactions;
- no generic SaaS cards/glassmorphism.
