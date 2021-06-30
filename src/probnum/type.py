"""Custom type aliases.

This module defines commonly used types in the library. These are separated into two
different kinds, API types and argument types.

API types are aliases which define custom types used throughout the library. Objects of
this type may be supplied as arguments or returned by a method.

Argument types are aliases which define commonly used method arguments. These should
only ever be used in the signature of a method and then be converted internally, e.g.
in a class instantiation or an interface. They enable the user to conveniently
specify a variety of object types for the same argument, while ensuring a unified
internal representation of those same objects.
"""

import numbers
from typing import Iterable, Tuple, Union

import numpy as np
import scipy.sparse
import scipy.sparse.linalg

########################################################################################
# API Types
########################################################################################

ShapeType = Tuple[int, ...]

RandomStateType = Union[np.random.RandomState, np.random.Generator]
"""Type of a random number generator."""

########################################################################################
# Argument Types
########################################################################################

IntArgType = Union[int, numbers.Integral, np.integer]
FloatArgType = Union[float, numbers.Real, np.floating]

ShapeArgType = Union[IntArgType, Iterable[IntArgType]]
"""Type of a public API argument for supplying a shape. Values of this type should
always be converted into :class:`ShapeType` using the function
:func:`probnum.utils.as_shape` before further internal processing."""

DTypeArgType = Union[np.dtype, str]
"""Type of a public API argument for supplying a dtype. Values of this type should
always be converted into :class:`np.dtype` using the function
:func:`np.dtype` before further internal processing."""

ScalarArgType = Union[int, float, complex, numbers.Number, np.number]
"""Type of a public API argument for supplying a scalar value. Values of this type
should always be converted into :class:`np.generic` using the function
:func:`probnum.utils.as_scalar` before further internal processing."""

MatrixArgType = Union[
    np.ndarray, scipy.sparse.spmatrix, scipy.sparse.linalg.LinearOperator
]

ArrayLikeGetitemArgType = Union[
    int,
    slice,
    np.ndarray,
    np.newaxis,
    None,
    type(Ellipsis),
    Tuple[Union[int, slice, np.ndarray, np.newaxis, None, type(Ellipsis)], ...],
]

RandomStateArgType = Union[None, int, np.random.RandomState, np.random.Generator]
"""Type of a public API argument for supplying a random number generator. Values of this
type should always be converted into :class:`RandomStateType` using the function
:func:`probnum.utils.as_random_state` before further internal processing."""


########################################################################################
# Other Types
########################################################################################

ToleranceDiffusionType = Union[FloatArgType, np.ndarray]
r"""Type of a quantity that describes tolerances, errors, and diffusions.

Used for absolute (atol) and relative tolerances (rtol), local error estimates, as well as
(the diagonal entries of diagonal matrices representing) diffusion models.
atol, rtol, and diffusion are usually floats, but can be generalized to arrays -- essentially,
to every :math:`\tau` that allows arithmetic operations such as

.. math:: \tau + tau * \text{vec}, \text{ or } L \otimes \text{diag}(\tau)

respectively. Currently, the array-support for diffusions is experimental (at best).
"""

DenseOutputLocationArgType = Union[FloatArgType, np.ndarray]
"""TimeSeriesPosteriors and derived classes can be evaluated at a single location 't'
or an array of locations."""
