"""Probabilistic linear solver state test cases."""

import numpy as np

from probnum import linalg, linops, randvars
from probnum.problems.zoo.linalg import random_linear_system, random_spd_matrix


def case_linear_solver_state(
    rng: np.random.Generator,
):
    """State of a linear solver."""
    # Problem
    n = 10
    linsys = random_linear_system(rng=rng, matrix=random_spd_matrix, dim=n)

    # Prior
    prior = linalg.solvers.beliefs.LinearSystemBelief(
        A=randvars.Constant(linsys.A),
        Ainv=None,
        x=randvars.Normal(
            mean=np.zeros(linsys.A.shape[1]), cov=linops.Identity(shape=linsys.A.shape)
        ),
        b=randvars.Constant(linsys.b),
    )

    # State
    solver_state = linalg.solvers.ProbabilisticLinearSolverState(
        problem=linsys, prior=prior, rng=rng
    )

    # Action
    solver_state.action = rng.standard_normal(size=n)

    return solver_state
