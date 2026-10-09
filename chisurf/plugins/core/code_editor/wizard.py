"""Code Editor plugin launcher."""

from chisurf.plugins.core.code_editor.gui.tool import CodeEditorEmtkTool, run_code_editor

if __name__ == "plugin":
    window = CodeEditorEmtkTool()
    window.show()


if __name__ == "__main__":
    run_code_editor()
