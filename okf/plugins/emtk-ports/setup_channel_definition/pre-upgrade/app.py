"""Standalone native detector/PIE setup application."""
from emtk import im
from emtk.app import ImApp
from emtk.docking import DockManager, Region
from chisurf.emtk.channel_definition import ChannelDefinitionWidget


class SetupChannelDefinitionApp(ImApp):
    def __init__(self, settings=None, model=None, on_changed=None):
        if settings is None and model is None:
            settings = {'windows':{'prompt':[0,2048],'delayed':[2048,4095]},'detectors':{'green':{'chs':[8,0,3],'micro_time_ranges':[[0,4095]],'g_factor':1.,'l1':0.,'l2':0.},'red':{'chs':[9,1,2],'micro_time_ranges':[[0,2048]],'g_factor':1.,'l1':0.,'l2':0.},'yellow':{'chs':[9,1,2],'micro_time_ranges':[[2048,4095]],'g_factor':1.,'l1':0.,'l2':0.}},'tttr_reading':{'file_type':'SPC-130','macro_time_resolution':50.,'micro_time_resolution':50.,'micro_time_binning':1}}
        self.page = ChannelDefinitionWidget(settings,model=model,on_changed=on_changed)
        self.model = self.page.model
        self.docks = DockManager(Region('setup'),name='setup_channel_definition')
        self.docks.add_window('setup','Detector channels and PIE windows',lambda box:self.page.draw(),dock='setup')
        super().__init__(gui=self._render,continuous=True)

    def _render(self):
        width,height = im.get_main_viewport().size
        self.docks.draw((0.,0.,float(width),float(height)))
        self.page.draw_dialogs((0.,0.,float(width),float(height)))

    def get_settings(self):
        return self.model.get_settings()

    def load_data_into_tables(self, data):
        from chisurf.core.setup_channel_definition import ChannelDefinition
        model = ChannelDefinition(data,file_path=self.model.file_path,db=self.model.db)
        model.on_changed = self.model.on_changed
        callback = self.model.on_changed
        self.model.__dict__.update(model.__dict__)
        self.model.on_changed = callback
        self.page.setup_name = self.model.current_name
        self.page.public = bool(self.model.data.get('_is_public'))
        self.page.optical = None
        self.model.changed()

    def export_settings(self):
        return {'channel_definition':self.get_settings(),'section':self.page.section,'setups_file':str(self.model.file_path) if self.model.file_path else None}

    def restore_settings(self, settings):
        if isinstance(settings.get('channel_definition'),dict):
            self.load_data_into_tables(settings['channel_definition'])
        try:
            self.page.section = max(0,min(5,int(settings.get('section',0))))
        except (TypeError,ValueError):
            self.page.section = 0
        self.model.file_path = settings.get('setups_file') or None

    def close(self):
        self.page.close()


def create_app(**kwargs):
    from chisurf.emtk.i18n import install
    install()
    return SetupChannelDefinitionApp(**kwargs)
