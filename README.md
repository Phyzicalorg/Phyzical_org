<p align="center">
  <img src="https://phyzical.org/icon.png" width="96" alt="phyzical" />
</p>

<h1 align="center">phyzical</h1>

<p align="center">
  <b>Browser-based robot teleoperation data platform.<br/>
  The fuel station for agent robot stacks — <a href="https://github.com/elizaOS/eliza">elizaOS</a>-ready by design.</b>
</p>

<p align="center">
  <a href="https://phyzical.org">phyzical.org</a> ·
  <a href="https://x.com/phyzical_org">@phyzical_org</a> ·
  <a href="#quickstart-convert-a-phyzical-episode-for-elizaos">Quickstart</a> ·
  <a href="docs/integration-elizaos.md">elizaOS Integration</a>
</p>

---

## What is phyzical

**phyzical** turns anyone with a browser into a robot data contributor. Users
teleoperate simulated robot arms like a 3D web game — drag the end-effector,
inverse kinematics solves the joints — and every session produces a
**30–60Hz demonstration trajectory** (joint positions, end-effector pose,
object poses, actions) ready for **Vision-Language-Action (VLA)** and
imitation-learning training. Episode provenance (Data ID + content hash +
contributor) is anchored on-chain.

No robot hardware. No expertise. Just a browser tab.

```
 browser teleop            phyzical backend              agent robot stacks
┌────────────────┐      ┌─────────────────────┐      ┌──────────────────────┐
│ Unity WebGL    │      │ quality checks       │      │ elizaOS eliza_robot  │
│ mouse-drag IK  │ ───▶ │ episode store        │ ───▶ │ trajectory_db        │
│ 30–60Hz record │      │ onchain provenance   │      │ imitation / RL       │
└────────────────┘      └─────────────────────┘      └──────────────────────┘
```

## Why elizaOS

[elizaOS](https://github.com/elizaOS/eliza) is an open-source agentic
operating system. Its robotics stack (developed in
[`elizaOS/research`](https://github.com/elizaOS/research) — `robot/` and
`plugin-ainex/`) ships everything an embodied agent needs **except large-scale
human demonstration data**:

| elizaOS robot stack has | it needs |
|---|---|
| MuJoCo / MJX simulation | diverse human manipulation demos |
| Alberta continual-RL + text-conditioned policy trainers | imitation warm-starts instead of exploring from zero |
| A unified SQLite **`trajectory_db`** (trajectories, steps, `control_frames`, `embodied_contexts`) | high-frequency demonstration frames to fill it |
| Profile-driven robots (`RobotProfileId`: Hiwonder AiNex, ASIMOV-1, …) | demos collected against those same morphologies |
| WebSocket bridge backends (mock / mujoco / ros / isaac) | a zero-install frontend where humans can actually demonstrate |

**phyzical is that missing supply side.** Crowdsourced browser demonstrations
in, `trajectory_db`-compatible training episodes out.

This repo contains the open pieces of that pipeline:

| Path | What it is |
|---|---|
| [`schema/episode.schema.json`](schema/episode.schema.json) | phyzical episode format (JSON Schema, v1) |
| [`schema/MAPPING.md`](schema/MAPPING.md) | field-by-field mapping: phyzical episode → elizaOS `trajectory_db` |
| [`converters/eliza_robot/import_phyzical.py`](converters/eliza_robot/import_phyzical.py) | **working converter** — phyzical episodes → elizaOS-compatible SQLite |
| [`examples/episode_block_sorting.json`](examples/episode_block_sorting.json) | sample episode (90 frames @30Hz, block-sorting task) |
| [`docs/integration-elizaos.md`](docs/integration-elizaos.md) | full integration design: data supply, DAgger loop, agent roles |

## Quickstart: convert a phyzical episode for elizaOS

Requires Python 3.10+. No dependencies — stdlib only.

```bash
python3 converters/eliza_robot/import_phyzical.py \
    examples/episode_block_sorting.json \
    --db trajectories.db
```

Output is a SQLite database using the **same DDL as
`eliza_robot/trajectory_db/schema.py`** (attributed, MIT), so it drops
straight into the elizaOS robot training pipeline:

```
trajectories        1 row   — the episode (source='phyzical', is_training_data=1)
trajectory_steps    1 row   — the human teleoperation macro-step
control_frames     90 rows  — 30Hz joint/EE/action frames
embodied_contexts   1 row   — object poses + task description
```

This mirrors how elizaOS already ingests external episode sources
(see their `trajectory_db/import_hyperscape.py`) — phyzical is simply the
next source: `source="phyzical"`.

## The loop we're building

1. **Data supply (this repo, now)** — browser demos → `trajectory_db` →
   imitation warm-starts for Alberta continual-RL and text-conditioned
   policies.
2. **Profile-matched tasks** — phyzical scenes pinned to elizaOS
   `RobotProfileId` morphologies (URDF/MJCF), so demos target robots the
   stack actually simulates and deploys.
3. **Human-in-the-loop flywheel (next)** — elizaOS policies roll out inside
   phyzical's browser scenes; humans take over when the policy fails
   (DAgger-style); correction segments flow back as high-value training data.
4. **Agent data economy** — elizaOS agents as autonomous dataset consumers,
   verifying episode provenance (Data ID + content hash) on-chain before
   purchase.

## Links

- Platform: [phyzical.org](https://phyzical.org)
- X / Twitter: [@phyzical_org](https://x.com/phyzical_org)
- elizaOS: [github.com/elizaOS/eliza](https://github.com/elizaOS/eliza) ·
  [docs.elizaos.ai](https://docs.elizaos.ai)
- elizaOS robotics research: [github.com/elizaOS/research](https://github.com/elizaOS/research)

## License

MIT — see [LICENSE](LICENSE). The embedded `trajectory_db` DDL originates
from [elizaOS/research](https://github.com/elizaOS/research) (MIT) and is
reproduced with attribution in the converter source.
