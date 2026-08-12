"""Small linear-algebra helpers: 3-vector geometry and a few rotation utilities.

The 3-vector functions are written against the last axis, so each works on a
single ``(3,)`` vector or on a stack of them (``(n, 3)``, ``(n, m, 3)``) with no
change at the call site. That is not decoration: the callers in
:mod:`chisurf.core.structure.protein` invoke them once per residue from a Python
loop, and a stacked call is how that loop stops being one.

These used to be ``numba``-compiled. They are not any more, and the measurement
that decided it is worth keeping: at ~0.4 s to import and a further 0.4-0.8 s to
JIT on the first ``angle()`` call, over a second was spent before the first
residue of a structure was processed -- against 3.4 ms for ten thousand compiled
calls. The import cost is why :mod:`chisurf.core.math` had to serve its
submodules lazily (PEP 562) in the first place.
"""

from __future__ import annotations

from math import cos, sin, sqrt

import numpy as np

from chisurf import typing


def cartesian(arrays: typing.List[np.array], out=None):
    """Compute the cartesian product of input arrays.

    :param arrays: list of arrays
        1-D arrays to form the cartesian product of.
    :param out: 2-D array of shape (M, len(arrays)) containing cartesian products
        formed of input arrays.
    :return: 2-D array of shape (M, len(arrays)) containing cartesian products
        formed of input arrays.

    Examples
    --------

    >>> cartesian([[1, 2, 3], [4, 5], [6, 7]])
    array([[1, 4, 6],
           [1, 4, 7],
           [1, 5, 6],
           [1, 5, 7],
           [2, 4, 6],
           [2, 4, 7],
           [2, 5, 6],
           [2, 5, 7],
           [3, 4, 6],
           [3, 4, 7],
           [3, 5, 6],
           [3, 5, 7]])

    """

    arrays = [np.asarray(x) for x in arrays]
    dtype = arrays[0].dtype

    n = np.prod([x.size for x in arrays])
    if out is None:
        out = np.zeros([n, len(arrays)], dtype=dtype)

    m = n // arrays[0].size
    out[:, 0] = np.repeat(arrays[0], m)
    if arrays[1:]:
        cartesian(arrays[1:], out=out[0:m,1:])
        for j in range(1, arrays[0].size):
            out[j*m:(j+1)*m,1:] = out[0:m,1:]
    return out


def sub3(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Subtract ``b`` from ``a``.

    Parameters
    ----------
    a, b : numpy.ndarray
        Vectors with 3 elements on the last axis.

    Returns
    -------
    numpy.ndarray
        ``a - b``.

    Example
    -------
    >>> import numpy as np
    >>> sub3(np.array([1., 0, 0]), np.array([0., 0, 0]))
    array([1., 0., 0.])
    """
    return np.subtract(a, b)


def add3(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Add two 3-vectors.

    Parameters
    ----------
    a, b : numpy.ndarray
        Vectors with 3 elements on the last axis.

    Returns
    -------
    numpy.ndarray
        ``a + b``.
    """
    return np.add(a, b)


def dot3(a: np.ndarray, b: np.ndarray) -> float | np.ndarray:
    """Dot product along the last axis.

    Parameters
    ----------
    a, b : numpy.ndarray
        Vectors with 3 elements on the last axis.

    Returns
    -------
    float or numpy.ndarray
        The scalar product; an array if the inputs are stacked.
    """
    return np.sum(np.multiply(a, b), axis=-1)


def cross3(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Cross product along the last axis.

    Parameters
    ----------
    a, b : numpy.ndarray
        Vectors with 3 elements on the last axis.

    Returns
    -------
    numpy.ndarray
        ``a x b``.
    """
    return np.cross(a, b)


def norm3(a: np.ndarray) -> float | np.ndarray:
    """Euclidean length along the last axis.

    Parameters
    ----------
    a : numpy.ndarray
        Vector with 3 elements on the last axis.

    Returns
    -------
    float or numpy.ndarray
        The length; an array if the input is stacked.
    """
    return np.sqrt(np.sum(np.multiply(a, a), axis=-1))


def sq_dist3(u: np.ndarray, v: np.ndarray) -> float | np.ndarray:
    """Squared Euclidean distance along the last axis.

    Parameters
    ----------
    u, v : numpy.ndarray
        Vectors with 3 elements on the last axis.

    Returns
    -------
    float or numpy.ndarray
        ``|u - v|**2``.
    """
    d = np.subtract(u, v)
    return np.sum(np.multiply(d, d), axis=-1)


def dist3(a: np.ndarray, b: np.ndarray) -> float | np.ndarray:
    """Euclidean distance along the last axis.

    Parameters
    ----------
    a, b : numpy.ndarray
        Vectors with 3 elements on the last axis.

    Returns
    -------
    float or numpy.ndarray
        ``|a - b|``.

    Example
    -------
    >>> import numpy as np
    >>> float(dist3(np.array([1., 0, 0]), np.array([0., 0, 0])))
    1.0
    """
    return np.sqrt(sq_dist3(a, b))


def angle(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float | np.ndarray:
    """The angle subtended at ``b`` by ``a`` and ``c``.

    Parameters
    ----------
    a, b, c : numpy.ndarray
        Points with 3 coordinates on the last axis.

    Returns
    -------
    float or numpy.ndarray
        The angle in radians; an array if the inputs are stacked.

    Notes
    -----
    The cosine is clamped to ``[-1, 1]`` before :func:`numpy.arccos`. This is
    not defensive padding: for three nearly collinear points the normalised dot
    product overshoots one by up to ``4.4e-16`` in double precision, and
    ``arccos`` of that is ``NaN``. Collinear backbone atoms are ordinary, so the
    unclamped form returned ``NaN`` for real structures. :func:`dihedral` has
    always clamped; this did not.

    Example
    -------
    >>> import numpy as np
    >>> a = np.array([0., 0, 0])
    >>> b = np.array([1., 0, 0])
    >>> c = np.array([0., 1, 0])
    >>> round(float(angle(a, b, c)) / np.pi * 360, 6)
    90.0
    """
    r12 = np.subtract(a, b)
    r23 = np.subtract(c, b)
    d = dot3(r12, r23) / (norm3(r12) * norm3(r23))
    return np.arccos(np.clip(d, -1.0, 1.0))


def dihedral(
        v1: np.ndarray,
        v2: np.ndarray,
        v3: np.ndarray,
        v4: np.ndarray
) -> float | np.ndarray:
    """Dihedral angle defined by four points.

    Obtain ``b1``, ``b2`` and ``b3`` by subtraction, then the plane normals
    ``n1 = b1 x b2`` and ``n2 = b2 x b3``. The angle sought is the angle between
    ``n1`` and ``n2``. The three vectors ``n1``, ``<b2>`` and ``m1 = n1 x <b2>``
    form an orthonormal frame; expressing ``n2`` in it gives ``x = n1.n2`` and
    ``y = m1.n2``, and the signed angle is ``atan2(y, x)``.

    ``atan2`` is used rather than ``acos`` both because it produces an angle over
    a range of 2*pi naturally, and because ``acos`` is poorly conditioned when the
    angle is close to 0 or +-pi.

    Parameters
    ----------
    v1, v2, v3, v4 : numpy.ndarray
        Points with 3 coordinates on the last axis.

    Returns
    -------
    float or numpy.ndarray
        The dihedral angle in radians; an array if the inputs are stacked.

    Example
    -------
    >>> import numpy as np
    >>> a = np.array([-1., 1, 0])
    >>> b = np.array([-1., 0, 0])
    >>> c = np.array([0., 0, 0])
    >>> d = np.array([0., -1, 0])
    >>> round(float(dihedral(a, b, c, d)) / np.pi * 360, 6)
    -360.0
    """
    b1 = np.subtract(v1, v2)
    b2 = np.subtract(v2, v3)
    b3 = np.subtract(v3, v4)
    n1 = cross3(b1, b2)
    n2 = cross3(b2, b3)
    m1 = cross3(b2, n1)

    n2_inv = 1.0 / norm3(n2)
    cos_phi = dot3(n1, n2) * (1.0 / norm3(n1) * n2_inv)
    sin_phi = dot3(m1, n2) * (1.0 / norm3(m1) * n2_inv)
    return -np.arctan2(
        np.clip(sin_phi, -1.0, 1.0),
        np.clip(cos_phi, -1.0, 1.0),
    )


def solve_richardson_lucy(
        p: np.array,
        u: np.array,
        d: np.array,
        max_iter: int
) -> np.ndarray:
    """Richardson-Lucy deconvolution.

    Parameters
    ----------
    p : numpy.ndarray
        Point-spread matrix of shape ``(n_i, n_j)``.
    u : numpy.ndarray
        Current estimate of length ``n_j``; updated in place and returned.
    d : numpy.ndarray
        Observed data of length ``n_i``.
    max_iter : int
        Number of iterations.

    Returns
    -------
    numpy.ndarray
        The estimate ``u`` after ``max_iter`` iterations.
    """
    for _ in range(max_iter):
        c = p @ u
        u[:] = u * (d / c @ p)
    return u


def euler_matrix(
        psi,
        theta,
        phi,
        approx:bool = False
) -> np.ndarray:
    """Return homogeneous rotation matrix from Euler angles psi, theta and phi

    Here the Euler-angles are defined according to DIN 9300. For small angles the Trigonometric functions can be
    approximated by the first order if the parameter approx is True.

    :param psi: double
        yaw-angle
    :param theta: double
        pitch-angle
    :param phi: double
        yaw-angle
    :param approx: bool

    """

    if approx is False:
        sin_psi, sin_theta, sin_phi = sin(psi), sin(theta), sin(phi)
        cos_psi, cos_theta, cos_phi = cos(psi), cos(theta), cos(phi)
    else:
        sin_psi, sin_theta, sin_phi = psi, theta, phi
        cos_psi, cos_theta, cos_phi = 1-abs(psi), 1-abs(theta), 1-abs(phi)

    m = np.identity(3)

    m[0, 0] = cos_theta * cos_psi
    m[0, 1] = cos_theta * sin_psi
    m[0, 2] = -sin_theta

    m[1, 0] = sin_phi * sin_theta * cos_psi - cos_phi * sin_psi
    m[1, 1] = sin_phi * sin_theta * sin_psi + cos_phi * cos_psi
    m[1, 2] = sin_phi * cos_theta

    m[2, 0] = cos_phi * sin_theta * cos_psi + sin_phi * sin_psi
    m[2, 1] = cos_phi * sin_theta * sin_psi - sin_phi * cos_psi
    m[2, 2] = cos_phi * cos_theta
    return m


def vector4_norm(v: np.ndarray) -> np.ndarray:
    """Normalise a 4-vector in place.

    Parameters
    ----------
    v : numpy.ndarray
        4-element vector, modified in place.

    Returns
    -------
    numpy.ndarray
        The same array, normalised.
    """
    s = sqrt(v[0]**2 + v[1]**2 + v[2]**2 + v[3]**2)
    v[0] /= s
    v[1] /= s
    v[2] /= s
    v[3] /= s
    return v


def quaternion_about_axis(angle: float, axis: np.ndarray) -> np.ndarray:
    """Return the quaternion for a rotation about an axis.

    Parameters
    ----------
    angle : float
        Rotation angle in radians.
    axis : numpy.ndarray
        3-element axis; need not be normalised.

    Returns
    -------
    numpy.ndarray
        Quaternion ``(w, x, y, z)``.
    """
    q = np.array([0.0, axis[0], axis[1], axis[2]], dtype=np.float64)
    vector4_norm(q)
    q[1] *= sin(angle/2.0)
    q[2] *= sin(angle/2.0)
    q[3] *= sin(angle/2.0)
    q[0] = cos(angle/2.0)
    return q


def quaternion_multiply(
        quaternion0: np.ndarray,
        quaternion1: np.ndarray
) -> np.ndarray:
    """Multiply ``quaternion1`` into ``quaternion0`` in place.

    Parameters
    ----------
    quaternion0 : numpy.ndarray
        Left factor ``(w, x, y, z)``; modified in place.
    quaternion1 : numpy.ndarray
        Right factor ``(w, x, y, z)``.

    Returns
    -------
    numpy.ndarray
        ``quaternion0``, holding the product.
    """
    w0, x0, y0, z0 = quaternion0
    w1, x1, y1, z1 = quaternion1

    quaternion0[0] = -x1*x0 - y1*y0 - z1*z0 + w1*w0
    quaternion0[1] = x1*w0 + y1*z0 - z1*y0 + w1*x0
    quaternion0[2] = -x1*z0 + y1*w0 + z1*x0 + w1*y0
    quaternion0[3] = x1*y0 - y1*x0 + z1*w0 + w1*z0
    return quaternion0


def rotate_point(p3: np.ndarray, quaternion: np.ndarray) -> np.ndarray:
    """Rotate a 3D point by a quaternion.

    Applies ``p' = p + 2w(v x p) + 2(v x (v x p))`` with ``v`` the vector part.

    Parameters
    ----------
    p3 : numpy.ndarray
        3-element point.
    quaternion : numpy.ndarray
        4-element quaternion ``(w, x, y, z)``.

    Returns
    -------
    numpy.ndarray
        The rotated point.

    Notes
    -----
    The vector part was sliced as ``quaternion[1:3]`` -- two elements, not
    three -- so every call reached past the end of it inside :func:`cross3`.
    Under the previous ``numba`` compilation that read whatever followed in
    memory instead of raising, which is why a function this broken could sit
    here: it has no callers, and nothing ever ran it.
    """
    v = quaternion[1:4]
    w = quaternion[0]

    vCp3 = cross3(v, p3)
    vCvCp3 = cross3(v, vCp3) * 2

    p_new = np.zeros(3, dtype=np.float64)
    p_new[0] = p3[0] + vCp3[0]*(2*w) + vCvCp3[0]
    p_new[1] = p3[1] + vCp3[1]*(2*w) + vCvCp3[1]
    p_new[2] = p3[2] + vCp3[2]*(2*w) + vCvCp3[2]

    return p_new
