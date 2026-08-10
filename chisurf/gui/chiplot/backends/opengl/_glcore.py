"""Qt-independent OpenGL rendering helpers for chiplot.

Uses Qt's GL wrappers (:class:`QOpenGLShaderProgram`, :class:`QOpenGLBuffer`)
for shader/buffer management — the same pattern chimol's renderer uses —
because they work reliably on macOS where raw PyOpenGL shader compilation
hits version mismatches. PyOpenGL is still used for draw calls and GL state.

The :class:`ViewTransform` maps data coordinates to clip space and is
fully Qt-free, keeping the data-transform logic reusable.
"""

from __future__ import annotations

import math

import numpy as np
from OpenGL import GL
from qtpy import QtGui


# ---------------------------------------------------------------------------
# Shader sources (GLSL 1.10 compatible — no #version needed)
# ---------------------------------------------------------------------------

_VERT_SRC = """
uniform mat4 u_mvp;
attribute vec2 a_pos;
attribute vec4 a_color;
varying vec4 v_color;
void main() {
    gl_Position = u_mvp * vec4(a_pos, 0.0, 1.0);
    v_color = a_color;
}
"""

_FRAG_SRC = """
uniform vec4 u_color;
uniform int  u_use_vertex_color;
varying vec4 v_color;
void main() {
    gl_FragColor = (u_use_vertex_color == 1) ? v_color : u_color;
}
"""

_POINT_VERT_SRC = """
uniform mat4 u_mvp;
uniform float u_point_size;
attribute vec2 a_pos;
attribute vec4 a_color;
varying vec4 v_color;
void main() {
    gl_Position = u_mvp * vec4(a_pos, 0.0, 1.0);
    gl_PointSize = u_point_size;
    v_color = a_color;
}
"""

_IMAGE_VERT_SRC = """
uniform mat4 u_mvp;
attribute vec2 a_pos;
attribute vec2 a_uv;
varying vec2 v_uv;
void main() {
    gl_Position = u_mvp * vec4(a_pos, 0.0, 1.0);
    v_uv = a_uv;
}
"""

_IMAGE_FRAG_SRC = """
uniform sampler2D u_texture;
uniform float     u_opacity;
varying vec2 v_uv;
void main() {
    vec4 texel = texture2D(u_texture, v_uv);
    gl_FragColor = vec4(texel.rgb, texel.a * u_opacity);
}
"""


class ShaderProgram:
    """A linked GLSL program backed by :class:`QOpenGLShaderProgram`.

    Parameters
    ----------
    vert_src : str
        Vertex shader source.
    frag_src : str
        Fragment shader source.
    """

    def __init__(self, vert_src: str, frag_src: str):
        self._prog = QtGui.QOpenGLShaderProgram()
        ok = (
            self._prog.addShaderFromSourceCode(QtGui.QOpenGLShader.Vertex, vert_src)
            and self._prog.addShaderFromSourceCode(QtGui.QOpenGLShader.Fragment, frag_src)
            and self._prog.link()
        )
        if not ok:
            raise RuntimeError(f"GLSL link error: {self._prog.log()}")
        self._uniforms: dict[str, int] = {}

    def use(self) -> None:
        """Make this the active program."""
        self._prog.bind()

    def release(self) -> None:
        """Deactivate the program."""
        self._prog.release()

    def uniform_loc(self, name: str) -> int:
        """Return the location of *name*, cached on first lookup."""
        loc = self._uniforms.get(name)
        if loc is None:
            loc = self._prog.uniformLocation(name)
            self._uniforms[name] = loc
        return loc

    def set_matrix4(self, name: str, mat: np.ndarray) -> None:
        """Upload a 4x4 float matrix uniform."""
        self._prog.setUniformValue(self.uniform_loc(name), QtGui.QMatrix4x4(mat.flatten()))

    def set_float(self, name: str, value: float) -> None:
        """Upload a scalar float uniform.

        The binding has a single overloaded ``setUniformValue``; it selects the
        GLSL type from the Python type, so the value must be a real ``float``
        (a Python ``int`` would bind an ``int`` uniform and silently miss).
        """
        self._prog.setUniformValue(self.uniform_loc(name), float(value))

    def set_int(self, name: str, value: int) -> None:
        """Upload a scalar int uniform."""
        self._prog.setUniformValue(self.uniform_loc(name), int(value))

    def set_vec2(self, name: str, values: tuple[float, float]) -> None:
        """Upload a vec2 uniform."""
        self._prog.setUniformValue(
            self.uniform_loc(name), float(values[0]), float(values[1]))

    def set_vec4(self, name: str, values: tuple[float, float, float, float]) -> None:
        """Upload a vec4 uniform."""
        self._prog.setUniformValue(
            self.uniform_loc(name),
            float(values[0]), float(values[1]), float(values[2]), float(values[3]),
        )

    def set_attribute(self, name: str, data: np.ndarray, stride: int = 0) -> None:
        """Upload a float vertex attribute array through a cached VBO.

        The array goes to the GPU as a buffer rather than through the
        binding's ``setAttributeArray``, which converts a NumPy array element
        by element in Python — unusable for the hundred-thousand-point curves
        this backend exists to draw.

        Parameters
        ----------
        name : str
            Attribute name in the shader.
        data : numpy.ndarray
            ``(N, K)`` array of vertex data (cast to float32).
        stride : int
            Stride in bytes (0 for tightly packed).
        """
        loc = self._prog.attributeLocation(name)
        if loc < 0:
            return
        arr = np.ascontiguousarray(data, dtype=np.float32)
        if arr.ndim == 1:
            arr = arr.reshape(-1, 1)
        vbo = self._buffers.get(name)
        if vbo is None:
            vbo = int(GL.glGenBuffers(1))
            self._buffers[name] = vbo
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, arr.nbytes, arr, GL.GL_DYNAMIC_DRAW)
        GL.glEnableVertexAttribArray(loc)
        GL.glVertexAttribPointer(
            loc, int(arr.shape[1]), GL.GL_FLOAT, GL.GL_FALSE, int(stride),
            ctypes.c_void_p(0))
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)

    def disable_attribute(self, name: str) -> None:
        """Disable a vertex attribute array."""
        loc = self._prog.attributeLocation(name)
        if loc >= 0:
            GL.glDisableVertexAttribArray(loc)

    @property
    def handle(self):
        """The underlying QOpenGLShaderProgram (escape hatch)."""
        return self._prog


# ---------------------------------------------------------------------------
# View transform (Qt-free)
# ---------------------------------------------------------------------------

class ViewTransform:
    """Maps data coordinates to OpenGL clip space ``[-1, 1]``.

    Parameters
    ----------
    x_range, y_range : tuple of float
        Visible ``(min, max)`` in data units.
    log_x, log_y : bool
        Whether the axis is logarithmic.
    """

    def __init__(
        self,
        x_range: tuple[float, float] = (0.0, 1.0),
        y_range: tuple[float, float] = (0.0, 1.0),
        *,
        log_x: bool = False,
        log_y: bool = False,
    ):
        self.x_range = list(x_range)
        self.y_range = list(y_range)
        self.log_x = log_x
        self.log_y = log_y

    def data_to_ndc(self, x: float, y: float) -> tuple[float, float]:
        """Map one data point to normalised device coordinates."""
        return (
            self._normalize(x, self.x_range[0], self.x_range[1], self.log_x),
            self._normalize(y, self.y_range[0], self.y_range[1], self.log_y),
        )

    @staticmethod
    def _normalize(value: float, lo: float, hi: float, log: bool) -> float:
        t = ViewTransform._param(value, lo, hi, log)
        return 2.0 * t - 1.0

    @staticmethod
    def _param(value: float, lo: float, hi: float, log: bool) -> float:
        if log:
            v = max(value, 1e-10)
            llo = math.log10(max(lo, 1e-10))
            lhi = math.log10(max(hi, 1e-10))
            return (math.log10(v) - llo) / max(lhi - llo, 1e-12)
        return (value - lo) / max(hi - lo, 1e-12)

    def transform_array(self, xs: np.ndarray, ys: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Vectorised data-to-NDC transform for arrays."""
        nx = self._norm_arr(xs, self.x_range[0], self.x_range[1], self.log_x)
        ny = self._norm_arr(ys, self.y_range[0], self.y_range[1], self.log_y)
        return nx, ny

    @staticmethod
    def _norm_arr(arr, lo, hi, log):
        if log:
            a = np.log10(np.maximum(arr, 1e-10))
            llo = math.log10(max(lo, 1e-10))
            lhi = math.log10(max(hi, 1e-10))
        else:
            a = arr.astype(np.float64)
            llo, lhi = lo, hi
        return 2.0 * (a - llo) / max(lhi - llo, 1e-12) - 1.0


# ---------------------------------------------------------------------------
# Nice tick calculation (Qt-free)
# ---------------------------------------------------------------------------

def nice_ticks(lo: float, hi: float, target: int = 8) -> list[float]:
    """Return a list of nice round tick positions spanning ``[lo, hi]``."""
    if lo == hi:
        hi = lo + 1.0
    span = hi - lo
    raw_step = span / max(target, 1)
    mag = 10.0 ** math.floor(math.log10(raw_step))
    normalized = raw_step / mag
    if normalized < 1.5:
        step = 1.0 * mag
    elif normalized < 3.0:
        step = 2.0 * mag
    elif normalized < 7.0:
        step = 5.0 * mag
    else:
        step = 10.0 * mag
    start = math.ceil(lo / step) * step
    ticks = []
    v = start
    while v <= hi + step * 0.001:
        ticks.append(v)
        v += step
    return ticks


def format_tick(value: float, step: float) -> str:
    """Format a tick label with appropriate precision."""
    if step == 0:
        decimals = 6
    elif step >= 1:
        decimals = max(0, -int(math.floor(math.log10(step))))
    else:
        decimals = max(0, -int(math.floor(math.log10(step))))
    if abs(value) >= 1e4 or (abs(value) < 1e-3 and value != 0):
        return f"{value:.1e}"
    return f"{value:.{min(decimals, 6)}f}"
