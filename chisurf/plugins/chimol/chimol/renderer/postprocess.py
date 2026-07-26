"""Render-to-texture scaffolding, and the silhouette pass built on it.

ChiMOL drew straight to the default framebuffer, which rules out every effect
that needs to *read* the scene back: silhouettes, ambient occlusion from shadow
maps, depth cue. Those are the axis on which the viewer beats PyMOL, so the
scaffolding is built once here and each effect becomes a small pass over it.

What it does
------------
``begin`` binds an offscreen framebuffer carrying a colour **and a depth
texture**; the scene renders into it unchanged. ``end`` puts the colour back on
screen with a full-screen quad and then runs the effect passes, which sample the
depth texture.

Two details that are specific to this setting and cost time if rediscovered:

* **the depth attachment has to be a texture, not a renderbuffer.** Qt's
  ``QOpenGLFramebufferObject`` gives a depth *renderbuffer*, which cannot be
  sampled, so the framebuffer is built by hand;
* **"the screen" is not framebuffer 0.** ``QOpenGLWidget`` renders into its own
  framebuffer and composites it, so the target to return to is
  ``defaultFramebufferObject()``. Binding 0 draws into nothing visible.

The silhouette algorithm
------------------------
Transcribed from ChimeraX's ``USE_DEPTH_OUTLINE`` shader
(``graphics/src/fragmentShader.txt``) and ``Silhouette._draw_depth_outline``:
take the **minimum** depth over a disc around each fragment and draw where this
fragment sits far enough behind it. The factor that is not guessable is

    nf * (d0 - ds)  >=  jump * (1 - nf1*ds) * (1 - nf1*d0)

whose right-hand side **linearises the non-linear depth buffer**, so ``depth_jump``
is a fraction of *scene* depth rather than of buffer values. Without it an
outline is hairline near the camera and fat far away, and the setting means
nothing consistent. Under an orthographic projection ``nf == 1``, the correction
collapses to 1, and the test is a plain depth difference -- which is the case to
check first, because it is the one that can be reasoned about by hand.
"""

from __future__ import annotations

import numpy as np

try:  # pragma: no cover - exercised only with a real GL context
    from OpenGL import GL
except Exception:  # pragma: no cover
    GL = None


#: Shaders are **GLSL 120**, not 330. The widget's context is the legacy profile
#: -- macOS gives OpenGL 2.1 unless a core profile is requested explicitly, and
#: the main shader is `#version 120` -- so a 330 shader fails to compile with
#: "version '330' is not supported" and the whole effect silently falls back.
#: That means `attribute`/`varying` rather than `in`/`out`, `gl_FragColor`
#: rather than a named output, `texture2D` rather than `texture`, and no vertex
#: array objects.
_QUAD_VERTEX = """#version 120
attribute vec2 in_pos;
varying vec2 tex_coord;
void main() {
    tex_coord = in_pos * 0.5 + 0.5;
    gl_Position = vec4(in_pos, 0.0, 1.0);
}
"""

_COPY_FRAGMENT = """#version 120
varying vec2 tex_coord;
uniform sampler2D source;
void main() { gl_FragColor = texture2D(source, tex_coord); }
"""

#: The largest silhouette thickness the loop can express. GLSL 120 wants
#: constant loop bounds, so the disc is walked at a fixed size and the radius
#: test inside decides what counts -- which is also what keeps the cost
#: predictable rather than scaling with a user setting.
MAX_SILHOUETTE_THICKNESS = 4

#: The depth-outline pass. `jump` is (depth_jump, near/far ratio); `step_size`
#: is (dx, dy, thickness) in texture units and pixels.
_OUTLINE_FRAGMENT = """#version 120
varying vec2 tex_coord;
uniform sampler2D depth_tex;
uniform vec4 color;
uniform vec2 jump;
uniform vec3 step_size;
void main() {
    float d0 = texture2D(depth_tex, tex_coord).r;
    float ds = d0;
    float thickness = step_size.z;
    float r2 = thickness * thickness;
    for (int i = -%(max)d; i <= %(max)d; ++i) {
        for (int j = -%(max)d; j <= %(max)d; ++j) {
            float fi = float(i);
            float fj = float(j);
            if (fi * fi + fj * fj <= r2 && !(i == 0 && j == 0)) {
                ds = min(ds, texture2D(depth_tex,
                    vec2(tex_coord.s + fi * step_size.x,
                         tex_coord.t + fj * step_size.y)).r);
            }
        }
    }
    // Linearise the depth buffer so `jump` is a fraction of scene depth.
    float nf = jump.y;
    float nf1 = 1.0 - nf;
    if (nf * (d0 - ds) < jump.x * (1.0 - nf1 * ds) * (1.0 - nf1 * d0)) {
        discard;
    }
    gl_FragColor = color;
}
""" % {"max": MAX_SILHOUETTE_THICKNESS}


class PostProcess:
    """An offscreen colour+depth target and the passes that read it.

    Every method is a no-op when the framebuffer could not be created, so a
    driver that refuses it degrades to the direct rendering that came before
    rather than to a black window.
    """

    def __init__(self) -> None:
        self._fbo = 0
        self._colour_tex = 0
        self._depth_tex = 0
        self._size = (0, 0)
        self._quad_vao = 0
        self._quad_vbo = 0
        self._copy_program = 0
        self._outline_program = 0
        self._failed = False

        #: Silhouette settings, named as ChimeraX names them.
        self.silhouette = False
        self.silhouette_thickness = 1.0
        self.silhouette_color = (0.0, 0.0, 0.0, 1.0)
        self.depth_jump = 0.03
        #: 1.0 for an orthographic projection, where the correction collapses.
        self.near_far_ratio = 1.0

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    @property
    def available(self) -> bool:
        """Whether the offscreen target is usable."""
        return bool(GL is not None and self._fbo and not self._failed)

    def wanted(self) -> bool:
        """Whether any effect currently needs the offscreen pass.

        With nothing enabled the scene is drawn directly, so the scaffolding
        costs nothing when it is not being used.
        """
        return bool(self.silhouette)

    def ensure(self, width: int, height: int) -> bool:
        """Create or resize the offscreen target. False when unavailable."""
        if GL is None or self._failed:
            return False
        width = max(1, int(width))
        height = max(1, int(height))
        if self._fbo and self._size == (width, height):
            return True
        try:
            self._release_target()
            self._create_target(width, height)
            self._ensure_programs()
        except Exception as exc:
            # A driver that will not give a sampleable depth texture is a
            # reason to fall back, not to fail: the scene still renders. Say why
            # once, so a silent fallback is not mistaken for the effect being off.
            import logging

            logging.getLogger(__name__).warning(
                "chimol: offscreen render target unavailable, effects disabled (%s)",
                exc,
            )
            self._failed = True
            self._release_target()
            return False
        return bool(self._fbo)

    def _create_target(self, width: int, height: int) -> None:
        self._colour_tex = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self._colour_tex)
        GL.glTexImage2D(
            GL.GL_TEXTURE_2D, 0, GL.GL_RGBA8, width, height, 0,
            GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, None,
        )
        for name, value in (
            (GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR),
            (GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR),
            (GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE),
            (GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE),
        ):
            GL.glTexParameteri(GL.GL_TEXTURE_2D, name, value)

        self._depth_tex = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self._depth_tex)
        GL.glTexImage2D(
            GL.GL_TEXTURE_2D, 0, GL.GL_DEPTH_COMPONENT24, width, height, 0,
            GL.GL_DEPTH_COMPONENT, GL.GL_FLOAT, None,
        )
        for name, value in (
            (GL.GL_TEXTURE_MIN_FILTER, GL.GL_NEAREST),
            (GL.GL_TEXTURE_MAG_FILTER, GL.GL_NEAREST),
            (GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE),
            (GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE),
        ):
            GL.glTexParameteri(GL.GL_TEXTURE_2D, name, value)
        GL.glBindTexture(GL.GL_TEXTURE_2D, 0)

        self._fbo = GL.glGenFramebuffers(1)
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self._fbo)
        GL.glFramebufferTexture2D(
            GL.GL_FRAMEBUFFER, GL.GL_COLOR_ATTACHMENT0,
            GL.GL_TEXTURE_2D, self._colour_tex, 0,
        )
        GL.glFramebufferTexture2D(
            GL.GL_FRAMEBUFFER, GL.GL_DEPTH_ATTACHMENT,
            GL.GL_TEXTURE_2D, self._depth_tex, 0,
        )
        status = GL.glCheckFramebufferStatus(GL.GL_FRAMEBUFFER)
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, 0)
        if status != GL.GL_FRAMEBUFFER_COMPLETE:
            raise RuntimeError(f"incomplete framebuffer: {status}")
        self._size = (width, height)

    def _release_target(self) -> None:
        if GL is None:
            return
        try:
            if self._fbo:
                GL.glDeleteFramebuffers(1, [self._fbo])
            if self._colour_tex:
                GL.glDeleteTextures(1, [self._colour_tex])
            if self._depth_tex:
                GL.glDeleteTextures(1, [self._depth_tex])
        except Exception:
            pass
        self._fbo = self._colour_tex = self._depth_tex = 0
        self._size = (0, 0)

    # ------------------------------------------------------------------ #
    # Shader helpers
    # ------------------------------------------------------------------ #
    def _ensure_programs(self) -> None:
        if not self._copy_program:
            self._copy_program = _compile(_QUAD_VERTEX, _COPY_FRAGMENT)
        if not self._outline_program:
            self._outline_program = _compile(_QUAD_VERTEX, _OUTLINE_FRAGMENT)
        if not self._quad_vbo:
            self._quad_vao, self._quad_vbo = _make_quad()

    # ------------------------------------------------------------------ #
    # The passes
    # ------------------------------------------------------------------ #
    def begin(self, width: int, height: int) -> bool:
        """Bind the offscreen target. False means "render normally"."""
        if not self.wanted() or not self.ensure(width, height):
            return False
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self._fbo)
        GL.glViewport(0, 0, *self._size)
        return True

    def end(self, default_fbo: int) -> None:
        """Put the scene back on screen and run the effect passes."""
        if not self.available:
            return
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, int(default_fbo))
        GL.glViewport(0, 0, *self._size)

        # The scene, as a full-screen quad. Depth testing and blending off: this
        # is a copy, and leaving depth on would test the copy against a buffer
        # that no longer holds the scene's depth.
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glDisable(GL.GL_BLEND)
        GL.glDisable(GL.GL_CULL_FACE)
        self._draw_quad(self._copy_program, {"source": self._colour_tex})

        if self.silhouette:
            GL.glEnable(GL.GL_BLEND)
            GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
            self._draw_outline()
            GL.glDisable(GL.GL_BLEND)

        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glEnable(GL.GL_CULL_FACE)

    def _draw_outline(self) -> None:
        width, height = self._size
        GL.glUseProgram(self._outline_program)
        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self._depth_tex)
        GL.glUniform1i(
            GL.glGetUniformLocation(self._outline_program, "depth_tex"), 0
        )
        GL.glUniform4f(
            GL.glGetUniformLocation(self._outline_program, "color"),
            *[float(c) for c in self.silhouette_color],
        )
        GL.glUniform2f(
            GL.glGetUniformLocation(self._outline_program, "jump"),
            float(self.depth_jump), float(self.near_far_ratio),
        )
        GL.glUniform3f(
            GL.glGetUniformLocation(self._outline_program, "step_size"),
            1.0 / float(width), 1.0 / float(height),
            float(self.silhouette_thickness),
        )
        self._draw_strip(self._outline_program)
        GL.glUseProgram(0)

    def _draw_quad(self, program: int, textures: dict) -> None:
        GL.glUseProgram(program)
        for unit, (name, texture) in enumerate(textures.items()):
            GL.glActiveTexture(GL.GL_TEXTURE0 + unit)
            GL.glBindTexture(GL.GL_TEXTURE_2D, texture)
            GL.glUniform1i(GL.glGetUniformLocation(program, name), unit)
        self._draw_strip(program)
        GL.glUseProgram(0)

    def _draw_strip(self, program: int) -> None:
        """Bind the quad and draw it, setting the attribute pointer each time."""
        location = GL.glGetAttribLocation(program, "in_pos")
        if location < 0:
            return
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._quad_vbo)
        GL.glEnableVertexAttribArray(location)
        GL.glVertexAttribPointer(location, 2, GL.GL_FLOAT, GL.GL_FALSE, 0, None)
        GL.glDrawArrays(GL.GL_TRIANGLE_STRIP, 0, 4)
        GL.glDisableVertexAttribArray(location)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)

    def release(self) -> None:
        """Drop every GL object. Safe to call without a current context."""
        if GL is None:
            return
        self._release_target()
        try:
            for program in (self._copy_program, self._outline_program):
                if program:
                    GL.glDeleteProgram(program)
            if self._quad_vbo:
                GL.glDeleteBuffers(1, [self._quad_vbo])
        except Exception:
            pass
        self._copy_program = self._outline_program = 0
        self._quad_vao = self._quad_vbo = 0


# --------------------------------------------------------------------------- #
# Small GL helpers
# --------------------------------------------------------------------------- #
def _compile(vertex_source: str, fragment_source: str) -> int:
    """Compile and link one program, raising with the log on failure."""
    program = GL.glCreateProgram()
    shaders = []
    for stage, source in (
        (GL.GL_VERTEX_SHADER, vertex_source),
        (GL.GL_FRAGMENT_SHADER, fragment_source),
    ):
        shader = GL.glCreateShader(stage)
        GL.glShaderSource(shader, source)
        GL.glCompileShader(shader)
        if not GL.glGetShaderiv(shader, GL.GL_COMPILE_STATUS):
            log = GL.glGetShaderInfoLog(shader)
            raise RuntimeError(f"shader compile failed: {log}")
        GL.glAttachShader(program, shader)
        shaders.append(shader)
    GL.glLinkProgram(program)
    if not GL.glGetProgramiv(program, GL.GL_LINK_STATUS):
        raise RuntimeError(f"link failed: {GL.glGetProgramInfoLog(program)}")
    for shader in shaders:
        GL.glDeleteShader(shader)
    return int(program)


def _make_quad() -> tuple[int, int]:
    """A triangle strip covering clip space, for the full-screen passes.

    No vertex array object: a 2.1 context has none, so the attribute pointer is
    set at draw time instead. Returns ``(0, vbo)`` to keep the caller's shape.
    """
    vertices = np.array(
        [-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, 1.0, 1.0], dtype=np.float32
    )
    vbo = GL.glGenBuffers(1)
    GL.glBindBuffer(GL.GL_ARRAY_BUFFER, vbo)
    GL.glBufferData(
        GL.GL_ARRAY_BUFFER, vertices.nbytes, vertices, GL.GL_STATIC_DRAW
    )
    GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
    return 0, int(vbo)
