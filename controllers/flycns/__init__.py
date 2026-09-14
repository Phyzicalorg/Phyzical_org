"""flycns -- the Fly connectome controller for phyzical episodes.

A MaleCNS visual crop wired to the scene camera: photoreceptors in,
descending-neuron readout out, dopamine-style teach events on collision or
success. Fixed biological wiring, experimental readout -- tagged
``controller=flycns`` in every episode it produces.

>>> from controllers.flycns import FlyCNSController
"""

from .controller import CONTROLLER_ID, FlyCNSController
from .graph import GRAPH_ID, READOUT_CELLS
from .hexeye import SOURCE_PHOTORECEPTORS, HexEye

__all__ = [
    "FlyCNSController",
    "CONTROLLER_ID",
    "GRAPH_ID",
    "READOUT_CELLS",
    "SOURCE_PHOTORECEPTORS",
    "HexEye",
]
