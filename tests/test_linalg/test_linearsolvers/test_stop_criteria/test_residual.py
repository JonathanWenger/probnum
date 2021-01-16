"""Tests for the residual stopping criterion."""
import numpy as np
import pytest

from probnum.linalg.linearsolvers.beliefs import LinearSystemBelief
from probnum.linalg.linearsolvers.stop_criteria import Residual
from probnum.problems import LinearSystem


@pytest.mark.parametrize(
    "norm_ord", [np.inf, -np.inf, 0.5, 1, 2, 10], ids=lambda i: f"ord{i}"
)
def test_different_norms(
    linsys_spd: LinearSystem, prior: LinearSystemBelief, norm_ord: float
):
    """Test if stopping criterion can be computed for different norms."""
    Residual(norm_ord=norm_ord)(
        problem=linsys_spd,
        belief=prior,
    )
