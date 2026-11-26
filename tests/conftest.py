import os
import tempfile

# isolate tests from the user's cache and server (set before hexcad is imported)
os.environ["HEXCAD_CACHE"] = tempfile.mkdtemp(prefix="hexcad-test-cache-")
os.environ["HEXCAD_SERVER"] = ""
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
