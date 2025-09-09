import pathlib
import json
import datetime
import numpy as np
import cv2
from ..object_tracker.tracking_results import TrackingResult
from ..objects_handler.object_result import ObjectResultHistory
import copy
from pathlib import Path

from sympy.multipledispatch.dispatcher import source

from ..database_controller import database_controller_pg
from psycopg2 import sql
from ..capture.video_capture_base import CaptureImage
# from object_tracker.object_tracking_botsort import BOTrack
from ..object_tracker.trackers.sctrack import SCTrack


def get_project_root() -> Path:
    return Path(__file__).parent.parent


def boxes_iou(box1, box2):
    area1 = (box1[2] - box1[0] + 1) * (box1[3] - box1[1] + 1)
    area2 = (box2[2] - box2[0] + 1) * (box2[3] - box2[1] + 1)
    if (((box1[0] <= box2[0] and box1[1] <= box2[1]) and (
            box2[2] <= box1[2] and box2[3] <= box1[3])) or  # Находится ли один bbox внутри другого
            ((box2[0] <= box1[0] and box2[1] <= box1[1]) and (box1[2] <= box2[2] and box1[3] <= box2[3]))):
        return 1.0, box1 if area1 > area2 else box2
    x_left = max(box1[0], box2[0])
    y_top = max(box1[1], box2[1])
    x_right = min(box1[2], box2[2])
    y_bottom = min(box1[3], box2[3])
    if x_right - x_left + 1 <= 0 or y_bottom - y_top + 1 <= 0:  # Если рамки никак не пересекаются
        return -1.0, None
    intersection = (x_right - x_left + 1) * (y_bottom - y_top + 1)
    iou = intersection / float(area1 + area2 - intersection)
    return iou, box1 if area1 > area2 else box2


def non_max_sup(boxes_coords, confidences, class_ids):
    confidences = np.array(confidences, dtype='float64')
    boxes_coords = np.array(boxes_coords, dtype='float64')
    class_ids = np.array(class_ids, dtype='float64')
    sorted_idxs = np.argsort(confidences)
    iou_thresh = 0.5
    keep_idxs = []
    while len(sorted_idxs) > 0:
        last = len(sorted_idxs) - 1
        suppress_idxs = [last]  # Индекс рамки с наибольшей вероятностью
        keep_idxs.append(sorted_idxs[last])
        for i in range(len(sorted_idxs) - 1):
            idx = sorted_idxs[i]
            iou, max_box = boxes_iou(boxes_coords[sorted_idxs[last]], boxes_coords[idx])
            if iou > iou_thresh:  # Если iou превышает порог, то добавляем данную рамку на удаление
                boxes_coords[idx] = copy.deepcopy(max_box)
                suppress_idxs.append(i)
        sorted_idxs = np.delete(sorted_idxs, suppress_idxs)
    boxes_coords = boxes_coords[keep_idxs].tolist()
    class_ids = class_ids[keep_idxs].tolist()
    confidences = confidences[keep_idxs].tolist()
    return boxes_coords, confidences, class_ids


def roi_to_image(roi_box_coords, x0, y0):
    image_box_coords = [x0 + int(roi_box_coords[0]), y0 + int(roi_box_coords[1]),
                        x0 + int(roi_box_coords[2]), y0 + int(roi_box_coords[3])]
    return image_box_coords


def create_roi(capture_image: CaptureImage, coords):
    rois = []
    img = capture_image.image
    for x, y, w, h in coords:
        roi_img = img[y:y+h, x:x+w]
        roi_capture = CaptureImage()
        roi_capture.source_id = capture_image.source_id
        roi_capture.frame_id = capture_image.frame_id
        roi_capture.current_video_frame = capture_image.current_video_frame
        roi_capture.current_video_position = capture_image.current_video_position
        roi_capture.time_stamp = capture_image.time_stamp
        roi_capture.image = roi_img
        rois.append([roi_capture, [x, y]])
    return rois


def merge_roi_boxes(all_roi, bboxes_coords, confidences, class_ids):
    bboxes_merged = []
    conf_merged = []
    ids_merged = []
    merged_idxs = []
    for i in range(len(bboxes_coords)):
        intersected_idxs = []
        if i in merged_idxs:
            continue
        for j in range(i + 1, len(bboxes_coords)):
            # Если рамки пересекаются, но находятся в разных регионах, то добавляем их в список пересекающихся
            if ((len(all_roi) != 0) and is_intersected(bboxes_coords[i], bboxes_coords[j])
                    and not is_same_roi(all_roi, bboxes_coords[i], bboxes_coords[j])):
                intersected_idxs.append(j)
        # Если рамка пересекается больше, чем с одной, то проверяем, с какой она пересекается больше, чтобы их объединить
        if len(intersected_idxs) > 1:
            iou = []
            # Определяем, с какой рамкой iou выше
            for k in range(len(intersected_idxs)):
                iou.append(boxes_iou(bboxes_coords[i], bboxes_coords[intersected_idxs[k]]))
            max_idx = iou.index(max(iou))
            # Объединяем с этой рамкой
            bboxes_coords[i] = [min(bboxes_coords[i][0], bboxes_coords[intersected_idxs[max_idx]][0]),
                                min(bboxes_coords[i][1], bboxes_coords[intersected_idxs[max_idx]][1]),
                                max(bboxes_coords[i][2], bboxes_coords[intersected_idxs[max_idx]][2]),
                                max(bboxes_coords[i][3], bboxes_coords[intersected_idxs[max_idx]][3])]
            confidences[i] = max(confidences[i], confidences[intersected_idxs[max_idx]])
            merged_idxs.append(intersected_idxs[max_idx])
        # Если пересекается только с одной, объединяем
        elif len(intersected_idxs) == 1:
            bboxes_coords[i] = [min(bboxes_coords[i][0], bboxes_coords[intersected_idxs[0]][0]),
                                min(bboxes_coords[i][1], bboxes_coords[intersected_idxs[0]][1]),
                                max(bboxes_coords[i][2], bboxes_coords[intersected_idxs[0]][2]),
                                max(bboxes_coords[i][3], bboxes_coords[intersected_idxs[0]][3])]
            confidences[i] = max(confidences[i], confidences[intersected_idxs[0]])
            merged_idxs.append(intersected_idxs[0])
        bboxes_merged.append(bboxes_coords[i])
        conf_merged.append(confidences[i])
        ids_merged.append(class_ids[i])
    return bboxes_merged, conf_merged, ids_merged


def is_same_roi(all_roi, box1, box2):
    if len(all_roi) == 0:
        return True
    surrounding_rois_box1 = []
    surrounding_rois_box2 = []
    for i, roi in enumerate(all_roi):
        if (((roi[1] <= box1[3] <= (roi[1] + roi[3])) and (roi[1] <= box1[1] <= (roi[1] + roi[3]))) and
                ((roi[1] <= box2[3] <= (roi[1] + roi[3])) and (roi[1] <= box2[1] <= (roi[1] + roi[3])))):
            # Если рамки находятся в одном регионе, но хотя бы одна из рамок уже находится в другом, значит
            # регионы вложенные, поэтому возвращаем False и объединяем рамки
            if len(surrounding_rois_box1) > 0 or len(surrounding_rois_box2) > 0:
                return False
            return True
        elif ((roi[1] <= box1[3] <= (roi[1] + roi[3])) and (roi[1] <= box1[1] <= (roi[1] + roi[3])) and not
        ((roi[1] <= box2[3] <= (roi[1] + roi[3])) and (roi[1] <= box2[1] <= (roi[1] + roi[3])))):
            # Проверка на вложенность регионов интереса, создаем для каждой рамки список окружающих регионов
            surrounding_rois_box1.append(i)
        elif ((roi[1] <= box2[3] <= (roi[1] + roi[3])) and (roi[1] <= box2[1] <= (roi[1] + roi[3])) and not
        ((roi[1] <= box1[3] <= (roi[1] + roi[3])) and (roi[1] <= box1[1] <= (roi[1] + roi[3])))):
            # Проверка на вложенность регионов интереса, создаем для каждой рамки список окружающих регионов
            surrounding_rois_box2.append(i)
    return False


def is_intersected(box1, box2):
    if ((box1[2] >= box2[0]) and (box2[2] >= box1[0])) and ((box1[3] >= box2[1]) and (box2[3] >= box1[1])):
        return True
    else:
        return False


def get_objs_info(bboxes_coords, confidences, class_ids):
    objects = []
    for bbox, class_id, conf in zip(bboxes_coords, class_ids, confidences):
        obj = {"bbox": bbox, "conf": conf, "class": class_id}
        objects.append(obj)
    return objects


def draw_boxes(image, objects, cam_id, model_names, text_config=None):
    """
    Draw bounding boxes and labels with adaptive text positioning.
    
    Args:
        image: OpenCV image
        objects: List of detected objects
        cam_id: Camera ID
        model_names: Class names mapping
        text_config: Text configuration dictionary (optional)
    """
    # Apply text configuration
    config = apply_text_config(text_config)
    
    for cam_objs in objects:
        if cam_objs['cam_id'] == cam_id:
            for obj in cam_objs['objects']:
                # Draw bounding box
                cv2.rectangle(image, (int(obj['bbox'][0]), int(obj['bbox'][1])),
                              (int(obj['bbox'][2]), int(obj['bbox'][3])), (0, 255, 0), thickness=8)
                
                # Create text label
                text = str(model_names[obj['class']]) + " " + "{:.2f}".format(obj['conf'])
                
                # Draw text with adaptive positioning
                put_text_with_bbox(image, text, obj['bbox'], 
                                 font_size_pt=config['font_size_pt'],
                                 font_face=config['font_face'],
                                 color=config['color'],
                                 thickness=config['thickness'],
                                 background_color=config['background_color'],
                                 position_offset_percent=config['position_offset_percent'],
                                 font_scale_method=config.get('font_scale_method', 'resolution_based'),
                                 base_resolution=config.get('base_resolution', (1920, 1080)),
                                 background_enabled=config.get('background_enabled', True))


def draw_preview_boxes(image, width, height, box):
    cv2.rectangle(image, (int(box[0] * width), int(box[1] * height)),
                  (int(box[2] * width), int(box[3] * height)), (0, 255, 0), thickness=1)
    return image


def draw_preview_boxes_zones(image, width, height, box, zone_coords):
    points = [(int(point[0] * width), int(point[1] * height)) for point in zone_coords]
    image = cv2.rectangle(image, (int(box[0] * width), int(box[1] * height)),
                          (int(box[2] * width), int(box[3] * height)), (0, 255, 0), thickness=1)
    image = cv2.polylines(image, pts=np.int32([points]), isClosed=True, color=(0, 0, 255), thickness=1)
    return image


def draw_boxes_from_db(db_controller, table_name, load_folder, save_folder):
    query = sql.SQL(
        'SELECT object_id, confidence, bounding_box, lost_bounding_box, frame_path, lost_frame_path FROM {table};').format(
        table=sql.Identifier(table_name))
    res = db_controller.query(query)
    for obj_id, conf, box, lost_box, image_path, lost_image_path in res:
        lost_load_dir = pathlib.Path(load_folder, 'lost')
        detected_load_dir = pathlib.Path(load_folder, 'detected')

        if not lost_load_dir.exists():
            Path.mkdir(lost_load_dir)
        lost_load_path = pathlib.Path(lost_load_dir, Path(lost_image_path).name)
        if not detected_load_dir.exists():
            Path.mkdir(detected_load_dir)
        detected_load_path = pathlib.Path(detected_load_dir, Path(image_path).name)

        if not save_folder.exists():
            pathlib.Path.mkdir(save_folder)

        lost_save_dir = pathlib.Path(save_folder, 'lost')
        if not lost_save_dir.exists():
            Path.mkdir(lost_save_dir)
        detected_save_dir = pathlib.Path(save_folder, 'detected')
        if not detected_save_dir.exists():
            Path.mkdir(detected_save_dir)
        lost_save_path = pathlib.Path(lost_save_dir, Path(lost_image_path).name)
        detected_save_path = pathlib.Path(detected_save_dir, Path(image_path).name)

        lost_image = cv2.imread(lost_load_path.as_posix())
        cv2.rectangle(lost_image, (int(box[0]), int(box[1])),
                      (int(box[2]), int(box[3])), (0, 255, 0), thickness=8)
        cv2.putText(lost_image, str(obj_id) + " " + "{:.2f}".format(conf),
                    (int(box[0]), int(box[1]) - 10), cv2.FONT_HERSHEY_SIMPLEX, 1,
                    (255, 255, 255), 2)

        detected_image = cv2.imread(detected_load_path.as_posix())
        cv2.rectangle(detected_image, (int(box[0]), int(box[1])),
                      (int(box[2]), int(box[3])), (0, 255, 0), thickness=8)
        cv2.putText(detected_image, str(obj_id) + " " + "{:.2f}".format(conf),
                    (int(box[0]), int(box[1]) - 10), cv2.FONT_HERSHEY_SIMPLEX, 1,
                    (255, 255, 255), 2)
        lost_saved = cv2.imwrite(lost_save_path.as_posix(), lost_image)
        detected_saved = cv2.imwrite(detected_save_path.as_posix(), detected_image)
        if not lost_saved or not detected_saved:
            print('Error saving image with boxes')


def draw_boxes_tracking(image: CaptureImage, cameras_objs, source_name, source_duration_msecs, font_scale, font_thickness, font_color, text_config=None):
    height, width, channels = image.image.shape
    
    # Apply text configuration
    config = apply_text_config(text_config)
    
    # Draw source name
    if source_name is int:
        source_text = "Source Id: " + str(source_name)
    else:
        source_text = str(source_name)
    
    # Position source name at bottom-left (10% from left, 10% from bottom)
    put_text_adaptive(image.image, source_text, (10, 90), 
                     font_size_pt=config['font_size_pt'],
                     font_face=config['font_face'],
                     color=config['color'],
                     thickness=config['thickness'],
                     background_color=config['background_color'],
                     font_scale_method=config.get('font_scale_method', 'resolution_based'),
                     base_resolution=config.get('base_resolution', (1920, 1080)),
                     background_enabled=config.get('background_enabled', True))

    # Draw time position
    if image.current_video_position and source_duration_msecs is not None:
        time_position_secs = image.current_video_position / 1000.0
        pos_string = "{:.1f}".format(time_position_secs) + " [" + "{:.1f}".format(source_duration_msecs / 1000.0) + "]"
        
        # Position time at bottom-right (10% from right, 10% from bottom)
        put_text_adaptive(image.image, pos_string, (90, 90), 
                         font_size_pt=config['font_size_pt'],
                         font_face=config['font_face'],
                         color=config['color'],
                         thickness=config['thickness'],
                         background_color=config['background_color'],
                         font_scale_method=config.get('font_scale_method', 'resolution_based'),
                         base_resolution=config.get('base_resolution', (1920, 1080)),
                         background_enabled=config.get('background_enabled', True))

    # Для трекинга отображаем только последние данные об объекте из истории
    # print(cameras_objs)
    for obj in cameras_objs:
        # if obj.frame_id < image.frame_id:
        #     continue

        last_hist_index = len(obj.history) - 1
        last_info = obj.track
        if obj.frame_id != image.frame_id:
            for i in range(len(obj.history) - 1):
                if obj.history[i].frame_id == image.frame_id:
                    last_hist_index = i
                    last_info = obj.history[i].track
                    break

        cv2.rectangle(image.image, (int(last_info.bounding_box[0]), int(last_info.bounding_box[1])),
                      (int(last_info.bounding_box[2]), int(last_info.bounding_box[3])), (0, 255, 0), thickness=font_thickness)
        
        # Create tracking text
        if obj.global_id is not None:
            tracking_text = 'g' + str(obj.global_id) + ' ' + str([last_info.class_id]) + " " + "{:.2f}".format(last_info.confidence)
        else:
            tracking_text = str(last_info.track_id) + ' ' + str([last_info.class_id]) + " " + "{:.2f}".format(last_info.confidence)
        
        # Draw tracking text with adaptive positioning
        put_text_with_bbox(image.image, tracking_text, last_info.bounding_box,
                          font_size_pt=config['font_size_pt'],
                          font_face=config['font_face'],
                          color=config['color'],
                          thickness=config['thickness'],
                          background_color=config['background_color'],
                          position_offset_percent=config['position_offset_percent'],
                          font_scale_method=config.get('font_scale_method', 'resolution_based'),
                          base_resolution=config.get('base_resolution', (1920, 1080)),
                          background_enabled=config.get('background_enabled', True))

        # print(len(obj['obj_info']))
        if len(obj.history) > 1:
            for i in range(0, last_hist_index):
                first_info = obj.history[i].track
                second_info = obj.history[i + 1].track
                first_cm_x = int((first_info.bounding_box[0] + first_info.bounding_box[2]) / 2)
                first_cm_y = int(first_info.bounding_box[3])
                second_cm_x = int((second_info.bounding_box[0] + second_info.bounding_box[2]) / 2)
                second_cm_y = int(second_info.bounding_box[3])
                cv2.line(image.image, (first_cm_x, first_cm_y),
                         (second_cm_x, second_cm_y), (0, 0, 255), thickness=font_thickness)


def draw_debug_info(image: CaptureImage, debug_info: dict):
    if not debug_info:
        return
    if 'detectors' not in debug_info.keys():
        return

    for det_id, det_debug_info in debug_info['detectors'].items():
        if 'source_ids' in det_debug_info.keys() and image.source_id in det_debug_info['source_ids']:
            source_id_index = det_debug_info['source_ids'].index(image.source_id)
            rois = det_debug_info['roi']
            if type(rois) is list and source_id_index in range(len(rois)):
                for roi in rois[source_id_index]:
                    cv2.rectangle(image.image, (int(roi[0]), int(roi[1])),
                                  (int(roi[0] + roi[2]), int(roi[1] + roi[3])), (255, 0, 0), thickness=9)


class ObjectResultEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime.datetime, datetime.date, datetime.time)):
            return obj.isoformat()
        if isinstance(obj, TrackingResult):
            return obj.__dict__
        if isinstance(obj, ObjectResultHistory):
            return obj.__dict__
        if isinstance(obj, CaptureImage):
            return None
        # if isinstance(obj, BOTrack):
        #     return None
        if isinstance(obj, SCTrack):
            return None

        return super().default(obj)


def normalize_config_path(config_path):
    """
    Normalize configuration file path by adding 'configs/' prefix if not present.
    
    Args:
        config_path: Path to configuration file (string or Path object)
        
    Returns:
        Normalized path as string
        
    Examples:
        >>> normalize_config_path("my_config.json")
        "configs/my_config.json"
        >>> normalize_config_path("configs/existing.json")
        "configs/existing.json"
        >>> normalize_config_path("/absolute/path/config.json")
        "/absolute/path/config.json"
    """
    import os
    from pathlib import Path
    
    config_path_str = str(config_path)
    
    # If it's already an absolute path or already has configs/ prefix, return as is
    if os.path.isabs(config_path_str) or config_path_str.startswith("configs"):
        return config_path_str
    
    # Add configs/ prefix
    return os.path.join("configs", config_path_str)


# =============================================================================
# TEXT RENDERING UTILITIES
# =============================================================================

def pt_to_pixels(pt_size, dpi=96):
    """
    Convert points to pixels based on DPI.
    
    Args:
        pt_size: Font size in points
        dpi: Dots per inch (default: 96 for standard screen)
        
    Returns:
        Font size in pixels
    """
    return int(pt_size * dpi / 72.0)


def calculate_font_scale_for_resolution(font_size_pt, image_width, image_height, base_resolution=(1920, 1080)):
    """
    Calculate font scale based on image resolution.
    
    This function calculates an appropriate font scale for OpenCV's putText function
    based on the desired font size in points and the current image resolution.
    
    Args:
        font_size_pt: Desired font size in points
        image_width: Width of the image in pixels
        image_height: Height of the image in pixels
        base_resolution: Base resolution for scaling (default: 1920x1080)
        
    Returns:
        Font scale value for OpenCV putText function
    """
    # Convert points to pixels at 96 DPI
    font_size_px = pt_to_pixels(font_size_pt, dpi=96)
    
    # Calculate resolution factor based on image size
    # Use the smaller dimension to avoid oversized text on very wide/tall images
    image_min_dimension = min(image_width, image_height)
    base_min_dimension = min(base_resolution[0], base_resolution[1])
    
    # Calculate scaling factor
    resolution_factor = image_min_dimension / base_min_dimension
    
    # Apply resolution scaling to font size
    scaled_font_size_px = font_size_px * resolution_factor
    
    # Convert to OpenCV font scale (approximate conversion)
    # OpenCV font scale is roughly pixels / 30 for FONT_HERSHEY_SIMPLEX
    font_scale = scaled_font_size_px / 30.0
    
    # Ensure minimum and maximum reasonable values
    font_scale = max(0.1, min(font_scale, 10.0))
    
    return font_scale


def calculate_font_scale_simple(font_size_pt, image_width, image_height):
    """
    Simple font scale calculation based on image diagonal.
    
    Args:
        font_size_pt: Desired font size in points
        image_width: Width of the image in pixels
        image_height: Height of the image in pixels
        
    Returns:
        Font scale value for OpenCV putText function
    """
    # Convert points to pixels
    font_size_px = pt_to_pixels(font_size_pt, dpi=96)
    
    # Calculate image diagonal
    image_diagonal = (image_width ** 2 + image_height ** 2) ** 0.5
    
    # Base diagonal for 1920x1080
    base_diagonal = (1920 ** 2 + 1080 ** 2) ** 0.5
    
    # Calculate scaling factor
    scale_factor = image_diagonal / base_diagonal
    
    # Apply scaling and convert to OpenCV scale
    scaled_font_size_px = font_size_px * scale_factor
    font_scale = scaled_font_size_px / 30.0
    
    # Ensure reasonable bounds
    font_scale = max(0.1, min(font_scale, 10.0))
    
    return font_scale


def percent_to_pixels(percent, total_size):
    """
    Convert percentage to pixels.
    
    Args:
        percent: Percentage value (0.0 to 100.0)
        total_size: Total size in pixels
        
    Returns:
        Position in pixels
    """
    return int(percent * total_size / 100.0)


def calculate_text_size(text, font_face=cv2.FONT_HERSHEY_SIMPLEX, font_scale=1.0, thickness=1):
    """
    Calculate text size in pixels.
    
    Args:
        text: Text string
        font_face: OpenCV font face
        font_scale: Font scale
        thickness: Font thickness
        
    Returns:
        Tuple of (width, height) in pixels
    """
    (text_width, text_height), baseline = cv2.getTextSize(text, font_face, font_scale, thickness)
    return text_width, text_height + baseline


def get_adaptive_font_scale(text, target_width_px, font_face=cv2.FONT_HERSHEY_SIMPLEX, thickness=1):
    """
    Calculate font scale to fit text within target width.
    
    Args:
        text: Text string
        target_width_px: Target width in pixels
        font_face: OpenCV font face
        thickness: Font thickness
        
    Returns:
        Font scale that fits the text
    """
    # Start with scale 1.0 and reduce until text fits
    scale = 1.0
    while scale > 0.1:  # Minimum scale limit
        text_width, _ = calculate_text_size(text, font_face, scale, thickness)
        if text_width <= target_width_px:
            return scale
        scale *= 0.9
    return 0.1


def put_text_adaptive(image, text, position_percent, font_size_pt=12, font_face=cv2.FONT_HERSHEY_SIMPLEX, 
                     color=(255, 255, 255), thickness=None, background_color=None, padding_percent=2.0,
                     font_scale_method="resolution_based", base_resolution=(1920, 1080), background_enabled=True):
    """
    Draw text with adaptive positioning and sizing.
    
    Args:
        image: OpenCV image
        text: Text to draw
        position_percent: Position as (x_percent, y_percent) from top-left
        font_size_pt: Font size in points
        font_face: OpenCV font face
        color: Text color (B, G, R)
        thickness: Font thickness (auto-calculated if None)
        background_color: Background color for text (optional)
        padding_percent: Padding around text in percent of image width
        font_scale_method: Method for calculating font scale ("resolution_based" or "simple")
        base_resolution: Base resolution for scaling (width, height)
        background_enabled: Whether to draw background rectangle (True/False)
        
    Returns:
        Modified image
    """
    height, width = image.shape[:2]
    
    # Calculate font scale based on image resolution
    if font_scale_method == "simple":
        font_scale = calculate_font_scale_simple(font_size_pt, width, height)
    else:  # resolution_based
        font_scale = calculate_font_scale_for_resolution(font_size_pt, width, height, base_resolution)
    
    # Auto-calculate thickness if not provided
    if thickness is None:
        thickness = max(1, int(font_scale * 2))
    
    # Calculate position in pixels
    x_px = percent_to_pixels(position_percent[0], width)
    y_px = percent_to_pixels(position_percent[1], height)
    
    # Calculate text size
    text_width, text_height = calculate_text_size(text, font_face, font_scale, thickness)
    
    # Adjust position to ensure text fits within image bounds
    if x_px + text_width > width:
        x_px = width - text_width - 10
    if y_px - text_height < 0:
        y_px = text_height + 10
    
    # Draw background if specified and enabled
    if background_color and background_enabled:
        padding_px = percent_to_pixels(padding_percent, width)
        cv2.rectangle(image, 
                     (x_px - padding_px, y_px - text_height - padding_px),
                     (x_px + text_width + padding_px, y_px + padding_px),
                     background_color, -1)
    
    # Draw text
    cv2.putText(image, text, (x_px, y_px), font_face, font_scale, color, thickness)
    
    return image


def put_text_with_bbox(image, text, bbox, font_size_pt=12, font_face=cv2.FONT_HERSHEY_SIMPLEX,
                      color=(255, 255, 255), thickness=None, background_color=None, 
                      position_offset_percent=(0, -10), font_scale_method="resolution_based", 
                      base_resolution=(1920, 1080), background_enabled=True):
    """
    Draw text near a bounding box with adaptive positioning.
    
    Args:
        image: OpenCV image
        text: Text to draw
        bbox: Bounding box (x1, y1, x2, y2)
        font_size_pt: Font size in points
        font_face: OpenCV font face
        color: Text color (B, G, R)
        thickness: Font thickness (auto-calculated if None)
        background_color: Background color for text (optional)
        position_offset_percent: Offset from bbox in percent of image size
        font_scale_method: Method for calculating font scale ("resolution_based" or "simple")
        base_resolution: Base resolution for scaling (width, height)
        background_enabled: Whether to draw background rectangle (True/False)
        
    Returns:
        Modified image
    """
    height, width = image.shape[:2]
    
    # Calculate font scale based on image resolution
    if font_scale_method == "simple":
        font_scale = calculate_font_scale_simple(font_size_pt, width, height)
    else:  # resolution_based
        font_scale = calculate_font_scale_for_resolution(font_size_pt, width, height, base_resolution)
    
    # Auto-calculate thickness if not provided
    if thickness is None:
        thickness = max(1, int(font_scale * 2))
    
    # Calculate position relative to bbox
    x_offset = percent_to_pixels(position_offset_percent[0], width)
    y_offset = percent_to_pixels(position_offset_percent[1], height)
    
    x_px = int(bbox[0]) + x_offset
    y_px = int(bbox[1]) + y_offset
    
    # Ensure text doesn't go outside image bounds
    if x_px < 0:
        x_px = 10
    if y_px < 0:
        y_px = 10
    
    # Calculate text size
    text_width, text_height = calculate_text_size(text, font_face, font_scale, thickness)
    
    # Adjust if text would go outside image
    if x_px + text_width > width:
        x_px = width - text_width - 10
    if y_px - text_height < 0:
        y_px = text_height + 10
    
    # Draw background if specified and enabled
    if background_color and background_enabled:
        padding_px = 5
        cv2.rectangle(image, 
                     (x_px - padding_px, y_px - text_height - padding_px),
                     (x_px + text_width + padding_px, y_px + padding_px),
                     background_color, -1)
    
    # Draw text
    cv2.putText(image, text, (x_px, y_px), font_face, font_scale, color, thickness)
    
    return image


def get_default_text_config():
    """
    Get default text configuration.
    
    Returns:
        Dictionary with default text settings
    """
    return {
        "font_size_pt": 42,
        "font_face": cv2.FONT_HERSHEY_SIMPLEX,
        "color": (0, 0, 255),  # White
        "thickness": None,  # Auto-calculated
        "background_color": (0, 0, 0),  # No background
        "background_enabled": False,  # Enable/disable background
        "padding_percent": 2.0,
        "position_offset_percent": (0, -10),
        "font_scale_method": "resolution_based",  # "resolution_based" or "simple"
        "base_resolution": (1920, 1080)  # Base resolution for scaling
    }


def apply_text_config(text_config, default_config=None):
    """
    Apply text configuration with defaults.
    
    Args:
        text_config: User-provided text configuration
        default_config: Default configuration (optional)
        
    Returns:
        Merged configuration
    """
    if default_config is None:
        default_config = get_default_text_config()
    
    merged_config = default_config.copy()
    if text_config:
        merged_config.update(text_config)
    
    return merged_config
