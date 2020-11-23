"""White noise kernel."""

from typing import Optional

import numpy as np

import probnum.utils as _utils
from probnum.type import IntArgType, ScalarArgType

from ._kernel import Kernel

_InputType = np.ndarray


class WhiteNoise(Kernel[_InputType]):
    """White noise kernel.

    Kernel representing independent and identically distributed white noise :math:`k(
    x_0, x_1) = \\sigma^2 \\delta(x_0, x_1)`.

    Parameters
    ----------
    input_dim :
        Input dimension of the kernel.
    sigma :
        Noise level.
    """

    def __init__(self, input_dim: IntArgType, sigma: ScalarArgType = 1.0):
        self.sigma = _utils.as_numpy_scalar(sigma)
        super().__init__(input_dim=input_dim, output_dim=1)

    def __call__(self, x0: _InputType, x1: Optional[_InputType] = None) -> np.ndarray:
        x0 = np.atleast_2d(x0)
        if x1 is None:
            return self.sigma ** 2 * np.eye(x0.shape[0])
        else:
            x1 = np.atleast_2d(x1)

        kernmat = self.sigma ** 2 * np.equal(x0, x1[:, np.newaxis, :]).all(
            axis=2
        ).T.astype(float)

        return self._normalize_kernelmatrix_shape(kerneval=kernmat, x0=x0, x1=x1)
