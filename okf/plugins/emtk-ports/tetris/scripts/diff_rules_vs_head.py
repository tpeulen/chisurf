"""Diff the committed Qt game's rules (HEAD tetris.py, class TetrisGame) against model.TetrisModel, method by method.

Run from the repo root. Prints every differing method (draw/setup excluded: view code).
"""
import ast, difflib, subprocess
head = subprocess.run(["git", "show", "HEAD:chisurf/plugins/misc/games/tetris/tetris.py"], capture_output=True, text=True, check=True).stdout
def methods(src, cls):
    return {f.name: ast.unparse(f) for n in ast.parse(src).body if isinstance(n, ast.ClassDef) and n.name == cls
            for f in n.body if isinstance(f, ast.FunctionDef)}
h = methods(head, "TetrisGame"); m = methods(open("chisurf/plugins/misc/games/tetris/model.py").read(), "TetrisModel")
for name in sorted((set(h) | set(m)) - {"draw", "setup"}):
    if h.get(name) != m.get(name):
        print("DIFF", name)
        print("\n".join(difflib.unified_diff((h.get(name) or "").splitlines(), (m.get(name) or "").splitlines(), lineterm="")))
