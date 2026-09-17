import sys

print("--- sys.path ---")
for p in sys.path:
    print(p)
print("----------------")

try:
    import pandas as pd

    print(f"Pandas imported from: {pd.__file__}")
    print(f"Pandas version: {pd.__version__}")
except Exception as e:
    print(f"FAILED to import pandas: {e}")
    import traceback

    traceback.print_exc()
