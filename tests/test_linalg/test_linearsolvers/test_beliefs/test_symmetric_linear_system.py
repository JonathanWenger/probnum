"""Tests for the symmetric normal linear system belief."""
import numpy as np
import pytest

import probnum.linops as linops
from probnum.linalg.linearsolvers.beliefs import SymmetricLinearSystemBelief
from probnum.problems import LinearSystem

pytestmark = pytest.mark.filterwarnings("ignore::scipy.sparse.SparseEfficiencyWarning")


def test_induced_solution_has_correct_distribution(
    linsys_spd: LinearSystem, symm_belief: SymmetricLinearSystemBelief
):
    """Test whether the induced distribution over the solution from a belief over the
    inverse is correct."""

    np.testing.assert_allclose(
        symm_belief.x.mean,
        symm_belief.Ainv.mean @ linsys_spd.b,
        err_msg="Induced belief over the solution has an inconsistent mean.",
    )
    W = symm_belief.Ainv.cov.A
    Wb = W @ linsys_spd.b
    bWb = (Wb.T @ linsys_spd.b).item()
    Sigma = 0.5 * (bWb * W + linops.MatrixMult(Wb @ Wb.T))
    np.testing.assert_allclose(
        symm_belief.x.cov.todense(),
        Sigma.todense(),
        err_msg="Induced belief over the solution has an inconsistent covariance.",
    )
