# phyzical → elizaOS trajectory_db converter

Converts [`phyzical-episode-v1`](../../schema/episode.schema.json) JSON files
into a SQLite database using the same DDL as the elizaOS robotics stack
(`eliza_robot/trajectory_db`). Standalone — Python 3.10+, stdlib only.

```bash
python3 import_phyzical.py ../../examples/episode_block_sorting.json --db trajectories.db --summary
```

Expected output:

```
[import] EP_a41b7c2e: 90 frames, 3.0s, success=True -> phyz_EP_a41b7c2e
trajectories         1
trajectory_steps     1
control_frames       90
embodied_contexts    1
Done: 1 episode(s) -> trajectories.db
```

The resulting database can be queried by any elizaOS `trajectory_db` tooling
(`source = 'phyzical'`). Field-level mapping rationale lives in
[`schema/MAPPING.md`](../../schema/MAPPING.md).

DDL reproduced from
[elizaOS/research](https://github.com/elizaOS/research)
`robot/eliza_robot/trajectory_db/schema.py` (MIT, © elizaOS contributors).
