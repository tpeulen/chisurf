"""Capture the native emtk user editor against a seeded TEMPORARY MMFDB.

Usage: ``python capture_emtk_populated.py <out_dir> [name-part ...]`` (only the pictures whose
file name contains one of the parts are written) from the repository root with the
PRD's environment (QT_QPA_PLATFORM=offscreen, PYTHONPATH with the repository, emtk and
mmfdb/src). Settings and database live in a temp folder; a fresh app is built per size.
"""
import sys
import tempfile
import time
from pathlib import Path

from test.gui.emtk_port_parity import draw_app, emtk_screenshot  # first: 'test' is also a stdlib name

out = Path(sys.argv[1])
tmp = Path(tempfile.mkdtemp(prefix="ue_emtk_"))

from chisurf.plugins.core.user_editor.test import seeded_db as db  # noqa: E402

db.use_folder(tmp)
client = db.admin_client()
db.seed(client)

import chisurf.plugins.core.user_editor.gui.model as model_module  # noqa: E402
from chisurf.plugins.core.user_editor.gui import view_model  # noqa: E402
from chisurf.plugins.core.user_editor.gui.app import UserEditorApp  # noqa: E402

view_model.active_user_id = lambda: "admin"
model_module.active_user_id = lambda: "admin"
model_module.UserEditorModel.carry_local_state = staticmethod(lambda old, new: None)


def build(factory, size=(1200, 800)):
    app = UserEditorApp(model_module.UserEditorModel(client_factory=factory), autoload=True)
    pump(app, size)
    return app


def pump(app, size):
    for _ in range(500):
        draw_app(app, size, 1)
        if not app.job.busy:
            break
        time.sleep(0.01)
    draw_app(app, size, 2)


def click(app, key, size):
    binding = app.form.tables["user_records"]
    control = binding.control
    index = next(i for i in range(control.row_count()) if control.key_of(i) == key)
    control.selected_key = key
    binding._on_select(index)
    draw_app(app, size, 2)


ONLY = sys.argv[2:]


def shot(app, name, size):
    if ONLY and not any(part in name for part in ONLY):
        return
    draw_app(app, size, 2)
    emtk_screenshot(app, out / name, size)
    print("wrote", name)


for size in ((1200, 800), (800, 600)):
    tag = f"{size[0]}x{size[1]}"
    app = build(lambda: client, size)
    shot(app, f"after_populated_{tag}.png", size)
    click(app, "bob", size)
    shot(app, f"after_populated_selected_{tag}.png", size)
    app.model.display_name = "Bob Baker-Smith"
    app.model.email = "not-an-email"
    shot(app, f"after_populated_dirty_validation_{tag}.png", size)
    app.model.do_save()
    shot(app, f"after_populated_save_refused_{tag}.png", size)
    app.model.email = "bob@example.org"
    app.model.ask_revert()
    shot(app, f"after_populated_revert_confirm_{tag}.png", size)
    app.model.confirm_no()
    app = build(lambda: client, size)
    click(app, "carol", size)
    app.model.ask_delete()
    shot(app, f"after_populated_delete_confirm_{tag}.png", size)
    app.model.confirm_no()
    app.model.password_cancel()
    app = build(lambda: client, size)
    click(app, "bob", size)
    app.model.ask_password()
    app.model.password_new, app.model.password_confirm = "Abcdef1!", "Abcdef1"
    shot(app, f"after_populated_password_{tag}.png", size)
    app.model.password_set()
    shot(app, f"after_populated_password_mismatch_{tag}.png", size)
    app.model.password_new = app.model.password_confirm = "Abcdef1!"
    app.model.password_set()
    shot(app, f"after_populated_password_staged_{tag}.png", size)

size = (1200, 800)
app = build(lambda: client, size)
app.form.tables["user_records"].control.filter.set_text("a")
app.form.tables["user_records"].control.sort_by("role", False)
shot(app, "after_populated_search_sorted_1200x800.png", size)
app = build(lambda: client, size)
click(app, "dave", size)
shot(app, "after_populated_role_kept_1200x800.png", size)
app = build(lambda: client, size)
app.model.new_user()
app.model.do_save()
shot(app, "after_populated_new_refused_1200x800.png", size)
app.model.user_id, app.model.display_name = "frank", "Frank Fischer"
app.model.do_save()
pump(app, size)
shot(app, "after_populated_new_saved_1200x800.png", size)
app = build(lambda: client, size)
click(app, "admin", size)
app.model.ask_delete()
shot(app, "after_populated_delete_refused_active_1200x800.png", size)
plain = db.admin_client(db.PLAIN_USER)
app = build(lambda: plain, size)
shot(app, "after_populated_denied_1200x800.png", size)
app = build(lambda: client, (500, 500))
click(app, "bob", (500, 500))
shot(app, "after_populated_narrow_500x500.png", (500, 500))
