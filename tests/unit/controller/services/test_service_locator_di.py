from evileye.controller.services.service_locator import ServiceLocator
from evileye.controller.services.pipeline_service import PipelineService
from evileye.controller.services.database_service import DatabaseService
from evileye.controller.services.events_service import EventsService
from evileye.controller.services.visualization_service import VisualizationService
from evileye.controller.services.config_service import ConfigurationService
from evileye.controller.services.objects_handler_service import ObjectsHandlerService
from evileye.controller.services.streaming_service import StreamingService
from evileye.controller.services.preview_render_service import PreviewRenderService


def test_service_locator_creates_services_via_container():
    locator = ServiceLocator()
    locator.create_all_services(class_manager=object())

    assert isinstance(locator.get_pipeline_service(), PipelineService)
    assert isinstance(locator.get_database_service(), DatabaseService)
    assert isinstance(locator.get_events_service(), EventsService)
    assert isinstance(locator.get_visualization_service(), VisualizationService)
    assert isinstance(locator.get_config_service(), ConfigurationService)
    assert isinstance(locator.get_objects_handler_service(), ObjectsHandlerService)
    assert isinstance(locator.get_streaming_service(), StreamingService)
    assert isinstance(locator.get_preview_render_service(), PreviewRenderService)


def test_service_locator_create_all_services_is_idempotent():
    locator = ServiceLocator()
    locator.create_all_services(class_manager=object())
    first = locator.get_pipeline_service()

    locator.create_all_services(class_manager=object())
    second = locator.get_pipeline_service()

    assert first is second
