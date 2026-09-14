#!/usr/bin/env python3
"""Run the flycns controller on the T-F01 task and emit a phyzical episode.

Task: **Keep Target Centered** (fly-native, phyzical.org task board T-F01).
A bright target drifts through the workspace on a Lissajous path; the fly
graph must keep it centred in the wrist camera and close the distance.
Success fires PAM reward events; driving into the workspace bound fires a
PPL101 aversive event and the guardrail turns the arm away.

The scene is synthetic and fully deterministic -- no simulator required --
so this doubles as the module's smoke test::

    python3 -m controllers.flycns.demo --out examples/episode_fly_keep_centered.json

The written episode validates against schema/episode.schema.json and imports
with converters/eliza_robot/import_phyzical.py (controller metadata included).

Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

if __package__ in (None, ""):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from controllers.flycns.controller import CONTROLLER_ID, FlyCNSController
else:
    from .controller import CONTROLLER_ID, FlyCNSController

FRAME = 64
HZ = 30
DURATION_S = 12.0
WORKSPACE = 1.0  # EE coordinates live in [-1, 1]^3


def render_frame(ee: list[float], target: list[float]) -> list[list[float]]:
    """Wrist-camera view: target rendered relative to the end-effector."""
    # Camera is centred on the EE; the target appears offset by (target - ee).
    du = (target[0] - ee[0]) * 0.5 + 0.5
    dv = (target[1] - ee[1]) * 0.5 + 0.5
    # Apparent size grows as z-distance closes.
    dist_z = max(0.05, target[2] - ee[2])
    radius = max(2.0, 6.0 / (dist_z * 10.0))

    frame = [[0.02] * FRAME for _ in range(FRAME)]
    cx, cy = du * (FRAME - 1), dv * (FRAME - 1)
    r_i = int(radius) + 2
    for py in range(max(0, int(cy) - r_i), min(FRAME, int(cy) + r_i + 1)):
        for px in range(max(0, int(cx) - r_i), min(FRAME, int(cx) + r_i + 1)):
            d = math.hypot(px - cx, py - cy)
            if d <= radius:
                frame[py][px] = 1.0
            elif d <= radius + 1.5:
                frame[py][px] = max(frame[py][px], 1.0 - (d - radius) / 1.5)
    return frame


def target_at(t: float) -> list[float]:
    """Lissajous drift, deterministic."""
    return [
        0.55 * math.sin(0.9 * t),
        0.45 * math.sin(1.4 * t + 1.2),
        0.55 + 0.25 * math.sin(0.5 * t + 0.4),
    ]


def joint_pos_for(ee: list[float]) -> list[float]:
    """Analytic 4-DOF pose for the recorded frames (base yaw + planar 2-link)."""
    base = math.atan2(ee[1], ee[0] + 1.4)
    reach = min(1.6, math.hypot(ee[0] + 1.4, ee[1]))
    elbow = math.acos(max(-1.0, min(1.0, (reach**2 - 2 * 0.9**2) / (2 * 0.9**2))))
    shoulder = math.atan2(ee[2], reach) + elbow / 2
    wrist = -(shoulder + elbow) * 0.5
    return [round(v, 4) for v in (base, shoulder, -elbow, wrist)]


def run(out_path: str, *, quiet: bool = False) -> dict:
    ctrl = FlyCNSController()
    ee = [0.0, 0.0, 0.0]
    frames = []
    dt = 1.0 / HZ
    n = int(DURATION_S * HZ)
    centered_since = None
    successes = 0

    for i in range(n):
        t = i * dt
        target = target_at(t)
        cam = render_frame(ee, target)

        # Event detection from the previous tick's motion.
        collision = abs(ee[0]) >= WORKSPACE or abs(ee[1]) >= WORKSPACE
        err = math.hypot(target[0] - ee[0], target[1] - ee[1])
        if err < 0.12:
            centered_since = t if centered_since is None else centered_since
        else:
            centered_since = None
        success = centered_since is not None and (t - centered_since) >= 1.0
        if success:
            centered_since = None  # re-arm
            successes += 1

        out = ctrl.step(cam, dt, collision=collision, success=success)

        cmd = out["action"]["cmd"]
        ee[0] = max(-WORKSPACE, min(WORKSPACE, ee[0] + cmd[0]))
        ee[1] = max(-WORKSPACE, min(WORKSPACE, ee[1] + cmd[1]))
        ee[2] = max(0.0, min(0.9, ee[2] + cmd[2] * 0.5))

        # Deterministic external disturbance ("gust") at t=5s: shoves the EE
        # into the workspace bound so the PPL101 aversive guardrail fires.
        if 5.0 <= t < 5.45:
            ee[0] = min(WORKSPACE, ee[0] + 0.14)

        frames.append(
            {
                "t": round(t, 4),
                "joint_pos": joint_pos_for(ee),
                "ee_pose": {"xyz": [round(v, 4) for v in ee]},
                "gripper": round(cmd[3] * 0.08, 4),
                "object_poses": {"target": {"xyz": [round(v, 4) for v in target]}},
                "action": out["action"],
                "dn_readout": out["dn_readout"],
                "fly_stim": out["fly_stim"],
            }
        )

    episode = {
        "schema": "phyzical-episode-v1",
        "episode_id": "EP_flycns_demo01",
        "task_id": "keep_target_centered_01",
        "task_description": "Keep the moving target centered in the wrist camera and close the distance.",
        "contributor": "0xFLYCNS0000000000000000000000000000DEMO",
        "robot_profile": "phyz_arm4_v1",
        "control_mode": "flycns",
        "controller": CONTROLLER_ID,
        "fly": ctrl.episode_metadata(),
        "sim": {"engine": "unity_webgl", "physics_hz": 60, "record_hz": HZ},
        "duration_s": DURATION_S,
        "success": successes > 0,
        "trajectory": frames,
    }
    payload = json.dumps(episode, separators=(",", ":"), sort_keys=True).encode()
    episode["provenance"] = {
        "data_id": "phyz:robinhood:pending",
        "content_hash": "sha256:" + hashlib.sha256(payload).hexdigest(),
        "anchored_at": None,
    }

    Path(out_path).write_text(json.dumps(episode, indent=2) + "\n", encoding="utf-8")

    if not quiet:
        ev = episode["fly"]["teach_events"]
        ppl = sum(1 for e in ev if e["cell"] == "PPL101")
        pam = sum(1 for e in ev if e["cell"] == "PAM")
        print(f"[flycns demo] {n} frames @{HZ}Hz  controller={CONTROLLER_ID}")
        print(f"[flycns demo] centred-hold successes: {successes}  PAM: {pam}  PPL101: {ppl}")
        print(f"[flycns demo] final habituation: {frames[-1]['fly_stim']['habituation']}")
        print(f"[flycns demo] wrote {out_path}")
    return episode


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Generate a flycns demo episode (T-F01)")
    p.add_argument("--out", default="examples/episode_fly_keep_centered.json")
    p.add_argument("--quiet", "-q", action="store_true")
    args = p.parse_args(argv)
    run(args.out, quiet=args.quiet)


if __name__ == "__main__":
    main()
