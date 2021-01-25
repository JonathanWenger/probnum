"""Belief update for the weak mean correspondence belief given linear observations."""
import dataclasses
from typing import Optional, Tuple, Type

import numpy as np

import probnum
import probnum.linops as linops
import probnum.random_variables as rvs
from probnum.linalg.solvers._state import LinearSolverState
from probnum.linalg.solvers.belief_updates._symmetric_normal_linear_obs import (
    SymmetricNormalLinearObsBeliefUpdate,
    _InverseMatrixSymmetricNormalLinearObsBeliefUpdate,
    _SymmetricNormalLinearObsCache,
    _SystemMatrixSymmetricNormalLinearObsBeliefUpdate,
)
from probnum.linalg.solvers.beliefs import (
    LinearSystemBelief,
    WeakMeanCorrespondenceBelief,
)
from probnum.linalg.solvers.data import (
    LinearSolverAction,
    LinearSolverData,
    LinearSolverObservation,
)
from probnum.problems import LinearSystem

# Public classes and functions. Order is reflected in documentation.
__all__ = ["WeakMeanCorrLinearObsBeliefUpdate"]


@dataclasses.dataclass
class _WeakMeanCorrLinearObsCache(_SymmetricNormalLinearObsCache):
    """Cached quantities assuming symmetric matrix-variate normal priors and linear
    observations."""

    # TODO use assumptions WS = Y and WY=H_0Y (Theorem 3, eqn. 1+2, Wenger2020)
    # @cached_property
    # def covfactorA_action(self) -> np.ndarray:
    #     return self.qoi_belief.cov.A @ self.action
    #
    # @cached_property
    # def action_covfactorA_action(self) -> float:
    #     return self.action.T @ self.covfactor_action


class _SystemMatrixWeakMeanCorrLinearObsBeliefUpdateState(
    _SystemMatrixSymmetricNormalLinearObsBeliefUpdate
):
    """Weak mean correspondence belief update for the system matrix."""

    def __call__(
        self,
        hyperparams: "probnum.linalg.solvers.hyperparams.UncertaintyUnexploredSpace",
        solver_state: "probnum.linalg.solvers.LinearSolverState",
    ) -> rvs.Normal:

        mean = (
            linops.aslinop(solver_state.prior.A.mean)
            + solver_state.cache.meanA_update_batch
        )
        cov = solver_state.prior.A.cov.A - solver_state.cache.covfactorA_update_batch[0]
        return rvs.Normal(mean=mean, cov=cov)


class _InverseMatrixWeakMeanCorrLinearObsBeliefUpdateState(
    _InverseMatrixSymmetricNormalLinearObsBeliefUpdate
):
    """Weak mean correspondence belief update for the inverse."""

    def __call__(
        self,
        hyperparams: "probnum.linalg.solvers.hyperparams.UncertaintyUnexploredSpace",
        solver_state: "probnum.linalg.solvers.LinearSolverState",
    ) -> rvs.Normal:
        """Updated belief for the inverse."""

        covfactor_op = (
            solver_state.prior.Ainv.cov.A
            - solver_state.cache.covfactorH_update_batch[0]
        )

        # Recursive covariance trace update (Section S4.3 of Wenger and Hennig, 2020)
        covfactor_op.trace = (
            solver_state.belief.Ainv.cov.A.trace()
            - solver_state.cache.sqnorm_covfactorH_observation
            / solver_state.cache.observation_covfactorH_observation
        )
        mean = (
            linops.aslinop(solver_state.prior.Ainv.mean)
            + solver_state.cache.meanH_update_batch
        )
        cov = linops.SymmetricKronecker(covfactor_op)
        return rvs.Normal(mean=mean, cov=cov)


class WeakMeanCorrLinearObsBeliefUpdate(SymmetricNormalLinearObsBeliefUpdate):
    r"""Weak mean correspondence belief update assuming linear observations."""

    def __init__(self, problem: LinearSystem, prior: LinearSystemBelief):
        super().__init__(
            problem=problem,
            prior=prior,
            cache_type=_WeakMeanCorrLinearObsCache,
            A_belief_update_type=_SystemMatrixWeakMeanCorrLinearObsBeliefUpdateState,
            Ainv_belief_update_type=_InverseMatrixWeakMeanCorrLinearObsBeliefUpdateState,
        )

    def __call__(
        self,
        belief: LinearSystemBelief,
        action: LinearSolverAction,
        observation: LinearSolverObservation,
        hyperparams: Optional[
            "probnum.linalg.solvers.hyperparams.LinearSolverHyperparams"
        ] = None,
        solver_state: Optional["probnum.linalg.solvers.LinearSolverState"] = None,
    ) -> Tuple[
        LinearSystemBelief, Optional["probnum.linalg.solvers.LinearSolverState"]
    ]:
        if solver_state is None:

            solver_state = LinearSolverState(
                problem=self._problem,
                prior=self._prior,
                belief=belief,
                data=LinearSolverData(
                    actions=[action],
                    observations=[observation],
                ),
                cache=self._cache_type.from_new_data(
                    action=action,
                    observation=observation,
                    prev_cache=self._cache_type(
                        problem=self._problem,
                        belief=self._prior,
                    ),
                ),
            )

        # Update empirical prior with new observations and uncertainty scale
        # TODO what about non-conjugate actions??
        self.prior = WeakMeanCorrespondenceBelief(
            A0=solver_state.prior.A0,
            Ainv0=solver_state.prior.Ainv0,
            b=solver_state.problem.b,
            uncertainty_scales=hyperparams,
            actions=solver_state.data.actions,
            observations=solver_state.data.observations,
            action_obs_innerprods=np.array(
                solver_state.cache.action_observation_innerprod_list
            ),
        )
        solver_state.prior = self.prior

        # Update belief (using optimized hyperparameters)
        updated_belief = LinearSystemBelief(
            x=self._x_belief_update(
                hyperparams=hyperparams,
                solver_state=solver_state,
            ),
            Ainv=self._Ainv_belief_update(
                hyperparams=hyperparams,
                solver_state=solver_state,
            ),
            A=self._A_belief_update(
                hyperparams=hyperparams,
                solver_state=solver_state,
            ),
            b=self._b_belief_update(
                hyperparams=hyperparams,
                solver_state=solver_state,
            ),
        )

        # Create new solver state from updated belief
        updated_solver_state = LinearSolverState.from_updated_belief(
            updated_belief=updated_belief, prev_state=solver_state
        )

        return updated_belief, updated_solver_state
