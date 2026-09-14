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
| [`schema/episode.schema.json`](schema/episode.schema.json) | phyzical episode format (JSON Schema, v1) — incl. `controller` / `fly` fields |
| [`schema/MAPPING.md`](schema/MAPPING.md) | field-by-field mapping: phyzical episode → elizaOS `trajectory_db` |
| [`converters/eliza_robot/import_phyzical.py`](converters/eliza_robot/import_phyzical.py) | **working converter** — phyzical episodes → elizaOS-compatible SQLite |
| [`controllers/flycns/`](controllers/flycns/) | **working Fly controller** — MaleCNS visual crop → descending-neuron readout → `ee_delta` |
| [`examples/episode_block_sorting.json`](examples/episode_block_sorting.json) | sample human episode (90 frames @30Hz, block-sorting task) |
| [`examples/episode_fly_keep_centered.json`](examples/episode_fly_keep_centered.json) | sample fly episode (360 frames @30Hz, `controller=flycns_v1`, PPL101 + PAM teach events) |
| [`docs/integration-elizaos.md`](docs/integration-elizaos.md) | full integration design: data supply, DAgger loop, agent roles |
| [`docs/flycns.md`](docs/flycns.md) | Fly controller design: the MaleCNS science, our mapping, what lands in the data |

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

## The Fly controller (`controller=flycns`)

phyzical arms accept **three actions sources** over the same WebSocket and
the same episode schema: **Human** (mouse-drag + IK — the pre-training core),
**Auto** (scripted patrol — coverage and baselines), and **Fly** — a mapped
fruit-fly nervous system.

In 2025, [Google Research and HHMI Janelia released
**MaleCNS v1.0**](https://blog.google/innovation-and-ai/technology/research/male-fruit-fly-brain-map/)
(CC BY): the first complete central nervous system map of an adult male
fruit fly — **~166,000+ neurons** across brain and ventral nerve cord,
including 3,335 R1–R6 and 811 R7/R8 photoreceptors. The Fly controller wires
a **visual crop** of that graph to the scene camera:

```
 scene camera ──▶ ommatidia sampling ──▶ fixed wiring ──▶ DN readout ──▶ ee_delta
 (64×64 crop)     R1–R6 + R8 channels    no training      turn/lift/       same WebSocket,
                  + habituation          no gradients     drive/grip       same schema
                                              ▲
                              PPL101 (aversive) / PAM (reward)
                              dopamine-style teach events on
                              collision or success
```

Run it — the controller and demo are in this repo, stdlib-only:

```bash
# generate a fly episode (T-F01 "Keep Target Centered", deterministic)
python3 controllers/flycns/demo.py --out examples/episode_fly_keep_centered.json

# import it into the same trajectory_db as human episodes
python3 converters/eliza_robot/import_phyzical.py \
    examples/episode_fly_keep_centered.json --db trajectories.db
```

Fly episodes log `controller=flycns_v1`, per-frame `dn_readout` and
`fly_stim`, and the teach-event history — same schema as human demos,
different actions source. QC is controller-aware (collision rate, drop
events, visual habituation instead of human smoothness), and the
`controller` tag is written into on-chain provenance metadata so datasets
can be filtered by source (`human` / `auto` / `flycns`). In the elizaOS
stack this surfaces as a `FlyController` profile alongside human
teleoperation.

Humans produce the pre-training core; Fly produces **differentiated
rollouts and control baselines** — saccadic, reactive trajectories no human
or script generates. Design doc: [`docs/flycns.md`](docs/flycns.md).

> **Fly mode is a mapped connectome controller. It is not a trained policy
> and not a claim of animal-level dexterity.** MaleCNS v1.0 © Google
> Research & HHMI Janelia, CC BY — the mapping is an engineering interface,
> not a biological claim.

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
- MaleCNS announcement: [blog.google — A map of the male fruit fly brain](https://blog.google/innovation-and-ai/technology/research/male-fruit-fly-brain-map/)

## License

MIT — see [LICENSE](LICENSE). The embedded `trajectory_db` DDL originates
from [elizaOS/research](https://github.com/elizaOS/research) (MIT) and is
reproduced with attribution in the converter source.
