# DEPRECATED: /api/v1/pipelines/{rid}/objects, /events, /stream/data
# These endpoints require direct access to Controller internals (PipelineManager._get_runner),
# which only works for in-process pipelines. With Config Runs the controller lives in a
# separate process, so these endpoints cannot function.
# Code kept for reference; router is no longer registered in app.py.

# import asyncio
# from typing import List, Optional, Dict, Any
#
# from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
# from pydantic import BaseModel
#
# from evileye.core.logger import get_module_logger
# from evileye.api.core.manager_access import get_manager
# from evileye.api.core.pipeline_manager import PipelineState
#
# logger = get_module_logger("api.events")
#
# router = APIRouter(prefix="/api/v1", tags=["events"])
#
#
# class ObjectBbox(BaseModel):
#     x1: float
#     y1: float
#     x2: float
#     y2: float
#
#
# class ObjectInfo(BaseModel):
#     object_id: int
#     source_id: int
#     class_id: int
#     class_name: Optional[str] = None
#     confidence: float
#     bbox: ObjectBbox
#     track_id: Optional[int] = None
#     timestamp: Optional[str] = None
#     properties: Dict[str, Any] = {}
#
#
# class EventInfo(BaseModel):
#     event_id: Optional[int] = None
#     event_type: str
#     source_id: Optional[int] = None
#     object_id: Optional[int] = None
#     timestamp: str
#     metadata: Dict[str, Any] = {}
#
#
# def _require_running_pipeline(rid: int):
#     """Return (pipeline_info, runner) or raise HTTPException."""
#     try:
#         info = get_manager().describe(rid)
#     except KeyError as exc:
#         raise HTTPException(status_code=404, detail=f"Pipeline '{rid}' not found") from exc
#     if info["state"] != PipelineState.RUNNING:
#         raise HTTPException(status_code=400, detail=f"Pipeline '{rid}' is not running")
#     runner = get_manager()._get_runner(rid)
#     return info, runner
#
#
# def _extract_objects(runner, object_type: str = "active") -> List[dict]:
#     """Extract tracked-object dicts from a pipeline runner."""
#     if runner.controller is None:
#         return []
#     obj_handler = runner.controller.obj_handler
#     if obj_handler is None:
#         return []
#     objects = []
#     sources = runner.controller.pipeline.get_sources() if hasattr(runner.controller, "pipeline") else []
#     source_ids = [src.get_id() for src in sources] if sources else [0]
#     for source_id in source_ids:
#         obj_list = obj_handler.get(object_type, source_id)
#         if not obj_list or not hasattr(obj_list, "objects"):
#             continue
#         for obj in obj_list.objects:
#             track = getattr(obj, "track", None)
#             bbox = getattr(track, "bounding_box", [0, 0, 0, 0]) if track else [0, 0, 0, 0]
#             confidence = getattr(track, "confidence", 0.0) if track else 0.0
#             track_id = getattr(track, "track_id", None) if track else None
#             objects.append({
#                 "object_id": getattr(obj, "object_id", 0),
#                 "source_id": getattr(obj, "source_id", source_id),
#                 "class_id": getattr(obj, "class_id", 0),
#                 "class_name": getattr(obj, "class_name", None),
#                 "confidence": float(confidence),
#                 "bbox": {
#                     "x1": float(bbox[0]) if len(bbox) >= 1 else 0,
#                     "y1": float(bbox[1]) if len(bbox) >= 2 else 0,
#                     "x2": float(bbox[2]) if len(bbox) >= 3 else 0,
#                     "y2": float(bbox[3]) if len(bbox) >= 4 else 0,
#                 },
#                 "track_id": track_id,
#                 "timestamp": str(getattr(obj, "time_stamp", "")),
#                 "properties": getattr(obj, "properties", {}),
#             })
#     return objects
#
#
# def _extract_events(runner, event_type_filter=None):
#     """Extract event dicts from a pipeline runner."""
#     if runner.controller is None:
#         return []
#     events_detector = runner.controller.events_detectors_controller
#     if events_detector is None:
#         return []
#     result = []
#     try:
#         events_dict = (
#             events_detector.events_detectors
#             if hasattr(events_detector, "events_detectors")
#             else events_detector.get()
#         )
#         if not events_dict:
#             return result
#         for _detector_name, events in events_dict.items():
#             if not events or not isinstance(events, list):
#                 continue
#             for event in events:
#                 if not hasattr(event, "get_name"):
#                     continue
#                 name = event.get_name()
#                 if event_type_filter and event_type_filter != name:
#                     continue
#                 result.append({
#                     "event_type": name,
#                     "source_id": getattr(event, "source_id", None),
#                     "object_id": getattr(event, "object_id", None),
#                     "timestamp": str(getattr(event, "timestamp", "")),
#                 })
#     except Exception as e:
#         logger.debug("Error accessing events: %s", e)
#     return result
#
#
# @router.get("/pipelines/{rid}/objects")
# async def get_objects(
#     rid: int,
#     object_type: str = Query("active", description="Object type: 'active', 'lost', 'all'"),
# ) -> List[ObjectInfo]:
#     _info, runner = _require_running_pipeline(rid)
#     try:
#         raw = _extract_objects(runner, object_type)
#         return [ObjectInfo(**obj) for obj in raw]
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error("Failed to retrieve objects for pipeline '%s': %s", rid, e)
#         raise HTTPException(status_code=500, detail=f"Failed to retrieve objects: {e}") from e
#
#
# @router.get("/pipelines/{rid}/events")
# async def get_events(
#     rid: int,
#     event_type: Optional[str] = Query(None, description="Filter by event type"),
# ) -> List[EventInfo]:
#     _info, runner = _require_running_pipeline(rid)
#     try:
#         raw = _extract_events(runner, event_type)
#         return [EventInfo(**ev) for ev in raw]
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error("Failed to retrieve events for pipeline '%s': %s", rid, e)
#         raise HTTPException(status_code=500, detail=f"Failed to retrieve events: {e}") from e
#
#
# @router.websocket("/pipelines/{rid}/stream/data")
# async def websocket_data_stream(
#     websocket: WebSocket,
#     rid: int,
#     update_interval: float = 0.1,
#     include_objects: bool = True,
#     include_events: bool = True,
# ):
#     await websocket.accept()
#     try:
#         _info, runner = _require_running_pipeline(rid)
#     except HTTPException as exc:
#         await websocket.send_json({"error": exc.detail})
#         await websocket.close()
#         return
#     try:
#         while True:
#             data = {}
#             if include_objects:
#                 data["objects"] = _extract_objects(runner, "active")
#             if include_events:
#                 data["events"] = _extract_events(runner)
#             data["metadata"] = {
#                 "pipeline_id": rid,
#                 "timestamp": str(asyncio.get_event_loop().time()),
#             }
#             await websocket.send_json(data)
#             await asyncio.sleep(update_interval)
#     except WebSocketDisconnect:
#         logger.info("WebSocket disconnected for pipeline '%s'", rid)
#     except Exception as e:
#         logger.error("WebSocket error for pipeline '%s': %s", rid, e)
#         try:
#             await websocket.send_json({"error": str(e)})
#         except Exception:
#             pass
