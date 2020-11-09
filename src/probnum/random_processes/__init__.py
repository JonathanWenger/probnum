from ._deterministic_process import DeterministicProcess
from ._gauss_markov_process import GaussMarkovProcess
from ._gaussian_process import GaussianProcess
from ._random_process import RandomProcess
from ._utils import asrandproc

# Public classes and functions. Order is reflected in documentation.
__all__ = [
    "asrandproc",
    "RandomProcess",
    "DeterministicProcess",
    "GaussianProcess",
    "GaussMarkovProcess",
]

# Set correct module paths. Corrects links and module paths in documentation.
RandomProcess.__module__ = "probnum.random_processes"

DeterministicProcess.__module__ = "probnum.random_processes"
GaussianProcess.__module__ = "probnum.random_processes"
GaussMarkovProcess.__module__ = "probnum.random_processes"

asrandproc.__module__ = "probnum.random_processes"
