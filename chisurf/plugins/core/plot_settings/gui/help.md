# Plot Settings

Configures how every chiplot panel in the application looks: which rendering
backend draws the plots, the colour palette curves and data take, the
appearance details (fonts, grid, background), and the advanced pyqtgraph
options for the panels that run on that engine.

Settings are grouped into collapsible sections so the common controls are
visible first and the specialist ones fold away. A **live preview** plot at
the bottom of the window re-renders as you change settings, so an effect is
seen before it is applied to the working panels.

## Backend

The backend decides *how* a plot is drawn, not *what* is in it. The pyqtgraph
engine is the default; the native renderers (wgpu, OpenGL) draw the same data
through shaders. Switching backend changes every open panel — the preview
shows the switch before you commit to it.

## Colours and appearance

The palette applies to newly drawn curves; existing fits keep the colours they
were drawn with until they are re-plotted. Appearance settings (fonts, grid
lines, background) apply immediately to every panel.

## Advanced pyqtgraph section

Options that only exist on the pyqtgraph engine — anti-aliasing, downsampling
mode, the SI-prefix and legend behaviours. They are inert when a native
backend is selected, which is why they fold away in their own section.

Press **Guide** for the walk-through.
