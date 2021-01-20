"""Tests for the implementation of a generic probabilistic linear solver."""

from typing import Iterator

import numpy as np
import pytest
import scipy.linalg
import scipy.sparse.linalg

from probnum.linalg.solvers import ProbabilisticLinearSolver
from probnum.problems import LinearSystem


def test_solver_state(linsys_spd: LinearSystem, solve_iterator: Iterator):
    """Test whether the solver state is consistent with the iteration."""
    for i in range(10):
        (belief, action, observation, solver_state) = next(solve_iterator)

        # Iteration
        assert solver_state.iteration == i + 1, (
            "Solver state iteration does " "not match iterations performed."
        )

        # Actions
        np.testing.assert_allclose(solver_state.action[-1], action)

        # Observations
        np.testing.assert_allclose(solver_state.observation[-1], observation)

        # Action - observation inner product
        np.testing.assert_allclose(
            solver_state.action_obs_innerprods,
            np.einsum(
                "nk,nk->k",
                np.hstack(solver_state.action),
                np.hstack(solver_state.observation),
            ),
        )

        # Residual
        np.testing.assert_allclose(
            solver_state.residual,
            linsys_spd.A @ belief.x.mean - linsys_spd.b,
            rtol=10 ** -6,
            atol=10 ** -10,
            err_msg="Residual in solver_state does not match actual residual.",
        )


@pytest.mark.xfail(
    raises=AssertionError,
    reason="This is currently not fulfilled for all PLS variants.",
)
def test_solution_equivalence(linsys_spd: LinearSystem, solve_iterator: Iterator):
    """The iteratively computed solution should match the induced solution
    estimate: x_k = E[A^-1] b"""
    for i in range(10):
        (belief, action, observation, solver_state) = next(solve_iterator)
        # E[x] = E[A^-1] b
        np.testing.assert_allclose(
            belief.x.mean,
            belief.Ainv.mean @ linsys_spd.b,
            rtol=1e-5,
            err_msg="Solution from matrix-based probabilistic linear solver "
            "does not match the estimated inverse, i.e. x != Ainv @ b ",
        )


def test_posterior_covariance_posdef(
    linsys_spd: LinearSystem, solve_iterator: Iterator
):
    """Posterior covariances of the output beliefs must be positive (semi-) definite."""
    for i in range(10):
        (belief, action, observation, solver_state) = next(solve_iterator)

        # Check positive definiteness
        eps = 10 ** 6 * np.finfo(float).eps
        assert np.all(
            0 <= scipy.linalg.eigvalsh(belief.A.cov.A.todense()) + eps
        ), "Covariance of A not positive semi-definite."
        assert np.all(
            0 <= scipy.linalg.eigvalsh(belief.Ainv.cov.A.todense()) + eps
        ), "Covariance of Ainv not positive semi-definite."


class TestConjugateDirectionsMethod:
    """Tests for probabilistic linear solvers which are conjugate direction methods."""

    def test_searchdir_conjugacy(
        self,
        conj_dir_method: ProbabilisticLinearSolver,
        linsys_spd: LinearSystem,
        n: int,
        random_state: np.random.RandomState,
    ):
        """Search directions should remain A-conjugate up to machine precision, i.e.
        s_i^T A s_j = 0 for i != j."""
        _, solver_state = conj_dir_method.solve(linsys_spd)
        actions = np.hstack(solver_state.action)

        # Compute pairwise inner products in A-space
        inner_prods = actions.T @ linsys_spd.A @ actions

        # Compare against identity matrix
        np.testing.assert_allclose(
            np.diag(np.diag(inner_prods)),
            inner_prods,
            atol=1e-6 * n,
            err_msg="Search directions from solver are not A-conjugate.",
        )

    def test_convergence_in_at_most_n_iterations(
        self,
        conj_dir_method: ProbabilisticLinearSolver,
        linsys_spd: LinearSystem,
        n: int,
    ):
        """Test whether the PLS takes at most n iterations, i.e. the convergence
        property of conjugate direction methods in exact arithmetic."""
        _, solver_state = conj_dir_method.solve(linsys_spd)
        assert solver_state.iteration <= n


class TestConjugateGradientMethod:
    """Tests for probabilistic linear solvers which are conjugate gradient methods."""

    def test_preconditioned_CG_equivalence(self):
        """Test whether the PLS recovers preconditioned CG in posterior mean for
        specific prior beliefs."""
        # todo use weakmeancorrespondence class with general prior mean to test this
        pass

    def test_CG_equivalence(
        self, conj_grad_method: ProbabilisticLinearSolver, linsys_spd: LinearSystem
    ):
        """The probabilistic linear solver(s) should recover CG iterates as a posterior
        mean for specific prior beliefs."""
        solve_iterator = conj_grad_method.solve_iterator(
            problem=linsys_spd,
            belief=conj_grad_method.prior,
            solver_state=conj_grad_method._init_solver_state(problem=linsys_spd)[1],
        )
        # Conjugate gradient method
        cg_iterates = []

        def callback_iterates_CG(xk):
            cg_iterates.append(
                np.eye(np.shape(linsys_spd.A)[0]) @ xk[:, None]
            )  # identity hack to actually save different iterations

        x0 = conj_grad_method.prior.x.mean
        x_cg, _ = scipy.sparse.linalg.cg(
            A=linsys_spd.A,
            b=linsys_spd.b,
            x0=x0,
            tol=conj_grad_method.stopping_criteria[1].rtol,
            maxiter=conj_grad_method.stopping_criteria[0].maxiter,
            callback=callback_iterates_CG,
        )
        cg_iters_arr = np.hstack([x0] + cg_iterates)

        # Probabilistic linear solver
        pls_iterates = []
        belief = None
        for ind, (belief, action, observation, solver_state) in enumerate(
            solve_iterator
        ):
            pls_iterates.append(belief.x.mean)
            has_converged, solver_state = conj_grad_method.has_converged(
                problem=linsys_spd, belief=belief, solver_state=solver_state
            )
            if has_converged:
                break

        pls_iters_arr = np.hstack([x0] + pls_iterates)
        np.testing.assert_allclose(
            belief.x.mean, x_cg[:, None], atol=10 ** -6, rtol=10 ** -6
        )
        np.testing.assert_allclose(
            pls_iters_arr, cg_iters_arr, atol=10 ** -6, rtol=10 ** -6
        )


class TestHyperparameterOptimization:
    def test_uncertainty_calibration_error(
        self, calibration_method: str, conj_grad_method
    ):
        """Test if the available uncertainty calibration procedures affect the error of
        the returned solution."""
        # TODO
        pass
        # tol = 10 ** -6
        #
        # x_est, Ahat, Ainvhat, info = conj_grad_method(
        #     A=A, b=b, calibration=calibration_method
        # )
        # assert(
        #     ((x_true - x_est.mean).T @ A @ (x_true - x_est.mean)).item() <= tol,
        #     "Estimated solution not sufficiently close to true solution.",
        # )