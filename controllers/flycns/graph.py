"""Fixed wiring: photoreceptors -> interneurons -> descending neurons.

This module is the engineering stand-in for the ``malecns_v1_visual_crop``
profile. The *interface* is the one the phyzical runtime commits to:

    photoreceptor activations in  ->  descending-neuron scalars out
    (turn, drive, lift, grip)     +   dopamine-style neuromodulation

The weights here are a deterministic, seeded, structured reduction -- NOT the
raw MaleCNS connectivity matrix (which is ~166K neurons and lives with the
dataset, CC BY, at Janelia). Swapping in weights distilled from the real
visual crop only requires replacing ``FixedGraph.project``. See
docs/flycns.md for what is biology and what is engineering.

Wiring is fixed: there is no training and no gradient anywhere in this file.
The only state that changes at runtime is *neuromodulation* -- transient gain
changes driven by teach events, mirroring how dopamine neurons (PPL101
aversive, PAM reward) gate behaviour in the fly without rewiring it.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

# ``random`` is used only at wiring-build time (seeded); never at runtime.

from .hexeye import HEX_RADIUS, hex_cells, hex_to_uv

GRAPH_ID = "malecns_v1_visual_crop"
READOUT_CELLS = ["DNp20", "DNpe017"]  # turn / drive readout naming
SEED = 8004  # deterministic wiring


def _build_interneurons(n_cells: int, n_inter: int) -> list[list[float]]:
    """Sparse seeded projection standing in for lamina/medulla channels."""
    rng = random.Random(SEED)
    weights = []
    for _ in range(n_inter):
        row = [0.0] * n_cells
        for _ in range(max(3, n_cells // 6)):
            row[rng.randrange(n_cells)] = rng.uniform(-1.0, 1.0)
        weights.append(row)
    return weights


@dataclass
class Neuromodulation:
    """Dopamine-style gain state. Teach events move it; time decays it."""

    drive_gain: float = 1.0
    turn_bias: float = 0.0
    approach_gain: float = 1.0

    def aversive(self, direction: float = 1.0) -> None:
        """PPL101-style punishment: suppress forward drive, bias a turn-away.

        ``direction`` is the escape sign (away from the collision side).
        """
        self.drive_gain = max(0.35, self.drive_gain * 0.55)
        self.turn_bias = max(-1.2, min(1.2, self.turn_bias + direction * 0.8))

    def reward(self) -> None:
        """PAM-style reward: reinforce the current approach."""
        self.approach_gain = min(1.6, self.approach_gain * 1.15)

    def decay(self, dt: float) -> None:
        self.drive_gain += (1.0 - self.drive_gain) * min(1.0, 0.6 * dt)
        self.approach_gain += (1.0 - self.approach_gain) * min(1.0, 0.25 * dt)
        self.turn_bias *= max(0.0, 1.0 - 1.8 * dt)


@dataclass
class FixedGraph:
    """Deterministic readout of descending-neuron activity."""

    n_inter: int = 64
    cells: list[tuple[int, int]] = field(default_factory=hex_cells)
    mod: Neuromodulation = field(default_factory=Neuromodulation)
    _w_inter: list[list[float]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self._w_inter:
            self._w_inter = _build_interneurons(len(self.cells), self.n_inter)

    def project(self, r16: list[float], r8: list[float]) -> dict:
        """Photoreceptor activations -> DN scalars in [-1, 1].

        Structured pooling (the part that is anatomy-shaped):
        * turn  -- horizontally antisymmetric pooling of R1-R6 transients,
                   like the T4/T5 -> DNp20 yaw pathway
        * lift  -- vertically antisymmetric pooling
        * drive -- centre-weighted R8 feature salience (approach target),
                   like Fd/loom channels onto DNpe017
        * grip  -- central saturation (target fills the fovea -> close)
        """
        turn = lift = drive = grip = 0.0
        wsum = 1e-9
        for i, (q, r) in enumerate(self.cells):
            u, v = hex_to_uv(q, r, HEX_RADIUS)
            dx, dy = (u - 0.5) * 2.0, (v - 0.5) * 2.0
            ecc = math.hypot(dx, dy)
            a16, a8 = r16[i], r8[i]
            turn += a16 * dx
            lift += a16 * dy
            drive += max(0.0, a8) * (1.0 - ecc)
            grip += max(0.0, a8) * max(0.0, 0.35 - ecc)
            wsum += abs(a16)

        # Interneuron energy modulates readout sharpness (fixed weights).
        energy = 0.0
        for row in self._w_inter:
            s = sum(w * a for w, a in zip(row, r16) if w)
            energy += abs(math.tanh(s))
        sharp = 0.6 + 0.4 * math.tanh(energy / self.n_inter * 3.0)

        m = self.mod
        return {
            "turn": max(-1.0, min(1.0, (turn / wsum) * 6.0 * sharp + m.turn_bias)),
            "lift": max(-1.0, min(1.0, (lift / wsum) * 6.0 * sharp)),
            "drive": max(0.0, min(1.0, drive * 2.2 * sharp * m.drive_gain * m.approach_gain)),
            "grip": max(0.0, min(1.0, grip * 8.0)),
        }
