"""Diff the committed Qt tool's model (HEAD gui/tool.py, _Kappa2DistModel) against gui/model.py, method by method."""
import ast, difflib, subprocess
head = subprocess.run(["git", "show", "HEAD~0:chisurf/plugins/calculator/kappa2_dist/gui/tool.py"], capture_output=True, text=True, check=True).stdout
import sys
if len(sys.argv) > 1:
    head = subprocess.run(["git", "show", f"{sys.argv[1]}:chisurf/plugins/calculator/kappa2_dist/gui/tool.py"], capture_output=True, text=True, check=True).stdout
def methods(src, cls):
    return {f.name: ast.unparse(f) for n in ast.parse(src).body if isinstance(n, ast.ClassDef) and n.name == cls
            for f in n.body if isinstance(f, ast.FunctionDef)}
h = methods(head, "_Kappa2DistModel"); m = methods(open("chisurf/plugins/calculator/kappa2_dist/gui/model.py").read(), "_Kappa2DistModel")
print("methods:", sorted(h) == sorted(m), sorted(set(h) ^ set(m)))
for name in sorted(set(h) | set(m)):
    if h.get(name) != m.get(name):
        print("DIFF", name)
        print("\n".join(difflib.unified_diff((h.get(name) or "").splitlines(), (m.get(name) or "").splitlines(), lineterm="")))
