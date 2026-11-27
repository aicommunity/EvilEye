"""create_app() must not write credentials into the repository root."""

import json
from pathlib import Path

from evileye.api.app import create_app
from evileye.core.paths import creds_path


def test_create_app_does_not_touch_repo_credentials(isolate_site_dir):
    repo_root = Path(__file__).resolve().parents[3]
    repo_creds = repo_root / "credentials.json"
    before = repo_creds.read_bytes() if repo_creds.exists() else None

    create_app()

    after = repo_creds.read_bytes() if repo_creds.exists() else None
    assert after == before

    site_creds = creds_path()
    assert site_creds == isolate_site_dir / "credentials.json"
    assert site_creds.is_file()
    written = json.loads(site_creds.read_text(encoding="utf-8"))
    assert isinstance(written.get("web_auth"), dict)
    assert repo_creds.resolve() != site_creds.resolve()
