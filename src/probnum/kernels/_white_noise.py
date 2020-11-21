"""White noise kernel."""

from typing import Optional, TypeVar

import numpy as np

import probnum.utils as _utils
from probnum.type import ScalarArgType

from ._kernel import Kernel

_InputType = TypeVar("InputType")


class WhiteNoise(Kernel[_InputType]):
    """White noise kernel.

    Kernel representing independent and identically distributed white noise :math:`k(
    x_0, x_1) = \\sigma^2 \\delta(x_0, x_1)`.

    Parameters
    ----------
    sigma
        Noise level.
    """

    def __init__(self, sigma: ScalarArgType):
        self.sigma = _utils.as_numpy_scalar(sigma)
        super().__init__(kernel=self._kernel, output_dim=1)

    def _kernel(self, x0: _InputType, x1: Optional[_InputType] = None) -> np.ndarray:
        x0 = _utils.as_colvec(x0)
        if x1 is None:
            return self.sigma ** 2 * np.eye(x0.shape[0])
        else:
            x1 = _utils.as_colvec(x1)

        return self.sigma ** 2 * np.equal(x0, x1[:, np.newaxis, :]).all(
            axis=2
        ).T.astype(float)
