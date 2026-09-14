# The Fly controller (`controller=flycns`)

phyzical arms accept three actions sources over the same WebSocket: **Human**
(mouse-drag + IK), **Auto** (scripted patrol) and **Fly** — a mapped fruit-fly
nervous system driving the arm. This document is the design reference for the
Fly controller: what the biology is, what our mapping is, and what ends up in
the episode data.

## The science: MaleCNS

In 2025, [Google Research and HHMI Janelia published
**MaleCNS**](https://blog.google/innovation-and-ai/technology/research/male-fruit-fly-brain-map/)
— the first complete central nervous system map of an adult male fruit fly
(*Drosophila melanogaster*): brain **and** ventral nerve cord, reconstructed
from electron microscopy with AI segmentation.

Key numbers we rely on:

| | |
|---|---|
| Neurons reconstructed | **~166,000+** (brain + ventral nerve cord) |
| R1–R6 photoreceptors (achromatic / motion pathway) | **3,335** |
| R7/R8 photoreceptors (feature / colour pathway) | **811** |
| Release | MaleCNS v1.0, **CC BY** |

The dataset is a *connectome*: which neuron synapses onto which, at what
strength. It is not a trained model and contains no behaviour by itself —
which is exactly why it is interesting as a **controller**: the wiring is
fixed, public, and reproducible by anyone.

## The mapping: `malecns_v1_visual_crop`

We do not simulate 166K neurons in a browser tab. The Fly controller uses a
**visual crop** — the retina→descending-neuron slice of the graph — behind a
small, committed interface:

```
 scene camera (64×64 crop)
        │
        ▼
 ommatidia sampling            61 pooled hex cells (HUD-matched);
 R1–R6 + R8 channels           source counts (3,335 / 811) kept as metadata
        │
        ▼
 fixed interneuron wiring      lamina/medulla-shaped pooling: motion
 (no training, no gradients)   antisymmetry → turn/lift, salience → drive
        │
        ▼
 descending-neuron readout     DNp20-style yaw, DNpe017-style drive,
 (turn, lift, drive, grip)     saccadic hold at ~4–5Hz
        │
        ▼
 ee_delta commands             same WebSocket, same episode schema
```

Dopamine-style **teach events** modulate the readout without rewiring it:

| Event | Trigger | Effect |
|---|---|---|
| `PPL101 (aversive)` | collision / workspace bound / drop | forward drive gated down, turn-away bias injected, decays over ~1s |
| `PAM (reward)` | task success criterion | approach gain reinforced, decays slowly |

This mirrors the fly's punishment/reward dopamine circuitry in *function*
(gain modulation), not in mechanism.

### What is biology and what is engineering

Be precise about this — it is also the footer disclaimer on phyzical.org:

- **Biology (CC BY, from MaleCNS v1.0):** the cell counts, the pathway
  structure (photoreceptors → optic lobe → descending neurons), the
  cell-type names (R1–R6, R8, DNp20, DNpe017, PPL101, PAM), and the
  behavioural motifs (saccades, habituation, dopamine gating).
- **Engineering (this repo):** the 61-ommatidia pooling resolution, the
  seeded reduced weight projection in `graph.py`, the gain constants, and
  the mapping of DN scalars onto `ee_delta`. The runtime interface is
  designed so distilled real-crop weights can replace `FixedGraph.project`
  without touching anything downstream.

**Fly mode is a mapped connectome controller. It is not a trained policy and
not a claim of animal-level dexterity.**

## What lands in the data

Fly episodes use the exact same schema as Human and Auto episodes
(`schema/episode.schema.json`), with three additions:

1. top-level `"controller": "flycns_v1"` and a `"fly"` metadata block
   (graph id, photoreceptor counts, readout cells, teach events),
2. per-frame `dn_readout` (turn/lift/drive/grip scalars) and `fly_stim`
   (stimulus mean + habituation),
3. `control_mode: "flycns"`.

Controller-aware QC reads them directly: Human episodes are scored on
smoothness and success; Fly episodes on **collision rate, drop events and
visual habituation** (a fly staring at a static scene stops producing
stimulus — such episodes are rejected).

The `controller` tag is written into on-chain provenance metadata, so
datasets can be filtered by actions source at purchase time
(`human` / `auto` / `flycns`).

## Why bother?

- **Differentiated rollouts** — fly episodes explore the workspace with
  saccadic, reactive dynamics no human or script produces; useful as
  contrast sets and control baselines against human demonstrations.
- **A reproducible controller** — anyone can re-run the exact same wiring;
  there is no checkpoint to leak or drift.
- **A safety layer (roadmap)** — HYBRID tasks let a human drive strategy
  while the fly reflex guardrail cuts in on imminent collision
  (see phyzical.org task T-001, and the roadmap item
  "Fly controller · visual crop → hybrid safety layer").
- **elizaOS profile** — the elizaOS robot stack gains a `FlyController`
  profile alongside human teleoperation; same `trajectory_db`, different
  actions source.

## Attribution

MaleCNS v1.0 © Google Research & HHMI Janelia, released **CC BY**. This
repository's mapping is an engineering interface built on top of the
published resource; it is not affiliated with or endorsed by either
institution.
