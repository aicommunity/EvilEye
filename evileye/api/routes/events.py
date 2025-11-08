from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from typing import List, Optional, Dict, Any
from pydantic import BaseModel

from evileye.core.logger import get_module_logger
from evileye.api.core.manager_access import get_manager
from evileye.api.core.pipeline_manager import PipelineState
import asyncio

logger = get_module_logger("api.events")

router = APIRouter(prefix="/api/v1", tags=["events"])


class ObjectBbox(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float


class ObjectInfo(BaseModel):
    object_id: int
    source_id: int
    class_id: int
    class_name: Optional[str] = None
    confidence: float
    bbox: ObjectBbox
    track_id: Optional[int] = None
    timestamp: Optional[str] = None
    properties: Dict[str, Any] = {}


class EventInfo(BaseModel):
    event_id: Optional[int] = None
    event_type: str
    source_id: Optional[int] = None
    object_id: Optional[int] = None
    timestamp: str
    metadata: Dict[str, Any] = {}


@router.get("/pipelines/{rid}/objects")
async def get_objects(
    rid: int,
    object_type: str = Query("active", description="Object type: 'active', 'lost', 'all'")
) -> List[ObjectInfo]:
    """
    Get tracked objects from the pipeline.
    
    Parameters:
    - pid: Pipeline ID
    - object_type: Type of objects to retrieve ('active', 'lost', 'all')
    """
    logger.info(f"GET /pipelines/{rid}/objects: object_type={object_type}")
    try:
        pipeline_info = get_manager().describe(rid)
        if pipeline_info["state"] != PipelineState.RUNNING:
            logger.warning(f"Pipeline '{rid}' is not running (state: {pipeline_info['state']})")
            raise HTTPException(status_code=400, detail=f"Pipeline '{rid}' is not running")
    except KeyError:
        logger.error(f"Pipeline '{rid}' not found")
        raise HTTPException(status_code=404, detail=f"Pipeline '{rid}' not found")
    
    try:
        runner = get_manager()._get_runner(rid)
        if runner.controller is None:
            logger.warning(f"Controller is None for pipeline '{rid}'")
            return []
        
        obj_handler = runner.controller.obj_handler
        if obj_handler is None:
            logger.warning(f"Object handler is None for pipeline '{pid}'")
            return []
        
        objects = []
        sources = runner.controller.pipeline.get_sources() if hasattr(runner.controller, 'pipeline') else []
        source_ids = [src.get_id() for src in sources] if sources else [0]
        
        for source_id in source_ids:
            obj_list = obj_handler.get(object_type, source_id)
            if not obj_list or not hasattr(obj_list, 'objects'):
                continue
            
            for obj in obj_list.objects:
                track = getattr(obj, 'track', None)
                bbox = getattr(track, 'bounding_box', [0, 0, 0, 0]) if track else [0, 0, 0, 0]
                confidence = getattr(track, 'confidence', 0.0) if track else 0.0
                track_id = getattr(track, 'track_id', None) if track else None
                
                obj_data = {
                    "object_id": getattr(obj, 'object_id', 0),
                    "source_id": getattr(obj, 'source_id', source_id),
                    "class_id": getattr(obj, 'class_id', 0),
                    "class_name": getattr(obj, 'class_name', None),
                    "confidence": confidence,
                    "bbox": {
                        "x1": bbox[0] if len(bbox) >= 1 else 0,
                        "y1": bbox[1] if len(bbox) >= 2 else 0,
                        "x2": bbox[2] if len(bbox) >= 3 else 0,
                        "y2": bbox[3] if len(bbox) >= 4 else 0
                    },
                    "track_id": track_id,
                    "timestamp": str(getattr(obj, 'time_stamp', '')),
                    "properties": getattr(obj, 'properties', {})
                }
                objects.append(ObjectInfo(**obj_data))
        
        logger.info(f"Retrieved {len(objects)} objects for pipeline '{rid}'")
        return objects
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve objects for pipeline '{rid}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve objects: {str(e)}")


@router.get("/pipelines/{rid}/events")
async def get_events(
    rid: int,
    event_type: Optional[str] = Query(None, description="Filter by event type")
) -> List[EventInfo]:
    """
    Get events from the pipeline.
    
    Parameters:
    - pid: Pipeline ID
    - event_type: Optional filter by event type
    """
    logger.info(f"GET /pipelines/{rid}/events: event_type={event_type}")
    try:
        pipeline_info = get_manager().describe(rid)
        if pipeline_info["state"] != PipelineState.RUNNING:
            logger.warning(f"Pipeline '{rid}' is not running for WebSocket (state: {pipeline_info['state']})")
            raise HTTPException(status_code=400, detail=f"Pipeline '{rid}' is not running")
    except KeyError:
        logger.error(f"Pipeline '{rid}' not found for WebSocket")
        raise HTTPException(status_code=404, detail=f"Pipeline '{rid}' not found")
    
    try:
        runner = get_manager()._get_runner(rid)
        if runner.controller is None:
            logger.warning(f"Controller is None for pipeline '{rid}'")
            return []
        
        events_detector = runner.controller.events_detectors_controller
        if events_detector is None:
            logger.warning(f"Events detector is None for pipeline '{rid}'")
            return []
        
        events_list = []
        try:
            events_dict = events_detector.events_detectors if hasattr(events_detector, 'events_detectors') else events_detector.get()
            
            if events_dict:
                for detector_name, events in events_dict.items():
                    if events and isinstance(events, list):
                        for event in events:
                            if hasattr(event, 'get_name'):
                                event_type_name = event.get_name()
                                if event_type and event_type != event_type_name:
                                    continue
                                
                                event_data = {
                                    "event_type": event_type_name,
                                    "source_id": getattr(event, 'source_id', None),
                                    "object_id": getattr(event, 'object_id', None),
                                    "timestamp": str(getattr(event, 'timestamp', '')),
                                    "metadata": {}
                                }
                                events_list.append(EventInfo(**event_data))
        except Exception as e:
            logger.debug(f"Error accessing events: {e}")
        
        logger.info(f"Retrieved {len(events_list)} events for pipeline '{rid}'")
        return events_list
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve events for pipeline '{rid}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve events: {str(e)}")


@router.get("/pipelines/{rid}/metadata")
async def get_metadata(rid: int) -> Dict[str, Any]:
    """
    Get pipeline metadata including statistics and configuration.
    
    Parameters:
    - pid: Pipeline ID
    """
    logger.info(f"GET /pipelines/{rid}/metadata")
    try:
        pipeline_info = get_manager().describe(rid)
    except KeyError:
        logger.error(f"Pipeline '{rid}' not found")
        raise HTTPException(status_code=404, detail=f"Pipeline '{rid}' not found")
    
    try:
        runner = get_manager()._get_runner(rid)
        metadata = {
            "pipeline_id": rid,
            "pipeline_name": pipeline_info.get("name"),
            "state": pipeline_info.get("state"),
            "statistics": {}
        }
        
        if runner.controller is not None:
            obj_handler = runner.controller.obj_handler
            if obj_handler:
                active_count = len(obj_handler.active_objs.objects) if hasattr(obj_handler, 'active_objs') else 0
                lost_count = len(obj_handler.lost_objs.objects) if hasattr(obj_handler, 'lost_objs') else 0
                metadata["statistics"] = {
                    "active_objects": active_count,
                    "lost_objects": lost_count
                }
            
            if hasattr(runner.controller, 'pipeline') and runner.controller.pipeline:
                sources = runner.controller.pipeline.get_sources()
                metadata["sources"] = [
                    {
                        "source_id": src.get_id(),
                        "source_name": getattr(src, 'source_name', f"Source-{src.get_id()}")
                    }
                    for src in sources
                ]
        
        logger.info(f"Retrieved metadata for pipeline '{rid}'")
        return metadata
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve metadata for pipeline '{rid}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve metadata: {str(e)}")


def _get_objects_data(runner, object_type: str = "active") -> List[dict]:
    """Helper function to extract objects data from pipeline."""
    if runner.controller is None:
        return []
    
    obj_handler = runner.controller.obj_handler
    if obj_handler is None:
        return []
    
    objects = []
    sources = runner.controller.pipeline.get_sources() if hasattr(runner.controller, 'pipeline') else []
    source_ids = [src.get_id() for src in sources] if sources else [0]
    
    for source_id in source_ids:
        obj_list = obj_handler.get(object_type, source_id)
        if not obj_list or not hasattr(obj_list, 'objects'):
            continue
        
        for obj in obj_list.objects:
            track = getattr(obj, 'track', None)
            bbox = getattr(track, 'bounding_box', [0, 0, 0, 0]) if track else [0, 0, 0, 0]
            confidence = getattr(track, 'confidence', 0.0) if track else 0.0
            track_id = getattr(track, 'track_id', None) if track else None
            
            obj_data = {
                "object_id": getattr(obj, 'object_id', 0),
                "source_id": getattr(obj, 'source_id', source_id),
                "class_id": getattr(obj, 'class_id', 0),
                "class_name": getattr(obj, 'class_name', None),
                "confidence": confidence,
                "bbox": {
                    "x1": float(bbox[0]) if len(bbox) >= 1 else 0,
                    "y1": float(bbox[1]) if len(bbox) >= 2 else 0,
                    "x2": float(bbox[2]) if len(bbox) >= 3 else 0,
                    "y2": float(bbox[3]) if len(bbox) >= 4 else 0
                },
                "track_id": track_id,
                "timestamp": str(getattr(obj, 'time_stamp', '')),
                "properties": getattr(obj, 'properties', {})
            }
            objects.append(obj_data)
    
    return objects


@router.websocket("/pipelines/{rid}/stream/data")
async def websocket_data_stream(
    websocket: WebSocket,
    rid: int,
    update_interval: float = 0.1,
    include_objects: bool = True,
    include_events: bool = True
):
    """
    WebSocket endpoint for real-time objects and events streaming.
    
    Parameters:
    - pid: Pipeline ID
    - update_interval: Update interval in seconds (default: 0.1)
    - include_objects: Include objects in stream (default: true)
    - include_events: Include events in stream (default: true)
    """
    logger.info(f"WebSocket connection established for pipeline '{rid}'")
    await websocket.accept()
    
    try:
        pipeline_info = get_manager().describe(rid)
        if pipeline_info["state"] != PipelineState.RUNNING:
            logger.warning(f"Pipeline '{rid}' is not running for WebSocket (state: {pipeline_info['state']})")
            await websocket.send_json({"error": f"Pipeline '{pid}' is not running"})
            return
    except KeyError:
        logger.error(f"Pipeline '{rid}' not found for WebSocket")
        await websocket.send_json({"error": f"Pipeline '{pid}' not found"})
        return
    
    try:
        runner = get_manager()._get_runner(rid)
        logger.info(f"WebSocket stream started for pipeline '{rid}', update_interval={update_interval}s")
        
        while True:
            data = {}
            
            if include_objects:
                objects = _get_objects_data(runner, "active")
                data["objects"] = objects
            
            if include_events:
                events_detector = runner.controller.events_detectors_controller if runner.controller else None
                if events_detector:
                    try:
                        events_dict = events_detector.events_detectors if hasattr(events_detector, 'events_detectors') else events_detector.get()
                        events_list = []
                        if events_dict:
                            for detector_name, events in events_dict.items():
                                if events and isinstance(events, list):
                                    for event in events:
                                        if hasattr(event, 'get_name'):
                                            events_list.append({
                                                "event_type": event.get_name(),
                                                "source_id": getattr(event, 'source_id', None),
                                                "object_id": getattr(event, 'object_id', None),
                                                "timestamp": str(getattr(event, 'timestamp', ''))
                                            })
                        data["events"] = events_list
                    except Exception as e:
                        logger.debug(f"Error accessing events in WebSocket: {e}")
                        data["events"] = []
            
            data["metadata"] = {
                "pipeline_id": rid,
                "timestamp": str(asyncio.get_event_loop().time())
            }
            
            await websocket.send_json(data)
            await asyncio.sleep(update_interval)
            
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for pipeline '{rid}'")
        pass
    except Exception as e:
        logger.error(f"WebSocket error for pipeline '{rid}': {e}")
        await websocket.send_json({"error": str(e)})
