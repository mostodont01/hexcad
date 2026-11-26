"""`hexcad serve` / `sync` must start on a server without the CAD kernel (e.g. no libGL for OCP)."""
import subprocess
import sys

CODE = """
import sys
class Block:
    def find_spec(self, name, path=None, target=None):
        if name.split('.')[0] in ('build123d', 'OCP'):
            raise ImportError('blocked: ' + name)
sys.meta_path.insert(0, Block())
from hexcad import cli, server, cache
assert 'build123d' not in sys.modules
"""


def test_server_modules_import_without_cad_kernel():
    r = subprocess.run([sys.executable, "-c", CODE], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
