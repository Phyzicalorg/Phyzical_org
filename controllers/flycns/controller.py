"""FlyCNSController: the third actions source for phyzical episodes.

One camera frame in, one relative end-effector command out::

    ctrl = FlyCNSController()
    out = ctrl.step(frame_64x64, dt=1/30, collision=False, success=False)
    # out["action"]      -> {"type": "ee_delta", "cmd": [dx, dy, dz, grip]}
    # out["dn_readout"]  -> {"turn": ..., "drive": ..., "lift": ..., "grip": ...}
    # out["teach_event"] -> {"cell": "PPL101"|"PAM", "kind": ...} | None

Behavioural shape (all fixed wiring, no policy):

* **saccadic pursuit** -- heading updates in bursts (~4-5Hz), like fly body
  saccades, instead of continuous smooth servoing
* **reflex guardrail** -- an aversive teach event immediately gates forward
  drive down and biases a turn-away (dopamine-style neuromodulation, not a
  learned update)
* **habituation** -- a static scene fades from the photoreceptors; QC reads
  the habituation metric to reject stuck episodes

Episodes produced with this controller are tagged ``controller=flycns_v1``
and carry the ``fly`` metadata block defined in schema/episode.schema.json.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .graph import GRAPH_ID, READOUT_CELLS, FixedGraph
from .hexeye import SOURCE_PHOTORECEPTORS, HexEye

CONTROLLER_ID = "flycns_v1"


@dataclass
class FlyCNSController:
    """Maps MaleCNS-crop-style readout onto relative EE motion."""

    saccade_interval: float = 0.22   # seconds between heading updates
    speed: float = 0.9               # EE units/s at full drive
    eye: HexEye = field(default_factory=HexEye)
    graph: FixedGraph = field(default_factory=FixedGraph)

    _t: float = 0.0
    _last_saccade: float = -1.0
    _held_turn: float = 0.0
    _held_lift: float = 0.0
    _last_event_t: dict = field(default_factory=dict)
    teach_events: list = field(default_factory=list)

    def step(
        self,
        frame: list[list[float]],
        dt: float = 1.0 / 30.0,
        *,
        collision: bool = False,
        success: bool = False,
    ) -> dict:
        """Advance one control tick."""
        self._t += dt
        self.graph.mod.decay(dt)

        # Teach events first: dopamine gates the very next readout.
        # A 0.5s refractory window per cell keeps sustained contact from
        # spamming events (one punishment per collision, not per tick).
        teach_event = None
        if collision and self._t - self._last_event_t.get("PPL101", -1.0) >= 0.5:
            escape = -1.0 if self._held_turn > 0 else 1.0  # turn away from travel
            self.graph.mod.aversive(direction=escape)
            teach_event = {"t": round(self._t, 3), "cell": "PPL101", "kind": "aversive", "ms": 200}
        elif success and self._t - self._last_event_t.get("PAM", -1.0) >= 0.5:
            self.graph.mod.reward()
            teach_event = {"t": round(self._t, 3), "cell": "PAM", "kind": "reward", "ms": 150}
        if teach_event:
            self._last_event_t[teach_event["cell"]] = self._t
            self.teach_events.append(teach_event)

        # Photoreceptors -> DN readout.
        stim = self.eye.sample(frame)
        dn = self.graph.project(stim["r16"], stim["r8"])

        # Saccadic heading hold: turn/lift only refresh in bursts.
        if self._t - self._last_saccade >= self.saccade_interval:
            self._held_turn = dn["turn"]
            self._held_lift = dn["lift"]
            self._last_saccade = self._t

        v = self.speed * dt
        cmd = [
            self._held_turn * v,          # dx  (yaw-mapped)
            self._held_lift * v,          # dy  (lift-mapped)
            dn["drive"] * v,              # dz  (approach)
            dn["grip"],                   # gripper aperture target
        ]

        return {
            "t": round(self._t, 4),
            "action": {"type": "ee_delta", "cmd": [round(c, 5) for c in cmd]},
            "dn_readout": {k: round(val, 4) for k, val in dn.items()},
            "fly_stim": {
                "mean": round(sum(stim["r16"]) / len(stim["r16"]), 4),
                "habituation": round(stim["habituation"], 4),
            },
            "teach_event": teach_event,
        }

    def episode_metadata(self) -> dict:
        """The `fly` block for a phyzical episode (schema/episode.schema.json)."""
        return {
            "graph": GRAPH_ID,
            "photoreceptors": dict(SOURCE_PHOTORECEPTORS),
            "ommatidia_sampled": len(self.eye.cells),
            "readout": list(READOUT_CELLS),
            "teach_events": list(self.teach_events),
        }

    def reset(self) -> None:
        self.eye.reset()
        self.graph.mod.__init__()
        self._t = 0.0
        self._last_saccade = -1.0
        self._held_turn = self._held_lift = 0.0
        self._last_event_t = {}
        self.teach_events = []
