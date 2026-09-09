#!/usr/bin/env python3
"""Import phyzical teleoperation episodes into an elizaOS-compatible
``trajectory_db`` SQLite database.

phyzical (https://phyzical.org) episodes are browser-teleoperation
demonstrations recorded at 30-60Hz: joint positions, end-effector pose,
gripper state, object poses, and the user action per frame.

This script normalises each episode into the unified trajectory schema used
by the elizaOS robotics stack (``eliza_robot/trajectory_db``), the same way
elizaOS ingests other external sources (cf. their ``import_hyperscape.py``):

    trajectories        1 row per episode   source='phyzical'
    trajectory_steps    1 macro-step        the human teleoperation session
    control_frames      1 row per frame     joint/EE/action data (30-60Hz)
    embodied_contexts   1 row per episode   object poses + task description

The table DDL below is reproduced from
``elizaOS/research: robot/eliza_robot/trajectory_db/schema.py`` (MIT license,
(c) elizaOS contributors) so this converter runs standalone -- no elizaOS
checkout required. Databases produced here open cleanly inside the elizaOS
robot training pipeline.

Usage::

    python3 import_phyzical.py episode1.json episode2.json --db trajectories.db
    python3 import_phyzical.py exports/*.json --db trajectories.db --summary

Requires Python 3.10+. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

# ---------------------------------------------------------------------------
# DDL -- reproduced from elizaOS/research robot/eliza_robot/trajectory_db/schema.py
# (MIT). Column names match the elizaOS production schema so that databases
# created here are drop-in compatible.
# ---------------------------------------------------------------------------

CREATE_TRAJECTORIES = """\
CREATE TABLE IF NOT EXISTS trajectories (
    id                  TEXT PRIMARY KEY,
    trajectory_id       TEXT UNIQUE NOT NULL,
    agent_id            TEXT NOT NULL,
    source              TEXT,
    archetype           TEXT,
    window_id           TEXT,
    scenario_id         TEXT,
    batch_id            TEXT,
    episode_id          TEXT,
    status              TEXT DEFAULT 'active',
    start_time          REAL,
    end_time            REAL,
    duration_ms         INTEGER,
    total_reward            REAL DEFAULT 0.0,
    reward_components_json  TEXT,
    ai_judge_reward         REAL,
    ai_judge_reasoning      TEXT,
    final_status            TEXT,
    final_pnl           REAL,
    final_balance       REAL,
    episode_length      INTEGER DEFAULT 0,
    metrics_json        TEXT,
    metadata_json       TEXT,
    is_training_data    BOOLEAN DEFAULT 0,
    is_evaluation       BOOLEAN DEFAULT 0,
    used_in_training    BOOLEAN DEFAULT 0,
    created_at          TEXT,
    updated_at          TEXT
);
"""

CREATE_TRAJECTORY_STEPS = """\
CREATE TABLE IF NOT EXISTS trajectory_steps (
    id                      TEXT PRIMARY KEY,
    trajectory_id           TEXT NOT NULL,
    step_number             INTEGER NOT NULL,
    timestamp               REAL,
    observation_json        TEXT,
    action_type             TEXT,
    action_name             TEXT,
    action_params_json      TEXT,
    action_success          BOOLEAN,
    action_result_json      TEXT,
    reward                  REAL DEFAULT 0.0,
    done                    BOOLEAN DEFAULT 0,
    environment_state_json  TEXT,
    reasoning               TEXT,
    metadata_json           TEXT,
    UNIQUE(trajectory_id, step_number),
    FOREIGN KEY (trajectory_id) REFERENCES trajectories(trajectory_id)
);
"""

CREATE_CONTROL_FRAMES = """\
CREATE TABLE IF NOT EXISTS control_frames (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    trajectory_id           TEXT NOT NULL,
    planner_step_id         TEXT,
    timestamp               REAL NOT NULL,
    joint_positions_json    TEXT,
    joint_velocities_json   TEXT,
    joint_targets_json      TEXT,
    imu_roll                REAL,
    imu_pitch               REAL,
    gyro_json               TEXT,
    entity_slots_json       TEXT,
    action_applied_json     TEXT,
    reward                  REAL,
    FOREIGN KEY (trajectory_id)    REFERENCES trajectories(trajectory_id),
    FOREIGN KEY (planner_step_id)  REFERENCES trajectory_steps(id)
);
"""

CREATE_EMBODIED_CONTEXTS = """\
CREATE TABLE IF NOT EXISTS embodied_contexts (
    id                  TEXT PRIMARY KEY,
    trajectory_id       TEXT NOT NULL,
    step_id             TEXT,
    timestamp           REAL,
    entities_json       TEXT,
    camera_views_json   TEXT,
    agent_pose_json     TEXT,
    task_description    TEXT,
    source              TEXT,
    FOREIGN KEY (trajectory_id) REFERENCES trajectories(trajectory_id),
    FOREIGN KEY (step_id)       REFERENCES trajectory_steps(id)
);
"""

INDEX_DDL = [
    "CREATE INDEX IF NOT EXISTS idx_traj_agent ON trajectories(agent_id);",
    "CREATE INDEX IF NOT EXISTS idx_traj_source ON trajectories(source);",
    "CREATE INDEX IF NOT EXISTS idx_traj_status ON trajectories(status);",
    "CREATE INDEX IF NOT EXISTS idx_traj_training ON trajectories(is_training_data);",
    "CREATE INDEX IF NOT EXISTS idx_step_traj ON trajectory_steps(trajectory_id);",
    "CREATE INDEX IF NOT EXISTS idx_cf_traj ON control_frames(trajectory_id);",
    "CREATE INDEX IF NOT EXISTS idx_cf_ts ON control_frames(timestamp);",
    "CREATE INDEX IF NOT EXISTS idx_ec_traj ON embodied_contexts(trajectory_id);",
]

ALL_TABLE_DDL = [
    CREATE_TRAJECTORIES,
    CREATE_TRAJECTORY_STEPS,
    CREATE_CONTROL_FRAMES,
    CREATE_EMBODIED_CONTEXTS,
]


# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------

def _new_id() -> str:
    return uuid4().hex


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dumps(obj) -> str | None:
    return json.dumps(obj, separators=(",", ":")) if obj is not None else None


def import_episode(conn: sqlite3.Connection, episode: dict, *, verbose: bool = True) -> str:
    """Insert one phyzical episode. Returns the trajectory_id."""
    episode_id = episode.get("episode_id") or f"EP_{_new_id()[:8]}"
    trajectory_id = f"phyz_{episode_id}"
    contributor = episode.get("contributor", "anonymous")
    task_id = episode.get("task_id", "unknown_task")
    success = bool(episode.get("success", False))
    frames = episode.get("trajectory", [])
    duration_s = float(episode.get("duration_s") or (frames[-1]["t"] if frames else 0.0))

    start_time = 0.0
    end_time = duration_s
    now = _now_iso()

    metadata = {
        "platform": "phyzical.org",
        "task_id": task_id,
        "robot_profile": episode.get("robot_profile"),
        "sim": episode.get("sim"),
        "control_mode": episode.get("control_mode", "ee_drag_ik"),
        "provenance": episode.get("provenance"),
        "schema": "phyzical-episode-v1",
    }

    conn.execute(
        """INSERT OR REPLACE INTO trajectories (
               id, trajectory_id, agent_id, source, episode_id, status,
               start_time, end_time, duration_ms, total_reward,
               final_status, episode_length, metadata_json,
               is_training_data, is_evaluation, used_in_training,
               created_at, updated_at
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            _new_id(),
            trajectory_id,
            contributor,
            "phyzical",
            episode_id,
            "completed" if success else "terminated",
            start_time,
            end_time,
            int(duration_s * 1000),
            1.0 if success else 0.0,
            "success" if success else "failure",
            len(frames),
            _dumps(metadata),
            1 if success else 0,
            0,
            0,
            now,
            now,
        ),
    )

    # One macro-step: the human teleoperation session.
    step_id = _new_id()
    first = frames[0] if frames else {}
    conn.execute(
        """INSERT INTO trajectory_steps (
               id, trajectory_id, step_number, timestamp,
               observation_json, action_type, action_name, action_params_json,
               action_success, reward, done, environment_state_json,
               reasoning, metadata_json
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            step_id,
            trajectory_id,
            0,
            start_time,
            _dumps(
                {
                    "joint_pos": first.get("joint_pos"),
                    "ee_pose": first.get("ee_pose"),
                    "object_poses": first.get("object_poses"),
                }
            ),
            "teleoperation",
            task_id,
            _dumps({"control": episode.get("control_mode", "ee_drag_ik")}),
            1 if success else 0,
            1.0 if success else 0.0,
            1,
            _dumps({"object_poses": first.get("object_poses")}),
            "human demonstration (browser teleoperation)",
            _dumps({"frames": len(frames)}),
        ),
    )

    # High-frequency control frames.
    last_index = len(frames) - 1
    rows = []
    for i, f in enumerate(frames):
        action = f.get("action") or {}
        rows.append(
            (
                trajectory_id,
                step_id,
                float(f.get("t", 0.0)),
                _dumps(f.get("joint_pos")),
                _dumps(f.get("joint_vel")),
                _dumps(f.get("joint_targets")),
                0.0,
                0.0,
                None,
                None,
                _dumps(
                    {
                        "type": action.get("type"),
                        "cmd": action.get("cmd"),
                        "gripper": f.get("gripper"),
                        "ee_pose": f.get("ee_pose"),
                    }
                ),
                (1.0 if success else 0.0) if i == last_index else 0.0,
            )
        )
    conn.executemany(
        """INSERT INTO control_frames (
               trajectory_id, planner_step_id, timestamp,
               joint_positions_json, joint_velocities_json, joint_targets_json,
               imu_roll, imu_pitch, gyro_json, entity_slots_json,
               action_applied_json, reward
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        rows,
    )

    # Embodied context: world state + task language.
    entities = []
    for name, pose in (first.get("object_poses") or {}).items():
        entities.append({"name": name, **(pose if isinstance(pose, dict) else {"pose": pose})})
    conn.execute(
        """INSERT INTO embodied_contexts (
               id, trajectory_id, step_id, timestamp, entities_json,
               camera_views_json, agent_pose_json, task_description, source
           ) VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            _new_id(),
            trajectory_id,
            step_id,
            start_time,
            _dumps(entities),
            _dumps([]),
            _dumps(first.get("ee_pose")),
            episode.get("task_description", task_id.replace("_", " ")),
            "phyzical_unity_webgl",
        ),
    )

    if verbose:
        print(
            f"[import] {episode_id}: {len(frames)} frames, "
            f"{duration_s:.1f}s, success={success} -> {trajectory_id}"
        )
    return trajectory_id


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Import phyzical episodes into an elizaOS-compatible trajectory_db"
    )
    parser.add_argument("inputs", nargs="+", help="phyzical episode JSON file(s)")
    parser.add_argument("--db", default="trajectories.db", help="output SQLite path")
    parser.add_argument("--summary", action="store_true", help="print table counts at the end")
    parser.add_argument("--quiet", "-q", action="store_true")
    args = parser.parse_args(argv)

    conn = sqlite3.connect(args.db)
    for ddl in ALL_TABLE_DDL:
        conn.execute(ddl)
    for ddl in INDEX_DDL:
        conn.execute(ddl)

    count = 0
    for pattern in args.inputs:
        path = Path(pattern)
        if not path.exists():
            print(f"[import] skip missing file: {pattern}", file=sys.stderr)
            continue
        episode = json.loads(path.read_text(encoding="utf-8"))
        import_episode(conn, episode, verbose=not args.quiet)
        count += 1

    conn.commit()

    if args.summary:
        for table in ("trajectories", "trajectory_steps", "control_frames", "embodied_contexts"):
            n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"{table:20s} {n}")

    conn.close()
    if not args.quiet:
        print(f"Done: {count} episode(s) -> {args.db}")


if __name__ == "__main__":
    main()
