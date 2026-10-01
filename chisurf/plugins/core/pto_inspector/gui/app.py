"""Read-only native PTO inspection, with data and provenance kept in sync."""
from __future__ import annotations

import html
import re
from pathlib import Path

from emtk import im, implot, nodes
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog
from emtk.widgets.data_table import TableBinding, draw_table

from chisurf.core.datastore import column_names, column_values, write_csv_table
from chisurf.core.fio.pto import Measurement
from chisurf.emtk.dataset_picker import DatasetPicker, session_client
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.emtk.node_editor.control import GraphControl, NodeContentRenderer
from chisurf.emtk.node_editor.document import GraphDocument
from chisurf.emtk.plugins import load_plugin

from .translations import install, tr
from .view_model import PtoInspectorViewModel


VENDOR_SUFFIXES = {'.ptu', '.spc', '.ht3', '.ht2', '.pt3', '.pt2', '.h5', '.hdf5'}


class ProvenanceContent(NodeContentRenderer):
    def node_shape(self, node):
        return nodes.NodeShape.DISC, node.title, 21

    def node_style(self, node):
        return (*node.config.get('title_color', (70, 130, 175)), 255)

    def port_label(self, node, port, is_output):
        return ''

    def link_style(self, edge):
        return (140, 150, 160, 255), 1.5, True


class PtoInspectorApp(ImApp):
    window_title = 'PTO Inspector'
    window_size = (1200, 800)

    def __init__(self, model=None, tool_loader=None):
        install()
        self.model = model or PtoInspectorViewModel()
        self.tool_loader = tool_loader or load_plugin
        self.notice = ''
        self.dialog = None
        self.file_window = None
        self.file_action = ''
        self.payload = {}
        self.payload_columns = []
        self._payload_uid = None
        self._store = None
        self.tools = []
        self.tool_index = 0
        self.child = None
        self._opened_tools = []
        self.picker = None
        self.vendor_paths = []
        self.child_box = (0, 0, 0, 0)
        self.child_focus = False
        self.rects = {}
        self.graph = GraphControl(read_only=True, content=ProvenanceContent(), on_select=self.graph_selected)
        self.artifacts = TableBinding({'source': 'artifact_rows', 'columns': [
            {'key': key, 'label': tr(title), 'width': width, 'description': tr(title) + ': ' + tr(description)}
            for key, title, width, description in [
                ('name', 'Name', 120, 'Artifact label; UID is the unique identity.'),
                ('kind', 'Kind', 140, 'Dictionary artifact kind.'),
                ('operation', 'Operation', 170, 'Recorded operation; empty means carried data.'),
                ('grain', 'Grain', 70, 'What one table row represents.'),
                ('rows', 'Rows', 65, 'Number of stored rows.'),
                ('size', 'Size', 75, 'Stored payload size.'),
                ('parents', 'Parents', 60, 'Number of recorded parent artifacts.'),
            ]], 'selected_call': 'select_row', 'activated_call': 'open_row',
            'row_key': 'uid', 'filter': True, 'column_picker': True, 'min_column_width': 40, 'fit_columns': True, 'expand': True}, self.model)
        self.table = TableBinding({'source': 'payload', 'columns_source': 'payload_columns',
                                   'filter': True, 'column_picker': True, 'expand': True}, self)
        self.docks = DockManager(Split('h', .36, Region('container'),
                                      Split('v', .30, Region('provenance'), Split('v', .32, Region('data'), Split('v', .53, Region('curve'), Region('details'))))))
        self.docks.add_window('container', tr('Container'), self.container_view, dock='container', closable=False)
        self.docks.add_window('provenance', tr('Provenance'), self.provenance_view, dock='provenance', closable=False)
        for key, title, callback in [('data', 'Data', self.data_view), ('curve', 'Curve', self.curve_view),
                                     ('details', 'Details', self.details_view), ('lineage', 'Lineage', self.lineage_view),
                                     ('parameters', 'Parameters', self.parameters_view), ('text', 'Text', self.text_view)]:
            self.docks.add_window(key, tr(title), callback, dock=key if key in {'data', 'curve', 'details'} else 'details', closable=False)
        self.tour = EmTkGuidedTour(Path(__file__).with_name('guide_emtk.json'), get_target_rect=self.rects.get, owner=self,
                                   wait_for_controls=True)
        self.help = EmTkHelpWindow(tr('Help'), resource=Path(__file__).with_name('help_emtk.md'), owner=self,
                                  on_start_guide=self.tour.start)
        self.model.add_observer(self.changed)
        super().__init__(self.render, continuous=False)
        self.changed('opened')

    def changed(self, event):
        if event == 'open_tool':
            self.safe(self.open_tool)
            return
        if event == 'opened':
            if self.model.inspection is not None:
                self.tour.notify_used('filename')
            self.graph.set_document(GraphDocument.from_dict(self.model.provenance_graph() or {'nodes': [], 'edges': []}))
            self._payload_uid = None
        self.tools = self.model.tool_manifests()
        self.tool_index = 0
        selected = self.model.selected_uid
        self.artifacts.control.selected_key = selected or None
        if selected:
            node = self.graph.document.node(str(selected))
            if node:
                self.graph.editor.selected_nodes = {self.graph.document.node_number(node.id)}
        self.notice = ''

    def safe(self, fn):
        try:
            return fn()
        except Exception as exc:
            self.notice = tr('Error') + ': ' + str(exc)
            return None

    def button(self, title, tip, fn, enabled=True):
        im.begin_disabled(not enabled)
        if im.button(tr(title)):
            self.safe(fn)
            self.tour.notify_used(title)
        self.rects[title] = (*im.get_item_rect_min(), *im.get_item_rect_size())
        im.set_item_tooltip(tr(tip))
        im.end_disabled()

    def choose_file(self, action):
        self.file_action = action
        selected = self.model.selected
        self.dialog = FileDialog(tr('Open') if action == 'open' else tr('Export'),
                                 mode='open' if action == 'open' else 'save',
                                 filters='Photon containers (*.pto);;Photon files (*.ptu *.spc *.ht3 *.ht2 *.pt3 *.pt2 *.h5 *.hdf5);;All files (*)' if action == 'open' else
                                 'CSV (*.csv);;All files (*)' if selected and selected.is_tabular else 'All files (*)',
                                 directory=str(Path(self.model.filename).parent) if self.model.filename else None)
        if action != 'open' and selected:
            self.dialog.filename = selected.name + ('.csv' if selected.is_tabular else '')
        self.file_window = DialogWindow(tr('Open') if action == 'open' else tr('Export'), size=(780, 560))

    def choose_pack_directory(self):
        self.file_action = 'pack'
        self.dialog = FileDialog(tr('Choose container folder'), mode='folder',
                                 directory=str(Path(self.vendor_paths[0]).parent))
        self.file_window = DialogWindow(tr('Choose container folder'), size=(780, 560))

    def pack_vendor_files(self, directory):
        paths = list(self.vendor_paths)
        if not paths:
            return
        target = Path(directory) / (Path(paths[0]).stem + '.pto')
        if target.exists():
            raise FileExistsError(tr('A container already exists. Choose another folder.') + ' ' + str(target))
        with Measurement.create(paths, out_dir=directory) as measurement:
            target = measurement.path
        self.vendor_paths = []
        self.model.set_filename(str(target))

    def open_database(self):
        self.picker = DatasetPicker(client=session_client(), kinds=['raw_measurement', 'raw_data'],
                                    formats=['pto'], on_paths=self.on_paths_dropped)
        self.picker.open()

    def export_payload(self, path):
        selected = self.model.selected
        if not selected or not self.model.inspection:
            raise ValueError(tr('Select an artifact.'))
        if selected.is_tabular:
            store = self.model.current_store()
            if store is None:
                raise ValueError('Cannot read the selected table.')
            write_csv_table(str(path), store, delimiter=',')
        else:
            self.model.inspection.measurement.extract(selected.uid, str(path))
        self.notice = tr('Exported') + ': ' + str(path)

    def verify(self):
        # one status line: the verdict's lines (the mismatching objects) are joined
        self.notice = self.model.verify().replace('\n', ' ')

    def graph_selected(self, kind, node):
        if kind == 'node':
            self.model.select_node(node)

    def open_tool(self):
        if not self.tools:
            self.notice = tr('No tool for this operation.')
            return None
        manifest = self.tools[min(self.tool_index, len(self.tools) - 1)]
        if not getattr(manifest.entrypoints, 'emtk', ''):
            self.notice = tr('This tool has not been ported to EMTK yet.') + ' ' + manifest.id
            return None
        child = self.tool_loader(manifest.id)
        target = getattr(child, 'model', child)
        for setter in ('set_filename', 'set_path', 'load_file'):
            fn = getattr(target, setter, None)
            if callable(fn) and self.model.filename:
                fn(self.model.filename)
                break
        self.child = child
        self._opened_tools.append(child)
        return child

    def container_view(self, box):
        self.rects['Container'] = box
        available = im.get_content_region_avail()[0]
        used = 0
        for title, tip, fn, enabled in [
            ('Open', 'Open a photon container.', lambda: self.choose_file('open'), True),
            ('Database', 'Choose a container from MMFDB.', self.open_database, True),
            ('Reload', 'Read changes from disk.', self.model.reload, bool(self.model.filename)),
            ('Verify', 'Check every stored checksum.', self.verify, bool(self.model.inspection)),
            ('Export', 'Export the selected payload.', lambda: self.choose_file('export'), bool(self.model.selected)),
            ('Help', 'Read the inspector help.', lambda: setattr(self.help, 'open', True), True),
            ('Guide', 'Start the guided tour.', self.tour.start, True),
        ]:
            width = len(tr(title)) * 8 + 16
            if used and used + width < available:
                im.same_line()
            else:
                used = 0
            self.button(title, tip, fn, enabled)
            used += width
        im.text_wrapped(self.model.filename or tr('Open a photon container.'))
        im.set_item_tooltip(tr('Container path.'))
        self.rects['filename'] = (*im.get_item_rect_min(), *im.get_item_rect_size())
        im.separator()
        if self.model.inspection is None:
            im.text_wrapped(tr('No container open. Drop a .pto on this window, or press Open. A container holds one measurement: the instrument file verbatim, and every result computed from it beside it.'))
        else:
            self.prose(self.model.summary_html())
        im.separator()
        draw_table(self.artifacts, 'artifacts')
        self.rects['Objects'] = (*im.get_item_rect_min(), *im.get_item_rect_size())

    def provenance_view(self, box):
        self.rects['Provenance'] = box
        self.button('Fit graph', 'Frame all provenance nodes.', self.graph.fit)
        im.same_line()
        self.button('Open tool', 'Open the native tool for this operation.', self.open_tool, bool(self.tools))
        if len(self.tools) > 1:
            _, self.tool_index = im.combo('##tools', self.tool_index, [m.display_name or m.id for m in self.tools])
            im.set_item_tooltip(tr('Choose the tool to open.'))
        x, y = im.get_cursor_screen_pos()
        w, h = im.get_content_region_avail()
        if self.graph._box[2:] != (w, max(40, h)):
            self.graph.fit()
        self.graph._box = (x, y, w, max(40, h))
        self.graph.io = self.io
        self.graph._draw_graph(self.graph._box)
        hovered = nodes.is_node_hovered(self.graph.editor)
        if hovered is not None:
            node = self.graph.document.node_for_number(hovered)
            if node:
                tip = f'{node.title}\nUID: {node.id}\n{node.config.get("kind", "")}\n{node.config.get("operation", "")}'
                im.get_current_context().set_tooltip(tip, owner=('pto_node', node.id))
        inside = x <= self.io.mouse_pos[0] <= x + w and y <= self.io.mouse_pos[1] <= y + h
        if inside and hovered is None:
            im.get_current_context().set_tooltip(tr('Select a node; double-click to open its tool. Alt-drag pans; wheel zooms.'), owner='pto_graph')
        if hovered is not None and self.io.mouse_double_clicked[0] and x <= self.io.mouse_pos[0] <= x + w and y <= self.io.mouse_pos[1] <= y + h:
            self.safe(self.open_tool)

    def refresh_payload(self):
        if self._payload_uid == self.model.selected_uid:
            return
        self._payload_uid = self.model.selected_uid
        self._store = self.model.current_store()
        self.payload, self.payload_columns = {}, []
        if self._store is None:
            return
        for i, name in enumerate(column_names(self._store)):
            self.payload[name] = column_values(self._store, i)
            unit = Measurement.column_units(self._store, name)
            self.payload_columns.append({'key': name, 'title': f'{name} [{unit}]' if unit else name,
                                         'tooltip': f'{name}: {unit}' if unit else name, 'width': 130})

    def data_view(self, box):
        self.rects['Data'] = box
        self.safe(self.refresh_payload)
        if self._store is None:
            im.text_wrapped(tr('The selected artifact is not a table.') if self.model.inspection else tr('No container open.'))
        else:
            draw_table(self.table, 'payload')

    def curve_view(self, box):
        self.rects['Curve'] = box
        curves = self.model.curve_series()
        if not curves:
            im.text_wrapped(tr('The selected artifact is not a curve.') if self.model.inspection else tr('No container open.'))
            return
        axes = self.model.curve_axes()
        _, height = im.get_content_region_avail()
        if implot.begin_plot('##pto_curve', (-1, max(70, height - 4))):
            implot.setup_axes(axes['x_label'], axes['y_label'])
            if axes.get('log_x'):
                implot.setup_axis_scale(implot.AXIS_X1, implot.SCALE_LOG10)
            for series in curves:
                implot.plot_line(series['name'], series['x'], series['y'])
            implot.end_plot()
        im.set_item_tooltip(tr('Stored curve; axes include units.'))

    @staticmethod
    def prose(text):
        text = re.sub(r'</t[dh]>\s*<t[dh][^>]*>', ': ', text)
        text = re.sub(r'</(?:tr|p|pre)>', '\n', text)
        im.text_wrapped(html.unescape(re.sub('<[^>]+>', '', text)))

    def details_view(self, box):
        self.rects['Details'] = box
        self.prose(self.model.detail_html())

    def lineage_view(self, box):
        self.rects['Lineage'] = box
        im.text_wrapped(self.model.lineage_text() or tr('Select an artifact.'))

    def parameters_view(self, box):
        from ..core import settings_text
        item = self.model.selected
        im.text_wrapped(settings_text(item.settings) if item and item.settings else tr('No settings recorded.'))

    def text_view(self, box):
        im.text_wrapped(self.model.payload_text() or tr('No text payload.'))

    def draw(self, painter, x, y, w, h):
        self._painter = painter
        super().draw(painter, x, y, w, h)
        self._painter = None

    def render(self):
        vp = im.get_main_viewport()
        box = (*vp.pos, *vp.size)
        if self.child:
            im.set_next_window_pos((0, 0), im.Cond.ALWAYS)
            im.set_next_window_size((vp.size[0], 58), im.Cond.ALWAYS)
            if im.begin('Tool navigation', flags=im.WindowFlags.NO_TITLE_BAR):
                self.button('Back to inspector', 'Return to the container without closing the tool.', lambda: setattr(self, 'child', None))
            im.end()
            self.child_box = (0, 58, vp.size[0], vp.size[1] - 58)
            if self.child:
                self.draw_child(self._painter, self.child, *self.child_box, local_coordinates=True)
        else:
            self.docks.draw((box[0], box[1], box[2], max(80, box[3] - 28)))
            im.set_next_window_pos((0, box[3] - 28), im.Cond.ALWAYS)
            im.set_next_window_size((box[2], 28), im.Cond.ALWAYS)
            if im.begin('Status', flags=im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE):
                im.text_unformatted(self.notice or self.model.status)
            im.end()
        if self.vendor_paths and not self.dialog:
            im.set_next_window_pos((box[2] * .2, box[3] * .2), im.Cond.ALWAYS)
            im.set_next_window_size((box[2] * .6, 190), im.Cond.ALWAYS)
            if im.begin(tr('Pack instrument data')):
                im.text_wrapped(tr('Choose a folder for the new PTO container. Source files are preserved.'))
                im.text_wrapped('\n'.join(str(p) for p in self.vendor_paths))
                self.button('Choose container folder', 'Create a new container in the selected folder.', self.choose_pack_directory)
                im.same_line()
                self.button('Cancel', 'Cancel container creation.', lambda: setattr(self, 'vendor_paths', []))
                if self.notice:
                    im.text_wrapped(self.notice)
            im.end()
        if self.dialog:
            close = self.file_window.begin(box)
            selected = self.dialog.draw()
            self.file_window.end()
            if close or selected is False:
                self.dialog = None
            elif selected:
                action = self.file_action
                self.dialog = None
                self.safe(lambda: self.on_paths_dropped(selected) if action == 'open' else self.pack_vendor_files(selected[0]) if action == 'pack' else self.export_payload(selected[0]))
        if self.picker:
            self.picker.draw(box)
        self.help.draw(box)
        self.tour.draw(vp.size[0], vp.size[1])

    def pointer_press(self, x, y, button, modifiers=0, clicks=1):
        self.child_focus = bool(self.child and y >= 58)
        super().pointer_press(x, y, button, modifiers, clicks)
        if self.child_focus:
            self.child.pointer_press(x, y - 58, button, modifiers, clicks)
        elif not self.child and button == 1:
            gx, gy, gw, gh = self.graph._box
            if gx <= x < gx + gw and gy <= y < gy + gh:
                self.graph.io = self.io
                self.graph.press(x, y, gx, gy, gw, gh, modifiers=modifiers, clicks=clicks)

    def pointer_release(self, x, y, button, modifiers=0):
        super().pointer_release(x, y, button, modifiers)
        if self.child and self.child_focus:
            self.child.pointer_release(x, y - 58, button, modifiers)
        self.graph.release()

    def pointer_move(self, x, y, buttons=0, modifiers=0):
        super().pointer_move(x, y, buttons, modifiers)
        if self.child:
            self.child.pointer_move(x, y - 58, buttons, modifiers)
        elif self.graph._panning:
            self.graph.drag(x, y)

    def wheel(self, x, y, steps, modifiers=0):
        # Wheel routing: the old scroll(x, y, dx, dy) override rejected the
        # host's scroll(rows) call outright (TypeError on the first tick).
        super().wheel(x, y, steps, modifiers)
        if self.child and y >= 58:
            self.child.wheel(x, y - 58, steps, modifiers)

    def key(self, key, text='', modifiers=0):
        if self.child and self.child_focus:
            return self.child.key(key, text, modifiers)
        return super().key(key, text, modifiers)

    def on_paths_dropped(self, paths):
        """Open the first dropped .pto; dropped vendor files are offered for packing."""
        for path in paths:
            if str(path).lower().endswith('.pto'):
                self.model.set_filename(str(path))
                return True
        vendor = sorted([Path(p) for p in paths if Path(p).suffix.lower() in VENDOR_SUFFIXES], key=lambda p: p.name)
        if vendor:
            self.vendor_paths = vendor
            return True
        return False

    def files_dropped(self, paths):
        """Host hook: emtk's Qt host accepts a drag only when the control has this (or on_files_dropped)."""
        return bool(self.on_paths_dropped([str(p) for p in paths or []]))

    on_files_dropped = files_dropped

    def export_settings(self):
        return {'filename': self.model.filename, 'selected_uid': self.model.selected_uid,
                'artifact_filter': self.artifacts.control.filter.text}

    def restore_settings(self, state):
        path = state.get('filename', '')
        if path:
            self.model.set_filename(path)
            if self.model.inspection and self.model.inspection.info(state.get('selected_uid', 0)):
                self.model.select_uid(state['selected_uid'])
        self.artifacts.control.filter.set_text(state.get('artifact_filter', ''))

    def close(self):
        self.model.close()
        for child in self._opened_tools:
            close = getattr(child, "close", None)
            if close:
                close()
        self._opened_tools.clear()


def make_app():
    return PtoInspectorApp()
