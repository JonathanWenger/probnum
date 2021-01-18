from typing import Optional, Tuple

import numpy as np

import probnum
from probnum.linalg.linearsolvers.observation_ops._observation_operator import (
    ObservationOperator,
)
from probnum.problems import LinearSystem

# Public classes and functions. Order is reflected in documentation.
__all__ = ["MatVecObservation"]


class MatVecObservation(ObservationOperator):
    r"""Matrix-vector product observations.

    Given an action :math:`s` collect an observation :math:`y` of the linear system by
    multiplying with the system matrix :math:`y = As`.
    """

    def __init__(self):
        super().__init__(observation_op=self.__call__)

    def __call__(
        self,
        problem: LinearSystem,
        action: np.ndarray,
        solver_state: Optional["probnum.linalg.linearsolvers.LinearSolverState"] = None,
    ) -> Tuple[np.ndarray, Optional["probnum.linalg.linearsolvers.LinearSolverState"]]:

        # Observation
        observation = problem.A @ action

        # Update solver state
        if solver_state is not None:
            solver_state.observations.append(observation)

        return observation, solver_state