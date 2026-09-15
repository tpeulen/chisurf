from __future__ import annotations
from chisurf import typing

import numpy as np
from typing import TYPE_CHECKING

import chisurf.core.support.decorators
import chisurf.core.parameter

from chisurf.core.curve import Curve
from chisurf.core.models import model
from chisurf.core.models.parameter_transform import ParameterTransformModel

if TYPE_CHECKING:
    from chisurf.core.fitting.fit import Fit, FitGroup

