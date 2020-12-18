"""Probabilistic Linear Solvers.

Iterative probabilistic numerical methods solving linear systems :math:`Ax = b`.
"""

import dataclasses
from typing import Callable, Dict, List, Optional, Tuple, Union

import numpy as np

import probnum.random_variables as rvs
from probnum._probabilistic_numerical_method import (
    PNMethodState,
    ProbabilisticNumericalMethod,
)
from probnum.problems import LinearSystem

from ._policies import LinearSolverPolicy
from ._stopping_criteria import StoppingCriterion

# pylint: disable="invalid-name"


@dataclasses.dataclass
class LinearSolverState(PNMethodState):
    r"""State of a probabilistic linear solver.

    The solver state contains miscellaneous quantities computed during an iteration
    of a probabilistic linear solver. The solver state is passed between the
    different components of the solver and may be used by them.

    For example the residual :math:`r_i = Ax_i - b` can (depending on the prior) be
    updated more efficiently than in :math:`\mathcal{O}(n^2)` and is therefore part
    of the solver state and passed to the stopping criteria.

    Parameters
    ----------
    belief
        Current belief over the solution :math:`x`, the system matrix :math:`A` and the
        inverse :math:`H=A^{-1}`.
    actions
        Performed actions :math:`s_i`.
    observations
        Collected observations :math:`y_i = A s_i`.
    iteration
        Current iteration :math:`i` of the solver.
    residual
        Residual :math:`r_i = Ax_i - b` of the current solution.
    rayleigh_quotients
        Rayleigh quotients :math:`R(A, s_i) = \frac{s_i^\top A s_i}{s_i^\top s_i}`.
    has_converged
        Has the solver converged?
    stopping_criterion
        Stopping criterion which caused termination of the solver.

    Examples
    --------

    """

    actions: List[np.ndarray]
    observations: List[np.ndarray]
    iteration: int = 0
    residual: Optional[Union[np.ndarray, rvs.RandomVariable]] = None
    rayleigh_quotients: Optional[List[float]] = None
    has_converged: bool = False
    stopping_criterion: Optional[List[StoppingCriterion]] = None


class ProbabilisticLinearSolver(ProbabilisticNumericalMethod):
    """Compose a custom probabilistic linear solver.

    Class implementing probabilistic linear solvers. Such (iterative) solvers infer
    solutions to problems of the form

    .. math:: Ax=b,

    where :math:`A \\in \\mathbb{R}^{n \\times n}` and :math:`b \\in \\mathbb{R}^{n}`.
    They return a probability measure which quantifies uncertainty in the output arising
    from finite computational resources or stochastic input. This class unifies and
    generalizes probabilistic linear solvers as described in the literature [1]_ [2]_
    [3]_ [4]_.

    Parameters
    ----------
    prior :
        Prior belief over the quantities of interest :math:`(x, A, A^{-1})` of the
        linear system.
    policy :
        Policy defining actions taken by the solver.
    observe :
        Observation process defining how information about the linear system is
        obtained.
    update_belief :
        Operator updating the belief over the quantities of interest :math:`(x, A,
        A^{-1})` of the linear system.
    stopping_criteria :
        Stopping criteria determining when the solver has converged.
    optimize_hyperparams :
        Function optimizing hyperparameters of the solver.

    References
    ----------
    .. [1] Hennig, P., Probabilistic Interpretation of Linear Solvers, *SIAM Journal on
       Optimization*, 2015, 25, 234-260
    .. [2] Cockayne, J. et al., A Bayesian Conjugate Gradient Method, *Bayesian
       Analysis*, 2019, 14, 937-1012
    .. [3] Bartels, S. et al., Probabilistic Linear Solvers: A Unifying View,
       *Statistics and Computing*, 2019
    .. [4] Wenger, J. and Hennig, P., Probabilistic Linear Solvers for Machine Learning,
       *Advances in Neural Information Processing Systems (NeurIPS)*, 2020

    See Also
    --------
    problinsolve : Solve linear systems in a Bayesian framework.
    bayescg : Solve linear systems with prior information on the solution.

    Examples
    --------
    Create a custom probabilistic linear solver from pre-defined components.

    >>> from probnum.linalg.linearsolvers import ProbabilisticLinearSolver

    >>> #pls = ProbabilisticLinearSolver()

    Define a linear system.

    >>> import numpy as np
    >>> import probnum as pn
    >>> from probnum.problems.zoo.linalg import random_spd_matrix
    >>> n = 20
    >>> A = random_spd_matrix(dim=n, random_state=1)
    >>> b = np.random.rand(n)

    Solve the linear system using the custom solver.

    >>> #sol, info = pls(A, b)
    """

    def __init__(
        self,
        prior: Tuple[rvs.RandomVariable, rvs.RandomVariable, rvs.RandomVariable],
        policy: LinearSolverPolicy,
        observe,
        update_belief,
        stopping_criteria=Optional[List[StoppingCriterion]],
        optimize_hyperparams=None,
    ):
        # pylint: disable="too-many-arguments"
        self.policy = policy
        self.observe = observe
        self.update_belief = update_belief
        self.stopping_criteria = stopping_criteria
        self.optimize_hyperparams = optimize_hyperparams
        super().__init__(
            prior=prior,
        )

    def has_converged(
        self, problem: LinearSystem, solver_state: LinearSolverState
    ) -> Tuple[bool, LinearSolverState]:
        """Check whether the solver has converged.

        Parameters
        ----------
        problem :
            Linear system to solve.
        solver_state :
            Current state of the solver.

        Returns
        -------
        has_converged :
            True if the method has converged.
        solver_state :
            Updated state of the solver.
        """
        if solver_state.has_converged:
            return True, solver_state

        # Check stopping criteria
        for stopping_criterion in self.stopping_criteria:
            _has_converged, convergence_criterion = stopping_criterion(
                problem, self.belief, solver_state
            )
            if _has_converged:
                solver_state.has_converged = True
                solver_state.stopping_criterion = stopping_criterion.__class__.__name__
                return True, convergence_criterion
        return False, solver_state

    def solve_iterator(self, problem: LinearSystem) -> LinearSolverState:
        """Generator implementing the solver iteration.

        This function allows stepping through the solver iteration one step at a time.

        Parameters
        ----------
        problem :
            Linear system to solve.

        Returns
        -------
        solver_state :
            Updated state of the linear solver.
        """
        # Setup
        solver_state = LinearSolverState(
            belief=self.prior,
            actions=[],
            observations=[],
            iteration=0,
            residual=problem.A @ self.prior[0].mean - problem.b,
            rayleigh_quotients=[],
            has_converged=False,
            stopping_criterion=None,
        )

        # Evaluate stopping criteria for
        _has_converged, solver_state = self.has_converged(
            problem=problem, solver_state=solver_state
        )

        while not _has_converged:
            # Compute action via policy
            action = self.policy(problem, solver_state.belief)
            solver_state.actions.append(action)

            # Make an observation of the linear system
            observation = self.observe(problem, action)
            solver_state.observations.append(observation)

            # Update the belief over the system matrix, its inverse and/or the solution
            solver_state.belief = self.update_belief(
                solver_state.belief, action, observation
            )

            # Evaluate stopping criteria
            _has_converged, solver_state = self.has_converged(
                problem=problem, solver_state=solver_state
            )

            yield solver_state

    def solve(
        self,
        problem: LinearSystem,
    ) -> Tuple[
        Tuple[rvs.RandomVariable, rvs.RandomVariable, rvs.RandomVariable],
        LinearSolverState,
    ]:
        """Solve the linear system.

        Parameters
        ----------
        problem :
            Linear system to solve.

        Returns
        -------
        """

        solve_iterator = self.solve_iterator(problem=problem)

        for solver_state in solve_iterator:
            pass

        # Belief over solution, inverse and system matrix
        x, A, Ainv = self._belief_solution()

        return (x, A, Ainv), solver_state

    def _belief_solution(self):
        """Compute the belief over the components of the linear system."""
        raise NotImplementedError
