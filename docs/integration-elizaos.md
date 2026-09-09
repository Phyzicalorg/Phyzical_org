# phyzical × elizaOS — Integration Design

**Status:** data-supply layer shipping (this repo) · flywheel in design
**Audience:** elizaOS contributors, robotics data consumers, phyzical contributors

## 1. The complementarity

The [elizaOS](https://github.com/elizaOS/eliza) robotics stack (developed in
[`elizaOS/research`](https://github.com/elizaOS/research)) is a full
brain-and-body pipeline for embodied agents:

- **Simulation** — MuJoCo / MJX scenes and env wrappers
- **Training** — Alberta continual-RL, text-conditioned policies, skill trainers
- **Data** — a unified SQLite `trajectory_db` (trajectories, planner steps,
  50–100Hz `control_frames`, `embodied_contexts`)
- **Embodiment** — profile-driven robots (`RobotProfileId`), first shipping
  profiles Hiwonder AiNex and ASIMOV-1, driven through a WebSocket bridge
  (backends: mock / mujoco / ros / isaac) surfaced to agents via
  `@elizaos/plugin-ainex`

What this stack does not have is a scalable source of **human demonstration
data**. RL from scratch is sample-inefficient; the standard remedy —
imitation warm-starts and offline RL — needs diverse human demos, and
collecting them traditionally requires robot hardware and lab time.

[phyzical](https://phyzical.org) is exactly that missing supply side: a
browser teleoperation platform where anyone produces 30–60Hz manipulation
demonstrations with verifiable onchain provenance. No hardware, global reach,
game-like onboarding.

> **phyzical is the fuel station; elizaOS robots are the fleet.**

## 2. Phase 1 — data supply (this repo)

```
phyzical episode JSON ──▶ import_phyzical.py ──▶ trajectory_db (SQLite)
   30–60Hz frames             stdlib-only             source='phyzical'
   task language              converter               ready for trainers
   onchain provenance
```

- The [episode schema](../schema/episode.schema.json) captures joint states,
  EE poses, object poses, per-frame actions, task language and provenance.
- The [converter](../converters/eliza_robot/import_phyzical.py) writes the
  exact `trajectory_db` DDL, following the precedent of elizaOS's own
  external importer (`import_hyperscape.py`): external world in,
  unified schema out, `source` field marks origin.
- Human demos correctly leave `llm_calls` empty — attribution between human
  and policy data stays clean at the schema level.

## 3. Phase 2 — profile-matched collection

phyzical task scenes align to elizaOS `RobotProfileId` morphologies (URDF /
MJCF), so crowdsourced demos target robots the elizaOS stack actually
simulates and deploys — starting with tabletop arms, extending to humanoid
profiles (AiNex, ASIMOV-1). The `robot_profile` field already exists in the
episode schema.

To eliminate cross-engine physics gap for contact-rich tasks, the roadmap
includes a MuJoCo-backed scene mode where the browser renders and inputs
while physics runs server-side — the same MuJoCo the policies train in.

## 4. Phase 3 — the human-in-the-loop flywheel

The highest-value integration: **DAgger-style correction data.**

1. An elizaOS text-conditioned policy rolls out inside a phyzical browser
   scene (policy segments logged with `llm_calls` / policy attribution).
2. When the policy stalls or fails, the human contributor takes over with
   the mouse (`control_mode: "policy_takeover"` — already in the schema).
3. Takeover segments — the exact states where the policy is weak — flow back
   through this converter as premium training data.
4. Retrain, redeploy, repeat.

Contributors stop demonstrating from scratch and start supervising robots —
faster for humans, and the data lands precisely on the policy's failure
distribution, which is what imitation learning actually needs.

## 5. Provenance

Every accepted episode carries a Data ID and content hash anchored onchain.
A consumer (human lab or an elizaOS agent acting as an autonomous dataset
buyer) can recompute the canonical payload hash and verify origin before
training. Provenance metadata survives conversion inside
`trajectories.metadata_json.provenance`.

## 6. Non-goals (for now)

- Not a fork or redistribution of the elizaOS robot stack — we track its
  public schema and conventions, and keep attribution.
- No claim of upstream endorsement; this is an open, schema-level
  integration that anyone can run today.

## Links

- phyzical: <https://phyzical.org> · [@phyzical_org](https://x.com/phyzical_org)
- elizaOS: <https://github.com/elizaOS/eliza> · <https://docs.elizaos.ai>
- elizaOS robotics research: <https://github.com/elizaOS/research>
