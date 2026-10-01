# Plot Settings

Configures how every chiplot panel in the application looks: which rendering
backend draws the plots, the colour palette curves and data take, the
appearance details (fonts, grid, background), and the advanced pyqtgraph
options for the panels that run on that engine.

Settings are grouped into collapsible sections so the common controls are
visible first and the specialist ones fold away. A **preview** plot at the
bottom of the window draws three *sample* curves (data, model, instrument
response — they preview the styling and are not your data) and re-renders as you
change settings, so an effect is seen before it is applied to the working panels.

Edits are *pending* until you press a button: **Apply** writes them into the
active settings (new plots use them, open node graphs are re-styled), **Save**
applies and also writes `settings_chisurf.yaml`, and **Reset** reloads every
control from the active settings and drops edits you did not apply. The status
line under the buttons says whether edits are waiting.

## Backend

The backend decides *how* a plot is drawn, not *what* is in it. The emtk
renderer is the default and pyqtgraph stays selectable for the plot families
emtk does not draw yet. A changed backend applies on the next application start
or when a new plot is created.

## Colours and appearance

Click a colour swatch to open a colour picker, or type a hex value. The palette
applies to newly drawn curves; existing fits keep the colours they were drawn
with until they are re-plotted. The preview shows the pending colours, line
width, grid, axis labels and legend before you apply them.

## Node graphs

The grid under a node graph — Global View, the light path, the provenance
inspector, the node editor — is a background, not a workspace, so it has its
own width and opacity here, quieter than a plot grid. A width below one pixel
fades the lines instead of narrowing them, which is what keeps the grid under
the edges drawn on top of it on a HiDPI screen. **Apply** also re-styles the
graph windows that are already open; the node-size entry is where a newly
opened Global View starts its own node-size control.

## Advanced pyqtgraph section

Options that only exist on the pyqtgraph engine — anti-aliasing, panning with
the left button, the background and foreground colours. They are inert when the
emtk backend is selected, which is why they fold away in their own section. The
preview follows the background (black, or white for `w` and `default`).

Press **Guide** for the walk-through.
