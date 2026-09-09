# Field Mapping: phyzical episode → elizaOS `trajectory_db`

This document specifies how a `phyzical-episode-v1` JSON converts into the
unified SQLite trajectory schema used by the elizaOS robotics stack
([`elizaOS/research`](https://github.com/elizaOS/research):
`robot/eliza_robot/trajectory_db/schema.py`). The conversion is implemented in
[`converters/eliza_robot/import_phyzical.py`](../converters/eliza_robot/import_phyzical.py).

## Design

elizaOS's `trajectory_db` separates **planner-level steps** (LLM/agent
decisions) from **high-frequency control frames** (50–100Hz robot data). A
human browser demonstration has no LLM calls — it is one continuous teleop
session — so an episode maps to:

- **1 row** in `trajectories` (the episode)
- **1 macro-step** in `trajectory_steps` (`action_type='teleoperation'`)
- **N rows** in `control_frames` (one per 30–60Hz frame, linked via `planner_step_id`)
- **1 row** in `embodied_contexts` (object poses + language instruction)

`llm_calls` and `provider_accesses` remain empty — correctly reflecting that
the demonstrator was human. When the DAgger loop ships (policy rollout +
human takeover), policy segments will populate these tables and takeover
segments stay human-attributed.

## `trajectories`

| trajectory_db column | phyzical source | note |
|---|---|---|
| `trajectory_id` | `"phyz_" + episode_id` | namespaced to avoid collisions |
| `agent_id` | `contributor` | wallet address of the human demonstrator |
| `source` | `"phyzical"` | filterable, cf. `idx_traj_source` |
| `episode_id` | `episode_id` | |
| `status` | `success ? "completed" : "terminated"` | |
| `start_time` / `end_time` | `0.0` / `duration_s` | episode-relative seconds |
| `duration_ms` | `duration_s * 1000` | |
| `total_reward` | `success ? 1.0 : 0.0` | sparse task reward |
| `final_status` | `"success"` / `"failure"` | |
| `episode_length` | `len(trajectory)` | frame count |
| `metadata_json` | task_id, robot_profile, sim, control_mode, provenance | includes onchain Data ID + content hash |
| `is_training_data` | `success` | failed demos kept but not flagged |

## `trajectory_steps` (1 macro-step)

| column | value |
|---|---|
| `step_number` | `0` |
| `action_type` | `"teleoperation"` |
| `action_name` | `task_id` |
| `action_params_json` | `{"control": control_mode}` |
| `observation_json` | first frame (joint_pos, ee_pose, object_poses) |
| `environment_state_json` | initial object poses |
| `reward` / `done` | task reward / `1` |
| `reasoning` | `"human demonstration (browser teleoperation)"` |

## `control_frames` (per frame)

| trajectory_db column | phyzical frame field |
|---|---|
| `timestamp` | `t` |
| `joint_positions_json` | `joint_pos` |
| `joint_velocities_json` | `joint_vel` (optional) |
| `joint_targets_json` | `joint_targets` (optional) |
| `action_applied_json` | `{type, cmd, gripper, ee_pose}` |
| `reward` | `0.0` except final frame = task reward |
| `planner_step_id` | the macro-step id |
| `imu_roll` / `imu_pitch` / `gyro_json` | `0.0` / `0.0` / `null` — tabletop arm, no IMU |

## `embodied_contexts` (1 per episode)

| column | value |
|---|---|
| `entities_json` | initial `object_poses` as named entity list |
| `agent_pose_json` | initial `ee_pose` |
| `task_description` | natural-language instruction (VLA language conditioning) |
| `source` | `"phyzical_unity_webgl"` |

## Provenance

The onchain record (Data ID, `content_hash`, anchor reference) travels inside
`trajectories.metadata_json.provenance`. Consumers can recompute the sha256
of the canonical episode payload and verify it against the chain before
training on the data.
