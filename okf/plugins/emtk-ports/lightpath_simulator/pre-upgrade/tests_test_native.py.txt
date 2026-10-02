"""Native graph actions, numerical backend and toolkit-free rendering."""
import numpy as np
from emtk import nodes
from chisurf.plugins.core.lightpath_simulator.gui.app import create_app


def test_constructor_preserves_initial_graph_positions():
    app=create_app()
    try:
        for node in app.controller.document.nodes:
            number=app.controller.document.node_number(node.id)
            assert nodes.get_node_grid_space_pos(app.graph_control.editor,number)==node.pos
    finally:
        app.close()


def test_native_graph_actions_and_preferences_roundtrip(tmp_path):
    from chisurf.plugins.core.lightpath_simulator.gui.controller import LightPathController
    state=tmp_path/'graph_state.json'
    controller=LightPathController(state_path=state)
    controller.auto_update=False
    try:
        source=controller.add_node('light_source',(100.,100.))
        detector=controller.add_node('detector',(400.,100.))
        assert controller.connect(source.id,0,detector.id,0)
        import pytest
        with pytest.raises(ValueError,match='already'):
            controller.connect(source.id,0,detector.id,0)
        controller.remove_node(source.id)
        assert not any(edge.source==source.id for edge in controller.document.edges)
        graph=tmp_path/'graph.json'
        controller.save_graph(graph)
        original=[(node.id,node.pos) for node in controller.document.nodes]
        controller.load_graph(graph)
        assert [(node.id,node.pos) for node in controller.document.nodes]==original
        easy=tmp_path/'preset.json'
        controller.save_preset(easy)
        assert easy.exists()
    finally:
        controller.close()
    restored=LightPathController(state_path=state)
    try:
        assert [(node.id,node.pos) for node in restored.document.nodes]==original
    finally:
        restored.close()


def test_real_native_simulation_mmfdb_export_and_populated_render(tmp_path,caplog):
    import json
    from emtk.testing import RecordingPainter
    from .test_headless import _build_probe_db,_dye_detector_graph
    from chisurf.plugins.core.lightpath_simulator.core.parameters import registered_lightpath_parameters
    db=tmp_path/'spectra.sqlite'
    dye,detector=_build_probe_db(db,'absorption')
    app=create_app(db_path=db)
    controller=app.controller
    controller.auto_update=False
    try:
        controller.load_document(_dye_detector_graph(dye,detector))
        controller.start('catalogue')
        controller._future.result(timeout=10)
        controller.poll()
        assert controller.probes and app.content.probes
        controller.start()
        controller._future.result(timeout=10)
        controller.poll()
        signals=controller.result['detector_signals']
        assert signals and signals[0]['intensity']>0
        assert controller.result['crosstalk_matrices']['excitation']['rows']==['488 nm']
        assert registered_lightpath_parameters() is controller.parameters
        app.draw(RecordingPainter(),0.,0.,1200.,800.)
        assert not [record for record in caplog.records if record.levelno>=40]
        instrument=tmp_path/'instrument.json'
        controller.export_instrument(instrument)
        assert json.loads(instrument.read_text())
        controller.start('save')
        controller._future.result(timeout=10)
        controller.poll()
        saved=controller.last_operation_id
        assert saved
        controller.start('list')
        controller._future.result(timeout=10)
        controller.poll()
        assert saved in [record['operation_id'] for record in controller.saved]
        controller.start('get',saved)
        controller._future.result(timeout=10)
        controller.poll()
        assert controller.result['detector_signals']==signals
    finally:
        app.close()
    assert registered_lightpath_parameters() is None


def test_easy_mode_updates_parameters_without_losing_layout():
    from chisurf.core.optical_configuration import _graph_to_config
    app=create_app()
    app.controller.auto_update=False
    try:
        ids=[node.id for node in app.controller.document.nodes]
        positions=[node.pos for node in app.controller.document.nodes]
        config=_graph_to_config(app.controller.graph())
        config['lasers']='488:0.5, 640:1.0'
        app.controller.apply_easy(config)
        assert [node.id for node in app.controller.document.nodes]==ids
        assert [node.pos for node in app.controller.document.nodes]==positions
        laser=next(node for node in app.controller.document.nodes if node.type=='light_source')
        assert laser.config['manual_lines']=='488:0.5, 640:1.0'
    finally:
        app.close()


def test_manual_line_node_edits_preserve_relative_powers(monkeypatch):
    from chisurf.emtk.node_editor.document import GraphNode
    from chisurf.plugins.core.lightpath_simulator.gui.emtk_view import BeampathContent
    from chisurf.plugins.core.lightpath_simulator.backend.crosstalk import propagate_node
    from unittest.mock import MagicMock
    node=GraphNode('laser','light_source',config={'source_mode':'manual','manual_lines':'488:0.5, 640:1.0'})
    values=[]
    def input_text(label,value):
        values.append(value)
        return True,'488:0.25, 640:0.75'
    monkeypatch.setattr('chisurf.plugins.core.lightpath_simulator.gui.emtk_view.im',MagicMock(input_text=input_text,combo=lambda *a:(False,0)))
    assert BeampathContent()._draw_light_source(node,False)
    assert values==['488:0.5, 640:1.0']
    assert node.config['manual_lines']=='488:0.25, 640:0.75'
    spectra,_=propagate_node('light_source',node.config,{},None)
    assert np.isclose(np.sum(spectra['Light']['488 nm'])/np.sum(spectra['Light']['640 nm']),1/3)


def test_easy_edits_preserve_custom_nodes_and_connections():
    from chisurf.core.optical_configuration import _graph_to_config
    controller=__import__('chisurf.plugins.core.lightpath_simulator.gui.controller',fromlist=['LightPathController']).LightPathController()
    controller.auto_update=False
    try:
        custom=controller.add_node('combiner',(750.,800.))
        custom.config['custom_metadata']={'retain':True}
        edges=[edge.key() for edge in controller.document.edges]
        config=_graph_to_config(controller.graph())
        config['lasers']='488:0.8'
        controller.apply_easy(config)
        assert controller.document.node(custom.id) is custom
        assert custom.config['custom_metadata']=={'retain':True}
        assert [edge.key() for edge in controller.document.edges]==edges
    finally:
        controller.close()


def test_native_rpc_client_uses_original_service_dispatcher(tmp_path):
    from chisurf.core.plugin.client import InProcessClient
    from chisurf.server.dispatcher import ServiceDispatcher
    from chisurf.server.session import SessionState
    from chisurf.plugins.core.lightpath_simulator.api.client import LightPathClient
    from chisurf.plugins.core.lightpath_simulator.rpc.services import register_services
    from .test_headless import _build_probe_db,_dye_detector_graph
    db=tmp_path/'rpc_spectra.sqlite'
    dye,detector=_build_probe_db(db,'absorption')
    dispatcher=ServiceDispatcher(SessionState())
    register_services(dispatcher)
    app=create_app(db_path=db,client=LightPathClient(InProcessClient(dispatcher)))
    app.controller.auto_update=False
    try:
        app.controller.load_document(_dye_detector_graph(dye,detector))
        app.controller.start()
        app.controller._future.result(timeout=10)
        app.controller.poll()
        assert app.controller.result['detector_signals'][0]['intensity']>0
        app.controller.start('save')
        app.controller._future.result(timeout=10)
        app.controller.poll()
        assert app.controller.last_operation_id
    finally:
        app.close()


def test_rpc_factory_respects_canonical_connection_profile(monkeypatch):
    from types import SimpleNamespace
    import chisurf.core.settings as settings
    from chisurf.plugins.core.lightpath_simulator.api.client import LightPathClient
    calls=[]
    client=SimpleNamespace(host='configured-profile',cmd_port=1234,pub_port=1235,token=None)
    def make_client(**kwargs):
        calls.append(kwargs)
        return client
    monkeypatch.setattr('chisurf.plugins.core.mmfdb_admin.gui.client.MMFDBClient',make_client)
    monkeypatch.setattr('chisurf.plugins.core.mmfdb_admin.gui.session.cached_token',lambda *a:None)
    monkeypatch.setattr('mmfdb.security.credentials.load_runtime_session_token',lambda *a:None)
    monkeypatch.setattr('mmfdb.security.credentials.load_session_token',lambda *a:None)
    monkeypatch.setitem(settings.cs_settings,'mmfdb',{'last_server':'old-profile','client':{'host':'configured-profile','cmd_port':1234,'pub_port':1235,'username':'current-user'}})
    wrapped=LightPathClient.from_settings(timeout_ms=25)
    assert wrapped.client is client
    assert calls==[{'timeout_ms':25}]


def test_cancel_preserves_previous_simulation_result(monkeypatch):
    import threading
    from concurrent.futures import CancelledError
    from chisurf.plugins.core.lightpath_simulator.gui.controller import LightPathController
    controller=LightPathController()
    controller.auto_update=False
    previous={'detector_signals':[{'intensity':1.}]}
    controller.result=previous
    started,release=threading.Event(),threading.Event()
    def backend(*args):
        started.set()
        assert release.wait(5)
        return {'detector_signals':[{'intensity':2.}]}
    monkeypatch.setattr(controller,'_backend',backend)
    try:
        controller.start()
        assert started.wait(5)
        controller.stop()
        release.set()
        try:controller._future.result(timeout=5)
        except CancelledError:pass
        controller.poll()
        assert controller.result is previous
        assert not controller.running
        assert 'cancelled' in controller.status
    finally:
        release.set()
        controller.close()


def test_real_backend_and_graph_render_stay_qt_free_in_clean_process():
    import subprocess,sys
    code='''
import sys,tempfile,logging
from pathlib import Path
import importlib.abc
class BlockQt(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in {'qtpy','PyQt5','PyQt6','PySide2','PySide6','pyqtgraph'}:
            raise ImportError('Qt dependency: '+fullname)
sys.meta_path.insert(0,BlockQt())
from chisurf.plugins.core.lightpath_simulator.tests.test_headless import _build_probe_db,_dye_detector_graph
from chisurf.plugins.core.lightpath_simulator.gui.app import create_app
from emtk.testing import RecordingPainter
class Errors(logging.Handler):
    def emit(self,record):
        if record.levelno>=40:raise AssertionError(record.getMessage())
logging.getLogger().addHandler(Errors())
with tempfile.TemporaryDirectory() as directory:
    db=Path(directory)/'spectra.sqlite'
    dye,detector=_build_probe_db(db,'absorption')
    app=create_app(db_path=db)
    app.controller.auto_update=False
    try:
        app.controller.load_document(_dye_detector_graph(dye,detector))
        app.controller.start()
        app.controller._future.result(timeout=10)
        app.controller.poll()
        assert app.controller.result['detector_signals'][0]['intensity']>0
        app.draw(RecordingPainter(),0.,0.,1000.,700.)
    finally:app.close()
qt=[key for key in sys.modules if key.startswith(('qtpy','PyQt','PySide'))]
assert not qt,qt
'''
    result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr


def test_populated_catalogue_choosers_display_assigned_components(tmp_path,monkeypatch):
    from .test_headless import _build_probe_db,_dye_detector_graph
    from chisurf.plugins.core.lightpath_simulator.core.workflow import get_probes_info
    from chisurf.plugins.core.lightpath_simulator.gui.emtk_view import BeampathContent
    from chisurf.emtk.node_editor.document import GraphDocument
    from unittest.mock import MagicMock
    db=tmp_path/'chooser.sqlite'
    dye,detector=_build_probe_db(db,'absorption')
    content=BeampathContent(get_probes_info(str(db))['probes'])
    assert detector in [value for label,value in content.choices('detector')]
    document=GraphDocument.from_dict(_dye_detector_graph(dye,detector))
    sample=next(node for node in document.nodes if node.type=='sample')
    chosen=[]
    def combo(label,index,labels):
        chosen.append(labels[index])
        return False,index
    monkeypatch.setattr('chisurf.plugins.core.lightpath_simulator.gui.emtk_view.im',MagicMock(combo=combo))
    content._draw_probe_chooser(sample,False)
    assert chosen==['MMFDB Dye']
