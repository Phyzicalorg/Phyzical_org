# flycns — the Fly connectome controller

> A [MaleCNS](https://blog.google/innovation-and-ai/technology/research/male-fruit-fly-brain-map/)
> visual crop wired to the scene camera: photoreceptors in, descending-neuron
> readout out, dopamine-style teach events on collision or success.
> Fixed biological wiring, experimental readout — tagged `controller=flycns`.

Full design doc: [`docs/flycns.md`](../../docs/flycns.md)

## Layout

| File | Role |
|---|---|
| [`hexeye.py`](hexeye.py) | 61-ommatidia compound eye: hex sampling, R1–R6 + R8 channels, photoreceptor adaptation (visual habituation) |
| [`graph.py`](graph.py) | fixed wiring (`malecns_v1_visual_crop` interface): structured pooling → DN scalars, plus PPL101/PAM neuromodulation |
| [`controller.py`](controller.py) | `FlyCNSController` — saccadic pursuit, reflex guardrail, teach-event log, `ee_delta` output |
| [`demo.py`](demo.py) | runnable T-F01 "Keep Target Centered" rollout → schema-valid episode JSON |

## Run it

```bash
# generate a fly episode (deterministic, stdlib only)
python3 controllers/flycns/demo.py --out examples/episode_fly_keep_centered.json

# import it into an elizaOS-compatible trajectory_db
python3 converters/eliza_robot/import_phyzical.py \
    examples/episode_fly_keep_centered.json --db trajectories.db
```

The demo drives the T-F01 scene: saccadic pursuit of a drifting target, a
scripted disturbance at t=5s that slams the arm into the workspace bound
(→ `PPL101 aversive`, drive gated down, turn-away), recovery, then a
centred-hold success (→ `PAM reward`).

## Use it as a library

```python
from controllers.flycns import FlyCNSController

ctrl = FlyCNSController()
out = ctrl.step(frame_64x64, dt=1/30, collision=False, success=False)
out["action"]       # {"type": "ee_delta", "cmd": [dx, dy, dz, grip]}
out["dn_readout"]   # {"turn": …, "lift": …, "drive": …, "grip": …}
out["fly_stim"]     # {"mean": …, "habituation": …}
ctrl.episode_metadata()  # the episode "fly" block (graph, counts, teach events)
```

**Disclaimer:** Fly mode is a mapped connectome controller. It is not a
trained policy and not a claim of animal-level dexterity. MaleCNS v1.0
© Google Research & HHMI Janelia, CC BY; the weight reduction here is an
engineering interface (see `graph.py` docstring).
