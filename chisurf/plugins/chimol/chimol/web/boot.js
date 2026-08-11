// Load chimol into the page. This file draws nothing.
//
// There is no JavaScript renderer and there must not be one: chimol's engine is
// eighteen WGSL shaders and the Python that hands them to a driver, and a second
// copy of that in JavaScript would have to grow its own ray tracer, its own BVH
// build and its own marching cubes to keep up. So this is a *loader* -- it
// starts Pyodide, puts the package on its filesystem, resolves the GPU device,
// and hands the canvas over. Every frame after that is Python calling WebGPU.
//
// A guard test fails if this file ever contains `createRenderPipeline`,
// `createBuffer` or `beginRenderPass`.
//
// The only thing here that is not plumbing is the *async* handover. WebGPU's
// `requestAdapter` and `requestDevice` return promises; everything after them is
// synchronous, because command recording is. Resolving both before the engine
// starts is what keeps `await` out of the engine -- otherwise every call site
// would have to become a coroutine on the desktop too, for a wait the desktop
// does not have.

const status = (message) => {
  const el = document.getElementById("status");
  if (el) el.textContent = message;
  console.log("[chimol]", message);
};

async function boot() {
  const canvas = document.getElementById("view");
  canvas.width = canvas.clientWidth * (window.devicePixelRatio || 1);
  canvas.height = canvas.clientHeight * (window.devicePixelRatio || 1);

  if (!navigator.gpu) {
    status("this browser has no WebGPU (navigator.gpu is undefined)");
    return;
  }

  status("loading Pyodide…");
  const pyodide = await loadPyodide();

  // numpy for the engine's arrays, Pillow for one image: the glyph atlas.
  // The browser has its own PNG decoder, but `createImageBitmap` is async and
  // the engine uploads the atlas from synchronous code -- so it reads it the
  // same way the desktop does, and the page pays for the decoder up front.
  status("loading numpy and Pillow…");
  await pyodide.loadPackage(["numpy", "Pillow"]);

  status("fetching chimol…");
  const response = await fetch("chimol.zip");
  if (!response.ok) throw new Error(`chimol.zip: ${response.status}`);
  const zip = await response.arrayBuffer();
  pyodide.unpackArchive(zip, "zip", { extractDir: "/chimol_pkg" });
  pyodide.runPython(`import sys; sys.path.insert(0, "/chimol_pkg")`);

  status("requesting a GPU device…");
  // Both promises resolve here, before any engine code runs.
  const adapter = await pyodide.runPythonAsync(`
from chimol.renderer.gpu import browser
adapter = await browser.request_adapter_async()
await adapter.request_device_async()
adapter
`);
  void adapter;

  status("reading 148l.pdb and building the scene…");
  globalThis.chimolCanvas = canvas;
  const viewer = pyodide.runPython(`
import js
from chimol.web import demo

viewer = demo.Viewer(js.chimolCanvas)
viewer.draw()
viewer
`);

  // Interaction. Every handler asks Python what the event *meant* -- the panel
  // decides whether a click landed on one of its buttons, and the camera owns
  // the trackball -- and redraws only when Python says something changed. The
  // browser contributes coordinates and a modifier mask; it decides nothing.
  const modifiersOf = (event) =>
    (event.shiftKey ? 0x02000000 : 0) |
    (event.ctrlKey ? 0x04000000 : 0) |
    (event.altKey ? 0x08000000 : 0) |
    (event.metaKey ? 0x10000000 : 0);

  // CSS pixels, not device ones. The panel is laid out in CSS pixels and
  // hit-tests in them, exactly as the desktop does with logical pixels -- a
  // pointer converted to device pixels would miss every control by the display
  // ratio.
  const at = (event) => {
    const box = canvas.getBoundingClientRect();
    return [event.clientX - box.left, event.clientY - box.top];
  };

  let frame = null;
  const redraw = () => {
    if (frame !== null) return;
    frame = requestAnimationFrame(() => {
      frame = null;
      viewer.draw();
    });
  };

  canvas.addEventListener("pointerdown", (event) => {
    canvas.setPointerCapture(event.pointerId);
    const [x, y] = at(event);
    if (viewer.press(x, y, event.button, modifiersOf(event))) redraw();
    event.preventDefault();
  });
  canvas.addEventListener("pointermove", (event) => {
    const [x, y] = at(event);
    if (viewer.move(x, y)) redraw();
  });
  const end = (event) => {
    viewer.release();
    redraw();
    if (canvas.hasPointerCapture(event.pointerId)) {
      canvas.releasePointerCapture(event.pointerId);
    }
  };
  canvas.addEventListener("pointerup", end);
  canvas.addEventListener("pointercancel", end);
  canvas.addEventListener("wheel", (event) => {
    if (viewer.wheel(event.deltaY > 0 ? 1 : -1)) redraw();
    event.preventDefault();
  }, { passive: false });
  // A right-click is a chimol gesture, not a place for the browser's menu.
  canvas.addEventListener("contextmenu", (event) => event.preventDefault());

  // Typing. The command line is drawn in the viewport by the same engine that
  // draws the panel, so the page's whole job is to name the key and say what
  // was typed -- `KeyboardEvent.key` plus the four modifier flags -- and let
  // Python decide whether anything wanted it.
  //
  // On `window`, not on the canvas: a canvas takes keyboard focus only with a
  // `tabindex` and a click, and a viewer you have to click before you can type
  // is a viewer whose prompt looks broken. Anything typed into a real form
  // control on the page is left alone.
  window.addEventListener("keydown", (event) => {
    const tag = (event.target && event.target.tagName) || "";
    if (tag === "INPUT" || tag === "TEXTAREA" || event.target?.isContentEditable) {
      return;
    }
    // A browser shortcut stays a browser shortcut: ctrl/cmd combinations are
    // offered to the engine, which takes only the handful of line-editing ones
    // and leaves reload, find and the console alone.
    const consumed = viewer.key(
      event.key,
      event.key.length === 1 ? event.key : "",
      event.ctrlKey,
      event.shiftKey,
      event.altKey,
      event.metaKey,
    );
    if (consumed) {
      // Only when consumed: Tab must still move focus, and space must still
      // scroll, on a page where nothing is being typed.
      event.preventDefault();
      redraw();
    }
  });

  globalThis.chimolViewer = viewer;
  status("drawn — drag to rotate, wheel to zoom, click the panel");
}

boot().catch((error) => {
  // Kept whole on `window` as well as logged. A Python traceback that crosses
  // into the console is truncated, and the useful line is the innermost one.
  globalThis.chimolError = String((error && error.stack) || error);
  status(`failed: ${error}`);
  console.error(error);
});
