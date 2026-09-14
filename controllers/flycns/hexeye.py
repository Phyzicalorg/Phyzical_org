"""Ommatidia sampling: a hexagonal compound-eye front end.

Maps a 64x64 luminance frame onto a hex lattice of ommatidia (axial radius 4
-> 61 cells, matching the phyzical.org HUD visualisation). Each ommatidium
pools a Gaussian-weighted patch of the frame into two photoreceptor channels:

* ``r16`` -- the pooled R1-R6 achromatic channel (motion pathway input)
* ``r8``  -- a centre-surround channel standing in for R7/R8 (feature input)

Photoreceptors adapt: a slow state tracks the mean stimulus and is subtracted
from the instantaneous response, so a static scene fades (visual habituation)
while transients pass through -- the property the QC stage measures.

The full MaleCNS visual crop contains 3,335 R1-R6 and 811 R7/R8 cells; this
runtime samples 61 pooled ommatidia and keeps the source counts as episode
metadata. See docs/flycns.md for the mapping rationale.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

HEX_RADIUS = 4  # axial radius -> 61 cells
FRAME_W = 64
FRAME_H = 64

# Source-graph metadata (MaleCNS v1.0 visual crop), carried into episodes.
SOURCE_PHOTORECEPTORS = {"r1r6": 3335, "r8": 811}


def hex_cells(radius: int = HEX_RADIUS) -> list[tuple[int, int]]:
    """Axial coordinates of a hex disk of the given radius (61 for r=4)."""
    cells = []
    for q in range(-radius, radius + 1):
        for r in range(max(-radius, -q - radius), min(radius, -q + radius) + 1):
            cells.append((q, r))
    return cells


def hex_to_uv(q: int, r: int, radius: int = HEX_RADIUS) -> tuple[float, float]:
    """Axial hex -> normalised image coordinates in [0, 1]^2."""
    x = 1.5 * q
    y = math.sqrt(3.0) * (r + q / 2.0)
    span = 1.5 * (2 * radius + 1)
    return 0.5 + x / span, 0.5 + y / span


@dataclass
class HexEye:
    """61-ommatidia compound eye with adapting photoreceptors."""

    radius: int = HEX_RADIUS
    adapt_rate: float = 0.06     # per-step adaptation toward current stimulus
    adapt_strength: float = 0.75  # how much of the adapted state is subtracted
    cells: list[tuple[int, int]] = field(default_factory=hex_cells)
    _adapt: list[float] = field(default_factory=lambda: [0.0] * 61)

    def sample(self, frame: list[list[float]]) -> dict:
        """Sample one 64x64 luminance frame (values in [0, 1]).

        Returns ``r16`` and ``r8`` activation lists (len 61, values ~[-1, 1]
        after adaptation), plus ``habituation`` -- how much of the scene the
        eye has adapted away (0 = fresh stimulus, 1 = fully habituated).
        """
        h = len(frame)
        w = len(frame[0]) if h else 0
        r16, r8 = [], []
        pooled_total, adapted_total = 0.0, 0.0

        for i, (q, r) in enumerate(self.cells):
            u, v = hex_to_uv(q, r, self.radius)
            cx, cy = u * (w - 1), v * (h - 1)

            # Gaussian pool (R1-R6) over a small patch.
            acc = wsum = 0.0
            # Surround ring for the R8 centre-surround channel.
            sur = swsum = 0.0
            rad = max(2, int(w / (3 * self.radius)))
            for dy in range(-rad, rad + 1):
                py = int(cy) + dy
                if py < 0 or py >= h:
                    continue
                for dx in range(-rad, rad + 1):
                    px = int(cx) + dx
                    if px < 0 or px >= w:
                        continue
                    d2 = dx * dx + dy * dy
                    val = frame[py][px]
                    wg = math.exp(-d2 / (0.5 * rad * rad))
                    acc += val * wg
                    wsum += wg
                    if d2 > rad * rad * 0.45:
                        sur += val
                        swsum += 1.0

            centre = acc / wsum if wsum else 0.0
            surround = sur / swsum if swsum else 0.0

            # Photoreceptor adaptation (visual habituation).
            self._adapt[i] += (centre - self._adapt[i]) * self.adapt_rate
            adapted = centre - self.adapt_strength * self._adapt[i]

            r16.append(adapted)
            r8.append(centre - surround)
            pooled_total += abs(centre)
            adapted_total += abs(adapted)

        habituation = 0.0
        if pooled_total > 1e-6:
            habituation = max(0.0, 1.0 - adapted_total / pooled_total)

        return {"r16": r16, "r8": r8, "habituation": habituation}

    def reset(self) -> None:
        self._adapt = [0.0] * len(self.cells)
