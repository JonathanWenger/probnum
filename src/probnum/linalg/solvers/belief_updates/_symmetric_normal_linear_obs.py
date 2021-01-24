"""Belief update given symmetric matrix-variate normal beliefs and linear
observations."""

try:
    # functools.cached_property is only available in Python >=3.8
    from functools import cached_property
except ImportError:
    from cached_property import cached_property

import dataclasses
from typing import List, Optional, Tuple, Union

import numpy as np

import probnum
import probnum.linops as linops
import probnum.random_variables as rvs
from probnum.linalg.solvers._state import LinearSolverCache
from probnum.linalg.solvers.belief_updates import (
    LinearSolverBeliefUpdate,
    LinearSolverQoIBeliefUpdate,
)
from probnum.linalg.solvers.beliefs import LinearSystemBelief
from probnum.linalg.solvers.hyperparams import (
    LinearSolverHyperparams,
    LinearSystemNoise,
)
from probnum.problems import LinearSystem

# pylint: disable="invalid-name"

# Public classes and functions. Order is reflected in documentation.
__all__ = ["SymmetricNormalLinearObsBeliefUpdate"]


@dataclasses.dataclass
class _SymmetricNormalLinearObsCache(LinearSolverCache):
    """Cached quantities assuming symmetric matrix-variate normal priors and linear
    observations."""

    @cached_property
    def action_observation(self) -> float:
        r"""Inner product :math:`s_i^\top y_i` between the current action and
        observation."""
        return (self.action.A.T @ self.observation.A).item()

    @cached_property
    def action_observation_innerprods(self) -> List[float]:
        """Inner products :math:`s_i^\top y_i` between action and observation pairs."""
        if self.prev_cache is None:
            return [self.action_observation]
        else:
            return self.prev_cache.action_observation_innerprods + [
                self.action_observation
            ]

    @cached_property
    def log_rayleigh_quotients(self) -> List[float]:
        r"""Log-Rayleigh quotients :math:`\ln R(A, s_i) = \ln(s_i^\top A s_i)-\ln(
        s_i^\top s_i)`."""
        log_rayleigh_quotient = (
            np.log(self.action_observation)
            - np.log((self.action.T @ self.action)).item()
        )
        if self.prev_cache is None:
            return [log_rayleigh_quotient]
        return self.prev_cache.log_rayleigh_quotients + [log_rayleigh_quotient]

    @cached_property
    def residual(self) -> np.ndarray:
        r"""Residual :math:`r = A x_i- b` of the solution estimate
        :math:`x_i=\mathbb{E}[\mathsf{x}]` at iteration :math:`i`."""
        if self.hyperparams is not None or self.prev_cache is None:
            return self.problem.A @ self.belief.x.mean - self.problem.b
        else:
            return self.prev_cache.residual + self.step_size * self.observation

    @cached_property
    def step_size(self) -> np.ndarray:
        r"""Step size :math:`\alpha_i` of the solver viewed as a quadratic optimizer
        taking steps :math:`x_{i+1} = x_i + \alpha_i s_i`."""
        if self.hyperparams is None and self.prev_cache is not None:
            return (
                -self.action.T @ self.prev_cache.residual / self.action_observation
            ).item()
        else:
            raise NotImplementedError

    @cached_property
    def deltaA(self) -> np.ndarray:
        r"""Residual :math:`\Delta^A_i = y_i - A_{i-1}s_i` between observation and
        prediction."""
        return self.observation - self.belief.A.mean @ self.action

    @cached_property
    def deltaH(self) -> np.ndarray:
        r"""Residual :math:`\Delta^H_i = s_i - H_{i-1}y_i` between inverse
        observation and prediction."""
        return self.action - self.belief.Ainv.mean @ self.observation

    @cached_property
    def deltaA_action(self) -> float:
        r"""Inner product :math:`(\Delta^A)^\top s` between matrix residual and
        action."""
        return self.deltaA.T @ self.action

    @cached_property
    def deltaH_observation(self) -> float:
        r"""Inner product :math:`(\Delta^H)^\top y` between inverse residual and
        observation."""
        return self.deltaH.T @ self.observation

    @cached_property
    def covfactorA_action(self) -> np.ndarray:
        r"""Uncertainty about the matrix along the current action.

        Computes the matrix-vector product :math:`W^A_{i-1}s_i` between the covariance
        factor of the matrix model and the current action.
        """
        return self.belief.A.cov.A @ self.action

    @cached_property
    def covfactorH_observation(self) -> np.ndarray:
        r"""Uncertainty about the inverse along the current observation.

        Computes the matrix-vector product :math:`W^H_{i-1}y_i` between the covariance
        factor of the inverse model and the current observation.
        """
        return self.belief.Ainv.cov.A @ self.observation

    @cached_property
    def sqnorm_covfactorA_action(self) -> float:
        r"""Squared norm :math:`\lVert W^A_{i-1}s_i\rVert^2` of the matrix covariance
        factor applied to the current action."""
        return (self.covfactorA_action.T @ self.covfactorA_action).item()

    @cached_property
    def sqnorm_covfactorH_action(self) -> float:
        r"""Squared norm :math:`\lVert W^H_{i-1}y_i\rVert^2` of the inverse covariance
        factor applied to the current observation."""
        return (self.covfactorH_observation.T @ self.covfactorH_observation).item()

    @cached_property
    def action_covfactorA_action(self) -> float:
        r"""Inner product :math:`s_i^\top W^A_{i-1} s_i` of the current action
        with respect to the covariance factor :math:`W_{i-1}` of the matrix model."""
        return self.action.T @ self.covfactorA_action

    @cached_property
    def observation_covfactorH_observation(self) -> float:
        r"""Inner product :math:`y_i^\top W^H_{i-1} y_i` of the current observation
        with respect to the covariance factor :math:`W^H_{i-1}` of the inverse model."""
        return self.observation.T @ self.covfactorH_observation

    @cached_property
    def delta_invcovfactorA_delta(self) -> float:
        r"""Inner product :math:`\Delta_i (W^A_{i-1})^{-1} \Delta_i` of the residual
        with respect to the inverse of the covariance factor."""
        return self.deltaA.T @ np.linalg.solve(self.belief.A.cov.A, self.deltaA)

    @cached_property
    def sum_delta_invgram_delta(self) -> float:
        r"""Sum of inner products :math:`\Delta^A_i G^A_{i-1}^{-1} \Delta^A_i` of the
        matrix residual and the inverse Gram matrix."""
        if self.prev_cache is None:
            prev_sum_delta_invgram_delta = 0.0
        else:
            prev_sum_delta_invgram_delta = self.prev_cache.sum_delta_invgram_delta
        return prev_sum_delta_invgram_delta + (
            2 * self.delta_invcovfactorA_delta / self.action_covfactorA_action
            - (self.deltaA_action / self.action_covfactorA_action) ** 2
        )

    @cached_property
    def meanA_update_op(self) -> linops.LinearOperator:
        """Rank 2 update term for the mean of the matrix model."""
        u = self.covfactorA_action / self.action_covfactorA_action
        v = self.deltaA - 0.5 * self.deltaA_action * u

        return linops.LinearOperator(
            shape=(self.action.shape[0], self.action.shape[0]),
            matvec=lambda x: u * (v.T @ x) + v * (u.T @ x),
            matmat=lambda x: u @ (v.T @ x) + v @ (u.T @ x),
        )

    @cached_property
    def meanH_update_op(self) -> linops.LinearOperator:
        """Rank 2 update term for the mean of the inverse model."""
        u = self.covfactorH_observation / self.observation_covfactorH_observation
        v = self.deltaH - 0.5 * self.deltaH_observation * u

        return linops.LinearOperator(
            shape=(self.action.shape[0], self.action.shape[0]),
            matvec=lambda x: u * (v.T @ x) + v * (u.T @ x),
            matmat=lambda x: u @ (v.T @ x) + v @ (u.T @ x),
        )

    @cached_property
    def covfactorA_update_ops(self) -> Tuple[linops.LinearOperator, ...]:
        """Rank 1 downdate term(s) for the covariance factors of the matrix model."""
        u = self.covfactorA_action / self.action_covfactorA_action

        covfactor_update_op = linops.LinearOperator(
            shape=(self.action.shape[0], self.action.shape[0]),
            matvec=lambda x: self.covfactorA_action * (u.T @ x),
            matmat=lambda x: self.covfactorA_action @ (u.T @ x),
        )
        return covfactor_update_op, covfactor_update_op

    @cached_property
    def covfactorH_update_ops(self) -> Tuple[linops.LinearOperator, ...]:
        """Rank 1 downdate term(s) for the covariance factors of the inverse model."""
        u = self.covfactorH_observation / self.observation_covfactorH_observation

        covfactor_update_op = linops.LinearOperator(
            shape=(self.action.shape[0], self.action.shape[0]),
            matvec=lambda x: self.covfactorH_observation * (u.T @ x),
            matmat=lambda x: self.covfactorH_observation @ (u.T @ x),
        )
        return covfactor_update_op, covfactor_update_op

    @cached_property
    def meanA_update_batch(self) -> linops.LinearOperator:
        """Matrix model mean update term for all actions and observations."""
        if self.prev_cache is None:
            return self.meanA_update_op
        return self.prev_cache.meanA_update_batch + self.meanA_update_op

    @cached_property
    def meanH_update_batch(self) -> linops.LinearOperator:
        """Inverse model mean update term for all actions and observations."""
        if self.prev_cache is None:
            return self.meanH_update_op
        return self.prev_cache.meanH_update_batch + self.meanH_update_op

    @cached_property
    def covfactorA_update_batch(self) -> Tuple[linops.LinearOperator, ...]:
        """Matrix model covariance factor downdate term for all actions and
        observations."""
        if self.prev_cache is None:
            return self.covfactorA_update_ops
        return tuple(
            map(
                lambda x, y: x + y,
                self.prev_cache.covfactorA_update_batch,
                self.covfactorA_update_ops,
            )
        )

    @cached_property
    def covfactorH_update_batch(self) -> Tuple[linops.LinearOperator, ...]:
        """Inverse model covariance factor downdate term for all actions and
        observations."""
        if self.prev_cache is None:
            return self.covfactorH_update_ops
        return tuple(
            map(
                lambda x, y: x + y,
                self.prev_cache.covfactorH_update_batch,
                self.covfactorH_update_ops,
            )
        )


class _SystemMatrixSymmetricNormalLinearObsBeliefUpdate(LinearSolverQoIBeliefUpdate):
    pass


class _InverseMatrixSymmetricNormalLinearObsBeliefUpdate(LinearSolverQoIBeliefUpdate):
    def __call__(self, hyperparams: LinearSystemNoise = None) -> rvs.Normal:
        """Updated belief for the matrix model."""
        if hyperparams is None:
            mean = linops.aslinop(self.qoi_prior.mean) + self.mean_update_batch
            cov = linops.SymmetricKronecker(
                self.qoi_prior.cov.A - self.covfactor_updates_batch[0]
            )
        elif isinstance(hyperparams.A_eps, linops.ScalarMult):
            eps_sq = hyperparams.A_eps.cov.A.scalar
            mean = linops.aslinop(self.qoi_prior.mean) + self.mean_update_batch / (
                1 + eps_sq
            )

            cov = linops.SymmetricKronecker(
                self.qoi_prior.cov.A - self.covfactor_updates_batch[0] / (1 + eps_sq)
            ) + linops.SymmetricKronecker(
                eps_sq / (1 + eps_sq) * self.covfactor_updates_batch[1]
            )
        else:
            raise NotImplementedError(
                "Belief updated for general noise not implemented."
            )
        return rvs.Normal(mean=mean, cov=cov)


class _SolutionSymmetricNormalLinearObsBeliefUpdate(LinearSolverQoIBeliefUpdate):
    def __call__(
        self, hyperparams: Optional[LinearSystemNoise] = None
    ) -> Optional[Union[rvs.Normal, np.ndarray]]:
        """Updated belief about the solution."""
        if hyperparams is None and self.prev_state is not None:
            return self.prev_state.residual + self.step_size * self.observation
        else:
            # Belief is induced from inverse and rhs
            return None


class _RightHandSideSymmetricNormalLinearObsBeliefUpdate(LinearSolverQoIBeliefUpdate):
    def __call__(
        self, hyperparams: LinearSystemNoise = None
    ) -> Union[rvs.Constant, rvs.Normal]:
        """Updated belief for the right hand side."""
        if hyperparams is None:
            return rvs.asrandvar(self.problem.b)
        else:
            raise NotImplementedError


class SymmetricNormalLinearObsBeliefUpdate(LinearSolverBeliefUpdate):
    r"""Belief update for a symmetric matrix-variate Normal belief and linear
    observations.

    Updates the posterior beliefs over the quantities of interest of the linear system
    under symmetric matrix-variate Gaussian prior(s) on :math:`A` and / or :math:`H`.
    Observations are assumed to be linear.

    Parameters
    ----------
    """

    def __init__(
        self,
        problem: LinearSystem,
        prior: LinearSystemBelief,
        x_belief_update_type=_SolutionSymmetricNormalLinearObsBeliefUpdate,
        A_belief_update_type=_SystemMatrixSymmetricNormalLinearObsBeliefUpdate,
        Ainv_belief_update_type=_InverseMatrixSymmetricNormalLinearObsBeliefUpdate,
        b_belief_update_type=_RightHandSideSymmetricNormalLinearObsBeliefUpdate,
    ):
        super().__init__(
            problem=problem,
            prior=prior,
            x_belief_update_type=x_belief_update_type,
            A_belief_update_type=A_belief_update_type,
            Ainv_belief_update_type=Ainv_belief_update_type,
            b_belief_update_type=b_belief_update_type,
        )