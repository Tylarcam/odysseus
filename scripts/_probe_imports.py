import sys, types, time
# Stub core/__init__ to avoid its cascade; we only want core.database.
sys.modules['core'] = types.ModuleType('core')
sys.modules['core'].__path__ = ['/app/core']

t0 = time.time()
print("importing core.database (runs init_db at import time)...", flush=True)
try:
    import core.database
    print(f"OK core.database in {time.time()-t0:.1f}s", flush=True)
except Exception as e:
    import traceback; traceback.print_exc()
    print("FAIL", flush=True)
print("DONE", flush=True)
