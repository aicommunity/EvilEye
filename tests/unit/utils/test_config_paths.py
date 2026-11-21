import subprocess
import sys

from evileye.utils.config_paths import normalize_config_path


def test_normalize_config_path_adds_prefix():
    assert normalize_config_path("my_config.json") == "configs/my_config.json"


def test_normalize_config_path_keeps_existing_prefix():
    assert normalize_config_path("configs/system.json") == "configs/system.json"


def test_config_paths_import_is_lightweight():
    code = (
        "import sys\n"
        "from evileye.utils.config_paths import normalize_config_path\n"
        "assert normalize_config_path('x.json') == 'configs/x.json'\n"
        "assert 'onnxruntime' not in sys.modules\n"
        "assert 'albumentations' not in sys.modules\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr or proc.stdout
