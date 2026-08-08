# Документация тестов EvilEye

Автоматически сгенерированная документация всех тестов.

Всего тестов: 87

## Содержание

### INTEGRATION тесты

- [attributes](#integration-attributes)
- [botsort](#integration-botsort)
- [controller](#integration-controller)
- [database](#integration-database)
- [detection](#integration-detection)
- [gstreamer](#integration-gstreamer)
- [image_saving](#integration-image_saving)
- [journal](#integration-journal)
- [labeling](#integration-labeling)
- [opencv](#integration-opencv)
- [pipeline](#integration-pipeline)
- [postgresql](#integration-postgresql)
- [preprocessing](#integration-preprocessing)
- [registry](#integration-registry)
- [roi](#integration-roi)
- [text_rendering](#integration-text_rendering)
- [video_file](#integration-video_file)
- [zone](#integration-zone)

### UNIT тесты

- [attributes](#unit-attributes)
- [pipeline](#unit-pipeline)


## INTEGRATION тесты

### attributes

##### test_attributes_detection.py

Тесты для системы атрибутов: ROI, ассоциации, тайминги, FSM.

- **Путь**: `integration/attributes/test_attributes_detection.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_attribute_state_creation`: Создание состояния атрибута.
  - `test_reset_presence`: Сброс накопленных данных присутствия.
  - `test_manager_creation`: Создание менеджера атрибутов.
  - `test_get_states_empty`: Получение состояний для несуществующего трека.
  - `test_update_new_attribute`: Обновление нового атрибута.
  - `test_fsm_none_to_exists`: Переход состояния none -> exists.
  - `test_fsm_exists_to_lost`: Переход состояния exists -> lost.
  - `test_fsm_lost_to_none`: Переход состояния lost -> none.
  - `test_ema_smoothing`: Тест EMA-сглаживания confidence.
  - `test_remove_track`: Удаление трека.
  - `test_roi_feeder_creation`: Создание ROI-фидера.
  - `test_roi_feeder_interface`: Тест интерфейса ProcessorFrame.
  - `test_get_source_ids`: Получение списка source_ids.
  - `test_classifier_creation`: Создание классификатора.
  - `test_classifier_interface`: Тест интерфейса ProcessorFrame.
  - `test_classifier_get_source_ids`: Получение списка source_ids.
  - `test_objects_handler_attributes_config`: Конфигурация атрибутов в ObjectsHandler.
  - `test_put_attributes`: Тест метода put_attributes.
  - `test_put_attributes_empty`: Тест put_attributes с пустыми данными.

### botsort

##### test_botsort.py

- **Путь**: `integration/tracking/botsort/test_botsort.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_botsort`

##### test_object_tracking_botsort.py

- **Путь**: `integration/tracking/botsort/test_object_tracking_botsort.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_one_obj_one_frame`
  - `test_several_objects`: Check correctness of track id assignment 
    

### controller

##### test_cli_working_directory.py

Test script for CLI working directory behavior.

- **Путь**: `integration/controller/test_cli_working_directory.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_cli_working_directory`: Test that CLI commands run in the correct working directory.
  - `test_deploy_command`: Test deploy command working directory behavior.

##### test_data_flow.py

- **Путь**: `integration/controller/test_data_flow.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_data_flow`: Test data flow in the system

##### test_deploy_samples_update.py

Test script to verify the updated deploy-samples command functionality.

- **Путь**: `integration/controller/test_deploy_samples_update.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_sample_videos_config`: Test the updated sample videos configuration.
  - `test_sample_configs`: Test the updated sample configuration files.
  - `test_cli_deploy_samples`: Test the CLI deploy-samples command structure.
  - `test_download_function`: Test the download function with new video names.
  - `test_configuration_consistency`: Test that configurations are consistent with video files.

##### test_double_click_functionality.py

- **Путь**: `integration/controller/test_double_click_functionality.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_double_click_functionality`: Test double click functionality in JSON journal

##### test_frequent_updates.py

- **Путь**: `integration/controller/test_frequent_updates.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_frequent_updates`: Test frequent updates of JSON files

##### test_image_paths.py

- **Путь**: `integration/controller/test_image_paths.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_image_paths`: Test image paths in journal

##### test_load_config_no_db.py

Test loading configuration without database.

- **Путь**: `integration/controller/test_load_config_no_db.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_load_config`: Test loading configuration file without database.

##### test_minimal_no_db.py

- **Путь**: `integration/controller/test_minimal_no_db.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_minimal_init`: Test minimal controller initialization without database.

##### test_path_resolution.py

Test script to verify path resolution for working directory vs package directory.

- **Путь**: `integration/controller/test_path_resolution.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_path_resolution`: Test path resolution functions.
  - `test_model_paths`: Test model path resolution in detectors and trackers.
  - `test_database_paths`: Test database image directory resolution.
  - `test_gui_paths`: Test GUI icon path resolution.
  - `test_configuration_paths`: Test configuration file path resolution.

##### test_real_double_click.py

- **Путь**: `integration/controller/test_real_double_click.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_real_double_click`: Test real double click functionality in GUI

##### test_realtime_updates.py

- **Путь**: `integration/controller/test_realtime_updates.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_realtime_updates`: Test real-time updates in journal window

##### test_relative_paths.py

Test script for relative path resolution in EvilEye components.

- **Путь**: `integration/controller/test_relative_paths.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_detector_relative_paths`: Test relative path resolution in YOLO detector.
  - `test_tracker_relative_paths`: Test relative path resolution in Botsort tracker.
  - `test_database_relative_paths`: Test relative path resolution in database controller.
  - `test_config_loading`: Test loading configuration with relative paths.
  - `test_relative_paths`: Test relative paths in labeling data.
  - `test_path_usage_example`: Test how to use relative paths to access images.

### database

##### test_controller_no_database.py

- **Путь**: `integration/database/test_controller_no_database.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_controller_with_database`: Test controller with database enabled.
  - `test_controller_without_database`: Test controller with database disabled.
  - `test_controller_default_behavior`: Test controller default behavior (should use database by default).

##### test_database_connect.py

Тест подключения к базе данных.

- **Путь**: `integration/database/test_database_connect.py`
- **Модуль**: `evileye.database_controller`
- **Тестовые функции**:
  - `test_database_connect`: Тест подключения к базе данных.

##### test_no_database_fixes.py

- **Путь**: `integration/database/test_no_database_fixes.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_objects_handler_without_db`: Test ObjectsHandler without database.
  - `test_events_processor_without_db`: Test EventsProcessor without database.
  - `test_controller_integration`: Test controller integration without database.

##### test_simple_no_database.py

- **Путь**: `integration/database/test_simple_no_database.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_basic_controller`: Test basic controller creation and initialization.

### detection

##### test_background_option.py

Test script to demonstrate the background disable option.

- **Путь**: `integration/detection/test_background_option.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_background_options`: Test different background options.
  - `test_config_file_background_settings`: Test background settings from configuration files.

##### test_detection.py

- **Путь**: `integration/detection/test_detection.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_detection`: Test object detection with YOLO

### gstreamer

##### test_gstreamer_reconnect_recording.py

- **Путь**: `integration/capture/gstreamer/test_gstreamer_reconnect_recording.py`
- **Модуль**: `evileye.run_config_helper`
- **Тестовые функции**:
  - `test_gstreamer_reconnect_recording`: Test automatic connection to 3 cameras with recording using configs/poly-cameras-gstreamer.json.
Tests:
1. Automatic connection to 3 cameras at startup (Cam1, Cam2-Cam3, Cam4-Cam5)
2. Recording is enabled and files are created for all cameras
3. Reconnect after connection break (simulated)
  - `test_gstreamer_reconnect_loop_logic`: Test that _reconnect_loop continues after timeout.
This is a unit test to verify the reconnect loop logic works correctly.
  - `test_gstreamer_recording_branch_setup`: Test that _setup_recording_branch method exists and can be called.

##### test_gstreamer_rtsp_connection.py

Test RTSP connection to a lab camera (credentials from `EVILEYE_TEST_RTSP_*` env vars).
This test helps debug connection issues with GStreamer pipeline.

- **Путь**: `integration/capture/gstreamer/test_gstreamer_rtsp_connection.py`
- **Модуль**: `evileye.capture`
- **Тестовые функции**:
  - `test_rtsp_connection_specific_camera_tcp`: Test connection to specific RTSP camera using TCP protocol.
  - `test_rtsp_connection_specific_camera`: Test connection to specific RTSP camera (creds from env).
Records a short video fragment for verification.
  - `test_rtsp_pipeline_string_generation`: Test that pipeline string is generated correctly for RTSP camera.
  - `test_rtsp_connection_with_recording`: Test RTSP connection with recording enabled.
  - `test_rtsp_gst_launch_command`: Generate gst-launch-1.0 command for manual testing.
This helps debug connection issues by testing pipeline directly.

##### test_record_video_fragment.py

Test script to record a short video fragment from RTSP camera and return the path.

- **Путь**: `integration/capture/gstreamer/test_record_video_fragment.py`
- **Модуль**: `evileye.capture`
- **Тестовые функции**:
  - `test_record_video_fragment`

### image_saving

##### test_correct_image_saving.py

- **Путь**: `integration/image_saving/test_correct_image_saving.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_correct_image_saving`: Test correct image saving: preview with boxes, frame without boxes

##### test_final_image_saving.py

- **Путь**: `integration/image_saving/test_final_image_saving.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_final_image_saving`: Final test to verify correct image saving after all fixes

##### test_image_fixes.py

- **Путь**: `integration/image_saving/test_image_fixes.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_image_fixes`: Test image fixes: original images and bounding boxes

##### test_image_saving.py

- **Путь**: `integration/image_saving/test_image_saving.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_image_saving`: Test image saving without database

### journal

##### test_data_source.py

- **Путь**: `integration/journal/test_data_source.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_data_source`: Test data source functionality

##### test_gui_refactoring.py

Тесты для рефакторинга GUI EvilEye

Проверяют основную функциональность WindowManager, BaseWindow и диалогов.

- **Путь**: `integration/journal/test_gui_refactoring.py`
- **Модуль**: `evileye.visualization_modules`
- **Тестовые классы**:
  - `TestWindow`
  - `TestWindow`
  - `TestWindow`
  - `TestWindow`
- **Тестовые функции**:
  - `test_widget`: Fixture для тестового виджета.
  - `test_register_window`: Тест регистрации окна
  - `test_unregister_window`: Тест отмены регистрации окна
  - `test_window_state_management`: Тест управления состоянием окна
  - `test_unsaved_changes_tracking`: Тест отслеживания несохраненных изменений
  - `test_get_windows_by_type`: Тест получения окон по типу
  - `test_status_summary`: Тест получения сводки о состоянии
  - `test_base_window_creation`: Тест создания BaseWindow
  - `test_unsaved_changes_tracking_base_window`: Тест отслеживания несохраненных изменений в BaseWindow
  - `test_config_save_load`: Тест сохранения и загрузки конфигурации
  - `test_save_confirmation_dialog`: Тест диалога подтверждения сохранения
  - `test_save_as_dialog`: Тест диалога 'Сохранить как'
  - `test_window_manager_integration`: Тест интеграции WindowManager с BaseWindow
  - `test_global_window_manager`: Тест глобального WindowManager

##### test_journal_button.py

- **Путь**: `integration/journal/test_journal_button.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_journal_button_behavior`

##### test_journal_button_simple.py

- **Путь**: `integration/journal/test_journal_button_simple.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_journal_button_logic`: Test the journal button configuration logic without creating full windows

##### test_journal_columns_compatibility.py

- **Путь**: `integration/journal/test_journal_columns_compatibility.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_journal_columns_compatibility`: Test that JSON journal columns match database journal structure

##### test_journal_complete.py

- **Путь**: `integration/journal/test_journal_complete.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_journal_complete`: Complete journal test

##### test_journal_complete_verification.py

- **Путь**: `integration/journal/test_journal_complete_verification.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_journal_complete_verification`: Complete verification of journal functionality

##### test_journal_directory.py

- **Путь**: `integration/journal/test_journal_directory.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_journal_directory_behavior`: Test journal behavior with different directory scenarios

##### test_journal_filters.py

- **Путь**: `integration/journal/test_journal_filters.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_journal_filters`: Test journal filtering

##### test_journal_final.py

- **Путь**: `integration/journal/test_journal_final.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_journal_scenarios`: Test all journal scenarios

##### test_journal_final_complete.py

- **Путь**: `integration/journal/test_journal_final_complete.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_journal_final_complete`: Test all journal scenarios with the latest fixes

##### test_journal_final_fix.py

- **Путь**: `integration/journal/test_journal_final_fix.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_journal_final_fix`: Test journal with fixed file naming

##### test_journal_final_images.py

- **Путь**: `integration/journal/test_journal_final_images.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_journal_final_images`: Test journal with image display functionality

##### test_journal_final_no_gui.py

- **Путь**: `integration/journal/test_journal_final_no_gui.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_journal_final_no_gui`: Test journal functionality without GUI

##### test_journal_final_structure.py

- **Путь**: `integration/journal/test_journal_final_structure.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_journal_final_structure`: Test journal with correct folder structure

##### test_journal_fixes.py

- **Путь**: `integration/journal/test_journal_fixes.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_journal_fixes`: Test journal fixes for different event types and bounding boxes

##### test_journal_gui.py

- **Путь**: `integration/journal/test_journal_gui.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_journal_gui`: Test journal GUI with fixes

##### test_journal_images.py

- **Путь**: `integration/journal/test_journal_images.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_journal_images`

##### test_journal_mapping.py

- **Путь**: `integration/journal/test_journal_mapping.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_journal_mapping`: Test journal data mapping

##### test_journal_simple.py

- **Путь**: `integration/journal/test_journal_simple.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_journal_simple`: Simple test for journal fixes

##### test_journal_simple_gui.py

- **Путь**: `integration/journal/test_journal_simple_gui.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_journal_simple_gui`: Test journal GUI with simple data display

##### test_journal_time_and_double_click.py

- **Путь**: `integration/journal/test_journal_time_and_double_click.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_journal_time_and_double_click`: Test time formatting and double click functionality in JSON journal

##### test_journal_updated.py

- **Путь**: `integration/journal/test_journal_updated.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_journal_updated`: Test updated journal with new structure

##### test_journal_updates_when_open.py

- **Путь**: `integration/journal/test_journal_updates_when_open.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_journal_updates_when_open`: Test journal updates when window is open

##### test_journal_with_images.py

- **Путь**: `integration/journal/test_journal_with_images.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_journal_with_images`: Test journal with existing images

##### test_json_journal.py

- **Путь**: `integration/journal/test_json_journal.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_json_journal`

##### test_main_window_journal.py

- **Путь**: `integration/journal/test_main_window_journal.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_main_window_journal`

##### test_main_window_no_db.py

- **Путь**: `integration/journal/test_main_window_no_db.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_main_window_without_db`: Test MainWindow without database.
  - `test_main_window_with_db`: Test MainWindow with database enabled.

##### test_main_window_roi_integration.py

- **Путь**: `integration/journal/test_main_window_roi_integration.py`
- **Модуль**: `evileye.visualization_modules`
- **Тестовые функции**:
  - `test_apply_roi_to_detector_by_index`
  - `test_apply_roi_to_detector_by_source_match`
  - `test_get_rois_from_detector_pipeline_first`
  - `test_get_rois_from_params_fallback`

##### test_no_bounding_boxes_in_journal.py

- **Путь**: `integration/journal/test_no_bounding_boxes_in_journal.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_no_bounding_boxes_in_journal`: Test that bounding boxes are not displayed in the journal table

##### test_real_journal.py

- **Путь**: `integration/journal/test_real_journal.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_real_journal`

### labeling

##### test_labeling_improvements.py

Test script to verify improvements in the labeling system.

- **Путь**: `integration/labeling/test_labeling_improvements.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_new_structure`: Test new folder structure.
  - `test_pixel_coordinates`: Test pixel coordinate format.
  - `test_buffering`: Test buffering functionality.
  - `test_performance`: Test performance improvements.

##### test_labeling_system.py

Test script to verify the labeling system functionality.

- **Путь**: `integration/labeling/test_labeling_system.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_labeling_manager`: Test LabelingManager functionality.
  - `test_objects_handler_integration`: Test ObjectsHandler integration with labeling.
  - `test_labeling_format`: Test the labeling format structure.

##### test_object_id_counter.py

Test script for object_id counter initialization from existing JSON files.

- **Путь**: `integration/labeling/test_object_id_counter.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_labeling_manager`: Test LabelingManager's _get_max_object_id method.
  - `test_objects_handler`: Test ObjectsHandler's object_id counter initialization.

### opencv

##### test_recording_opencv.py

- **Путь**: `integration/capture/opencv/test_recording_opencv.py`
- **Модуль**: `evileye.capture`
- **Тестовые функции**:
  - `test_opencv_recording_basic`

### pipeline

##### test_pipeline_capture_config.py

Test script to verify PipelineCapture configuration.

- **Путь**: `integration/pipeline/test_pipeline_capture_config.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_pipeline_capture_config`: Test PipelineCapture configuration loading.
  - `test_pipeline_capture_usage`: Test PipelineCapture usage with configuration.

##### test_pipeline_capture_launch.py

Test script to verify PipelineCapture launch.

- **Путь**: `integration/pipeline/test_pipeline_capture_launch.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_pipeline_capture_launch`: Test PipelineCapture launch with configuration.
  - `test_pipeline_capture_with_controller`: Test PipelineCapture with controller initialization.

##### test_pipeline_capture_simple.py

Simple test for PipelineCapture with simplified initialization.

- **Путь**: `integration/pipeline/test_pipeline_capture_simple.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_pipeline_capture_simple`: Test PipelineCapture with simplified initialization.

##### test_pipeline_capture_sources.py

Test script to verify PipelineCapture get_sources method.

- **Путь**: `integration/pipeline/test_pipeline_capture_sources.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_pipeline_capture_sources`: Test PipelineCapture get_sources functionality.
  - `test_pipeline_capture_controller_compatibility`: Test that PipelineCapture is compatible with controller.

##### test_pipeline_inheritance.py

- **Путь**: `integration/pipeline/test_pipeline_inheritance.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_pipeline_inheritance`: Test PipelineCapture inheritance chain.
  - `test_pipeline_discovery`: Test pipeline discovery mechanism.

##### test_pipeline_refactoring.py

Test script to verify pipeline refactoring.

- **Путь**: `integration/pipeline/test_pipeline_refactoring.py`
- **Модуль**: `evileye.core`
- **Тестовые классы**:
  - `TestPipeline`
  - `TestSimplePipeline`
- **Тестовые функции**:
  - `test_pipeline_base`: Test PipelineBase functionality.
  - `test_pipeline_simple`: Test PipelineSimple functionality.
  - `test_pipeline_capture`: Test PipelineCapture functionality.
  - `test_pipeline_processors`: Test PipelineProcessors functionality.
  - `test_pipeline_hierarchy`: Test pipeline class hierarchy.

### postgresql

##### test_database_connect.py

Тест подключения к PostgreSQL базе данных.

- **Путь**: `integration/database/postgresql/test_database_connect.py`
- **Модуль**: `evileye.database_controller`
- **Тестовые функции**:
  - `test_database_connect`: Тест подключения к PostgreSQL базе данных.

### preprocessing

##### test_preprocessing_base.py

- **Путь**: `integration/preprocessing/test_preprocessing_base.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_preprocessing_base`: Test PreprocessingBase inheritance.
  - `test_preprocessing_pipeline`: Test PreprocessingPipeline registration.

##### test_preprocessing_vehicle_usage.py

- **Путь**: `integration/preprocessing/test_preprocessing_vehicle_usage.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_preprocessing_pipeline_creation`: Test creating PreprocessingPipeline through registry.
  - `test_processor_frame_with_preprocessing`: Test ProcessorFrame with PreprocessingPipeline.
  - `test_controller_with_preprocessing`: Test controller with preprocessing.

### registry

##### test_registry.py

- **Путь**: `integration/registry/test_registry.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_registry_before_imports`: Test registry before importing preprocessing module.
  - `test_registry_after_imports`: Test registry after importing preprocessing module.
  - `test_direct_import`: Test direct import of PreprocessingPipeline.
  - `test_import_order`: Test different import orders.
  - `test_controller_imports`: Test what controller imports.

##### test_registry_debug.py

- **Путь**: `integration/registry/test_registry_debug.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_registry_debug`: Debug registry registration.
  - `test_import_evileye_preprocessing`: Test importing evileye.preprocessing directly.

### roi

##### test_roi_core.py

- **Путь**: `integration/roi/test_roi_core.py`
- **Модуль**: `evileye.visualization_modules`
- **Тестовые функции**:
  - `test_add_and_get_rois`
  - `test_resize_roi_updates_data`

##### test_roi_window_integration.py

- **Путь**: `integration/roi/test_roi_window_integration.py`
- **Модуль**: `evileye.visualization_modules`
- **Тестовые функции**:
  - `test_window_set_image_and_load_rois`

### text_rendering

##### test_font_scaling.py

Test script for the improved font scaling system.
Demonstrates resolution-based font scaling vs the old hardcoded method.

- **Путь**: `integration/text_rendering/test_font_scaling.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_font_scaling_comparison`: Compare different font scaling methods.
  - `test_visual_comparison`: Create visual comparison of different scaling methods.
  - `test_resolution_independence`: Test that text appears similar size across different resolutions.
  - `test_edge_cases`: Test edge cases and extreme resolutions.

##### test_text_config_application.py

Test script to verify that text_config is properly applied from configuration.

- **Путь**: `integration/text_rendering/test_text_config_application.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_text_config_from_file`: Test text_config loading from sample configuration files.
  - `test_default_config`: Test default text configuration.
  - `test_config_merging`: Test merging of user config with defaults.
  - `test_visualizer_integration`: Test that visualizer properly receives text_config.

##### test_text_rendering.py

Test script for the new text rendering system.
Demonstrates adaptive text positioning and sizing.

- **Путь**: `integration/text_rendering/test_text_rendering.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_text_rendering`: Test different text rendering scenarios.
  - `test_text_config`: Test text configuration system.
  - `test_edge_cases`: Test edge cases and error handling.

### video_file

##### test_retention.py

- **Путь**: `integration/capture/video_file/test_retention.py`
- **Модуль**: `evileye.video_recorder`
- **Тестовые функции**:
  - `test_retention_enforce`

### zone

##### test_zone_events_db_adapter.py

- **Путь**: `integration/events/zone/test_zone_events_db_adapter.py`
- **Модуль**: `evileye.events_detectors`
- **Тестовые функции**:
  - `test_zone_events_db_adapter_insert_and_update`

##### test_zone_events_db_real.py

- **Путь**: `integration/events/zone/test_zone_events_db_real.py`
- **Модуль**: `evileye.database_controller`
- **Тестовые функции**:
  - `test_zone_events_real_db_insert_update`

##### test_zone_events_detector.py

- **Путь**: `integration/events/zone/test_zone_events_detector.py`
- **Модуль**: `evileye.events_detectors`
- **Тестовые функции**:
  - `test_zone_event_generated_after_threshold`
  - `test_zone_no_event_if_below_threshold`


## UNIT тесты

### attributes

##### test_attributes_detection.py

Тесты для системы атрибутов: ROI, ассоциации, тайминги, FSM.

- **Путь**: `unit/attributes/test_attributes_detection.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_attribute_state_creation`: Создание состояния атрибута.
  - `test_reset_presence`: Сброс накопленных данных присутствия.
  - `test_manager_creation`: Создание менеджера атрибутов.
  - `test_get_states_empty`: Получение состояний для несуществующего трека.
  - `test_update_new_attribute`: Обновление нового атрибута.
  - `test_fsm_none_to_exists`: Переход состояния none -> exists.
  - `test_fsm_exists_to_lost`: Переход состояния exists -> lost.
  - `test_fsm_lost_to_none`: Переход состояния lost -> none.
  - `test_ema_smoothing`: Тест EMA-сглаживания confidence.
  - `test_remove_track`: Удаление трека.
  - `test_roi_feeder_creation`: Создание ROI-фидера.
  - `test_roi_feeder_interface`: Тест интерфейса ProcessorFrame.
  - `test_get_source_ids`: Получение списка source_ids.
  - `test_classifier_creation`: Создание классификатора.
  - `test_classifier_interface`: Тест интерфейса ProcessorFrame.
  - `test_classifier_get_source_ids`: Получение списка source_ids.
  - `test_objects_handler_attributes_config`: Конфигурация атрибутов в ObjectsHandler.
  - `test_put_attributes`: Тест метода put_attributes.
  - `test_put_attributes_empty`: Тест put_attributes с пустыми данными.

### pipeline

##### test_pipeline_base_methods.py

- **Путь**: `unit/pipeline/test_pipeline_base_methods.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_pipeline_base_abstract_methods`: Test that PipelineBase has required abstract methods.
  - `test_pipeline_simple_implementation`: Test that PipelineSimple implements abstract methods.
  - `test_pipeline_processors_implementation`: Test that PipelineProcessors implements abstract methods.
  - `test_pipeline_capture_implementation`: Test that PipelineCapture implements abstract methods.

##### test_pipeline_registration.py

- **Путь**: `unit/pipeline/test_pipeline_registration.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_pipeline_registration`: Test that PipelineCapture is properly registered.
  - `test_pipeline_imports`: Test that all pipeline imports work correctly.

##### test_preprocessing_pipeline_usage.py

- **Путь**: `unit/pipeline/test_preprocessing_pipeline_usage.py`
- **Модуль**: `evileye.core`
- **Тестовые функции**:
  - `test_preprocessing_pipeline_creation`: Test creating PreprocessingPipeline through registry.
  - `test_processor_frame_with_preprocessing`: Test ProcessorFrame with PreprocessingPipeline.
  - `test_controller_with_preprocessing`: Test controller with preprocessing.

