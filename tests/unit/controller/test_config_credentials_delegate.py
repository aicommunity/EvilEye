from evileye.controller.services.config_service import ConfigurationService


def test_reconcile_credentials_strips_injected_password_field():
    svc = ConfigurationService()
    loaded = {
        "pipeline": {
            "sources": [{"camera": "rtsp://host/stream", "source": "VideoFile"}],
        }
    }
    params = {
        "pipeline": {
            "sources": [
                {
                    "camera": "rtsp://host/stream",
                    "source": "VideoFile",
                    "password": "injected",
                }
            ],
        }
    }
    svc.reconcile_credentials_fields(params, loaded, credentials_loaded=False)
    assert "password" not in params["pipeline"]["sources"][0]
