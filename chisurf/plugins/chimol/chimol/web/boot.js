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

  const at = (event) => {
    const box = canvas.getBoundingClientRect();
    const ratio = canvas.width / box.width;
    return [(event.clientX - box.left) * ratio, (event.clientY - box.top) * ratio];
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
