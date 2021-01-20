try:
    # functools.cached_property is only available in Python >=3.8
    from functools import cached_property
except ImportError:
    from cached_property import cached_property

import dataclasses
from typing import Optional, Tuple, Union

import numpy as np

import probnum
import probnum.linops as linops
import probnum.random_variables as rvs
from probnum.linalg.solvers.belief_updates._belief_update import (
    LinearSolverBeliefUpdate,
)
from probnum.linalg.solvers.beliefs import (
    LinearSystemNoise,
    NoisySymmetricNormalLinearSystemBelief,
    SymmetricNormalLinearSystemBelief,
)
from probnum.problems import LinearSystem

# Public classes and functions. Order is reflected in documentation.
__all__ = [
    "SymmetricNormalLinearObsBeliefUpdate",
    "LinearSolverBeliefUpdateTerms",
]


@dataclasses.dataclass
class LinearSolverBeliefUpdateTerms:
    r"""Belief update terms for a quantity of interest.

    Collects the belief update terms for a quantity of interest of a linear
    system, i.e. additive terms for the mean and covariance (factors).
    """
    mean: Optional[linops.LinearOperator] = None
    cov: Optional[linops.LinearOperator] = None
    covfactors: Optional[Tuple[linops.LinearOperator, ...]] = None


@dataclasses.dataclass
class SymmetricNormalLinearObsBeliefUpdateState(LinearSolverBeliefUpdateState):
    r"""Quantities computed for the belief update of a linear solver.

    This state assumes a symmetric matrix-variate Normal belief and linear
    observations.

    Parameters
    ----------
    problem
        Linear system to be solved.
    belief
        Belief over the quantities of the linear system.
    actions
        Performed actions.
    observations
        Collected observations of the problem.
    residual
        Residual :math:`r = A x_i- b` of the solution estimate
        :math:`x_i=\mathbb{E}[\mathsf{x}]` at iteration :math:`i`.
    action_obs_innerprods
        Inner product(s) :math:`(S^\top Y)_{ij} = s_i^\top y_j` of actions
        and observations. If a vector, actions and observations are assumed to be
        conjugate, i.e. :math:`s_i^\top y_j =0` for :math:`i \neq j`.
    log_rayleigh_quotients
        Log-Rayleigh quotients :math:`\ln R(A, s_i) = \ln(s_i^\top A s_i)-\ln(s_i^\top
        s_i)`.
    step_sizes
        Step sizes :math:`\alpha_i` of the solver viewed as a quadratic optimizer taking
        steps :math:`x_{i+1} = x_i + \alpha_i s_i`.
    x
        Belief update term for the solution.
    A
        Belief update term for the system matrix.
    Ainv
        Belief update term for the inverse.
    b
        Belief update term for the right hand side.
    """
    x: Optional[LinearSolverBeliefUpdateTerms] = None
    A: Optional[LinearSolverBeliefUpdateTerms] = None
    Ainv: Optional[LinearSolverBeliefUpdateTerms] = None
    b: Optional[LinearSolverBeliefUpdateTerms] = None


class SymmetricNormalLinearObsBeliefUpdate(LinearSolverBeliefUpdate):
    r"""Belief update for a symmetric matrix-variate Normal belief and linear
    observations.

    Updates the posterior beliefs over the quantities of interest of the linear system
    under symmetric matrix-variate Gaussian prior(s) on :math:`A` and / or :math:`H`.
    Observations are assumed to be linear.

    Examples
    --------

    """

    def update(
        self,
        problem: LinearSystem,
        belief: "probnum.linalg.solvers.beliefs.LinearSystemBelief",
        actions: np.ndarray,
        observations: np.ndarray,
        hyperparams: LinearSystemNoise = LinearSystemNoise(A_eps=None, b_eps=None),
        solver_state: Optional["probnum.linalg.solvers.LinearSolverState"] = None,
    ) -> SymmetricNormalLinearSystemBelief:

        # Compute update terms

        # Construct updated beliefs
        A_updated = None
        Ainv_updated = None
        b_updated = None
        x_updated = self._updated_belief_x(
            belief_x=belief.x,
            updated_belief_Ainv=Ainv_updated,
            updated_belief_b=b_updated,
            noise=hyperparams,
            solver_state=solver_state,
        )

        # Clear cache of state attributes which were not explicitly updated

        if hyperparams.A_eps is None and hyperparams.b_eps is None:
            return SymmetricNormalLinearSystemBelief(
                x=x_updated,
                Ainv=Ainv_updated,
                A=A_updated,
                b=b_updated,
            )

        else:
            return NoisySymmetricNormalLinearSystemBelief(
                x=x_updated,
                Ainv=Ainv_updated,
                A=A_updated,
                b=b_updated,
                noise=hyperparams,
            )

    def _updated_belief_x(
        self,
        belief_x: rvs.Normal,
        updated_belief_Ainv: rvs.Normal,
        updated_belief_b: Union[rvs.Constant, rvs.Normal],
        noise: LinearSystemNoise,
        solver_state: Optional["probnum.linalg.solvers.LinearSolverState"],
    ) -> Tuple[
        Optional[Union[np.ndarray, rvs.Normal]],
        Optional["probnum.linalg.solvers.LinearSolverState"],
    ]:
        """Updated Gaussian belief about the solution :math:`x` of the linear system."""
        if noise.A_eps is None and noise.b_eps is None:
            update_terms_x, solver_state = self._update_terms_x(
                belief_x=belief_x,
                updated_belief_Ainv=updated_belief_Ainv,
                updated_belief_b=updated_belief_b,
                noise=noise,
                solver_state=solver_state,
            )
            return belief_x.mean + update_terms_x.mean, solver_state
        else:
            return None, solver_state

    def _update_terms_x(
        self,
        belief_x: rvs.Normal,
        updated_belief_Ainv: rvs.Normal,
        updated_belief_b: Union[rvs.Constant, rvs.Normal],
        noise: LinearSystemNoise,
        solver_state: Optional["probnum.linalg.solvers.LinearSolverState"],
    ) -> Tuple[
        LinearSolverBeliefUpdateTerms,
        Optional["probnum.linalg.solvers.LinearSolverState"],
    ]:
        r"""Mean and covariance update terms for the solution.

        For a prior belief :math:`\mathsf{x} \sim \mathcal{N}(\mu, \Sigma)`, computes
        the update terms :math:`\mu_{\text{update}}(y)` and
        :math:`\Sigma_{\text{update}}(y)` given observations :math:`y`, such that
        :math:`\mathsf{x} \mid y \sim \mathcal{N}(\mu +\mu_{\text{update}}(y), \Sigma -
        \Sigma_{\text{update}}(y))`.
        """
        if noise.A_eps is None and noise.b_eps is None:
            # Current residual
            residual = solver_state.residual

            # Step size
            step_size = self._step_size(
                residual=residual,
                action=self.action,
                observation=self.observation,
            )
            # Solution estimate update
            x_mean_update = step_size * self.action

            # Update residual
            self._residual(
                residual=residual,
                step_size=step_size,
                observation=self.observation,
            )
            return x_mean_update, None
        else:
            raise NotImplementedError

    @cached_property
    def A(self) -> rvs.Normal:
        """Updated Gaussian belief about the system matrix :math:`A`."""
        mean_update, cov_update = self.A_update_terms(belief_A=self.belief.A)
        A_mean = linops.aslinop(self.belief.A.mean) + mean_update
        A_covfactor = linops.aslinop(self.belief.A.cov.A) - cov_update

        return rvs.Normal(mean=A_mean, cov=linops.SymmetricKronecker(A_covfactor))

    def A_update_terms(
        self,
        belief_A: rvs.Normal,
    ) -> Tuple[
        Union[np.ndarray, linops.LinearOperator],
        Union[np.ndarray, linops.LinearOperator],
    ]:
        r"""Mean and covariance update terms for the system matrix.

        For a prior belief :math:`\mathsf{A} \sim \mathcal{N}(A_0, W \otimes_s W)`,
        computes the update terms :math:`A_{\text{update}}(y)` and
        :math:`W_{\text{update}}(y)` given observations :math:`y`, such that
        :math:`\mathsf{A} \mid y \sim \mathcal{N}\big(A_0 +A_{\text{update}}(y), (W -
        W_{\text{update}}(y)) \otimes_s (W - W_{\text{update}}(y))\big)`.

        Parameters
        ----------
        belief_A : Belief over the system matrix.
        """
        u, v, Ws = self._matrix_model_update_components(
            belief_matrix=belief_A,
            action=self.action,
            observation=self.observation,
        )
        # Rank 2 mean update (+= uv' + vu')
        mean_update = self._matrix_model_mean_update_op(u=u, v=v)
        # Rank 1 covariance Kronecker factor update (-= u(Ws)')
        cov_update = self._matrix_model_covariance_factor_update_op(u=u, Ws=Ws)

        return mean_update, cov_update

    @cached_property
    def Ainv(self) -> rvs.Normal:
        """Updated Gaussian belief about the inverse of the system matrix
        :math:`H=A^{-1}`."""
        mean_update, cov_update = self.Ainv_update_terms(belief_Ainv=self.belief.Ainv)
        Ainv_mean = linops.aslinop(self.belief.Ainv.mean) + mean_update
        Ainv_covfactor = linops.aslinop(self.belief.Ainv.cov.A) - cov_update

        return rvs.Normal(mean=Ainv_mean, cov=linops.SymmetricKronecker(Ainv_covfactor))

    def Ainv_update_terms(
        self, belief_Ainv: rvs.Normal
    ) -> Tuple[
        Union[np.ndarray, linops.LinearOperator],
        Union[np.ndarray, linops.LinearOperator],
    ]:
        r"""Mean and covariance update terms for the inverse.

        For a prior belief :math:`\mathsf{H} \sim \mathcal{N}(H_0, W \otimes_s W)`,
        computes the update terms :math:`H_{\text{update}}(y)` and
        :math:`W_{\text{update}}(y)` given observations :math:`y`, such that
        :math:`\mathsf{H} \mid y \sim \mathcal{N}\big(H_0 +H_{\text{update}}(y), (W -
        W_{\text{update}}(y)) \otimes_s (W - W_{\text{update}}(y))\big)`.

        Parameters
        ----------
        belief_Ainv : Belief over the inverse.
        """
        u, v, Wy = self._matrix_model_update_components(
            belief_matrix=belief_Ainv,
            action=self.observation,
            observation=self.action,
        )
        # Rank 2 mean update (+= uv' + vu')
        mean_update = self._matrix_model_mean_update_op(u=u, v=v)
        # Rank 1 covariance Kronecker factor update (-= u(Wy)')
        cov_update = self._matrix_model_covariance_factor_update_op(u=u, Ws=Wy)
        return mean_update, cov_update

    @cached_property
    def b(self) -> Union[rvs.Normal, rvs.Constant]:
        """Updated belief about the right hand side :math:`b` of the linear system."""
        return self.belief.error_b

    def _residual(
        self,
        residual: np.ndarray,
        step_size: float,
        observation: np.ndarray,
    ) -> np.ndarray:
        """Update the residual :math:`r_i = Ax_i - b`."""
        new_residual = residual + step_size * observation
        if self.solver_state is not None:
            self.solver_state.residual = new_residual
        return new_residual

    @staticmethod
    def _matrix_model_update_components(
        belief_matrix: rvs.RandomVariable,
        action: np.ndarray,
        observation: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        r"""Computes the components :math:`u=Ws(s^\top Ws)^{-1}` and :math:`v=\Delta
        - \frac{1}{2}(y^\top \Delta) u` of the update."""
        Ws = belief_matrix.cov.A @ action
        delta_A = observation - belief_matrix.mean @ action
        u = Ws / (action.T @ Ws)
        v = delta_A - 0.5 * (action.T @ delta_A) * u

        return u, v, Ws

    @staticmethod
    def _matrix_model_mean_update_op(
        u: np.ndarray, v: np.ndarray
    ) -> linops.LinearOperator:
        """Linear operator implementing the symmetric rank 2 mean update (+= uv' +
        vu')."""

        def mv(x):
            return u * (v.T @ x) + v * (u.T @ x)

        def mm(x):
            return u @ (v.T @ x) + v @ (u.T @ x)

        return linops.LinearOperator(
            shape=(u.shape[0], u.shape[0]), matvec=mv, matmat=mm
        )

    @staticmethod
    def _matrix_model_covariance_factor_update_op(
        u: np.ndarray, Ws: np.ndarray
    ) -> linops.LinearOperator:
        """Linear operator implementing the symmetric rank 2 covariance factor downdate
        (-= Ws u')."""

        def mv(x):
            return Ws * (u.T @ x)

        def mm(x):
            return Ws @ (u.T @ x)

        return linops.LinearOperator(
            shape=(u.shape[0], u.shape[0]), matvec=mv, matmat=mm
        )

    def _step_size(
        self,
        residual: np.ndarray,
        action: np.ndarray,
        observation: np.ndarray,
    ) -> float:
        r"""Compute the step size :math:`\alpha` such that :math:`x_{i+1} = x_i +
        \alpha_i s_i`, where :math:`s_i` is the current action."""
        # Compute step size
        if self.solver_state is not None:
            try:
                action_obs_innerprod = self.solver_state.action_obs_innerprods[
                    self.solver_state.iteration
                ]
            except IndexError:
                action_obs_innerprod = (action.T @ observation).item()
        else:
            action_obs_innerprod = (action.T @ observation).item()
        step_size = (-action.T @ residual / action_obs_innerprod).item()

        # Update solver state
        if self.solver_state is not None:
            self.solver_state.action_obs_innerprods.append(action_obs_innerprod)
            self.solver_state.step_sizes.append(step_size)
            self.solver_state.log_rayleigh_quotients.append(
                _log_rayleigh_quotient(
                    action_obs_innerprod=action_obs_innerprod, action=action
                )
            )

        return step_size


def _log_rayleigh_quotient(action_obs_innerprod: float, action: np.ndarray) -> float:
    r"""Compute the log-Rayleigh quotient :math:`\ln R(A, s_i) = \ln(s_i^\top A
    s_i) -\ln(s_i^\top s_i)` for the current action."""
    return (np.log(action_obs_innerprod) - np.log(action.T @ action)).item()