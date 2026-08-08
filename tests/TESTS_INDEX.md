# Индекс тестов EvilEye

Краткий индекс всех тестов по модулям.

## MP refactor (unit)

| File | Module |
|------|--------|
| `unit/core/test_mp_async_bridge.py` | MpAsyncBridge FIFO |
| `unit/object_detector/test_detection_thread_yolo_mp_async.py` | Detection MP order |
| `unit/object_tracker/test_botsort_parent_init.py` | R6 parent init |
| `unit/capture/test_queue_policy.py` | queue_policy |

Gate: `scripts/soak_mp_memory.sh`, `reports/mp_refactor_gate/`. Runbook: [docs/diploma_benchmark_methodology.md](../../docs/diploma_benchmark_methodology.md).

## INTEGRATION тесты

### attributes

- `test_attributes_detection.py` - Тесты для системы атрибутов: ROI, ассоциации, тайминги, FSM.

### botsort

- `test_botsort.py`
- `test_object_tracking_botsort.py`

### controller

- `test_cli_working_directory.py` - Test script for CLI working directory behavior.
- `test_data_flow.py`
- `test_deploy_samples_update.py` - Test script to verify the updated deploy-samples command functionality.
- `test_double_click_functionality.py`
- `test_frequent_updates.py`
- `test_image_paths.py`
- `test_load_config_no_db.py` - Test loading configuration without database.
- `test_minimal_no_db.py`
- `test_path_resolution.py` - Test script to verify path resolution for working directory vs package directory
- `test_real_double_click.py`
- `test_realtime_updates.py`
- `test_relative_paths.py` - Test script for relative path resolution in EvilEye components.

### database

- `test_controller_no_database.py`
- `test_database_connect.py` - Тест подключения к базе данных.
- `test_no_database_fixes.py`
- `test_simple_no_database.py`

### detection

- `test_background_option.py` - Test script to demonstrate the background disable option.
- `test_detection.py`

### gstreamer

- `test_gstreamer_reconnect_recording.py`
- `test_gstreamer_rtsp_connection.py` - Test RTSP connection to a lab camera (creds via EVILEYE_TEST_RTSP_* env)
- `test_record_video_fragment.py` - Test script to record a short video fragment from RTSP camera and return the pat

### image_saving

- `test_correct_image_saving.py`
- `test_final_image_saving.py`
- `test_image_fixes.py`
- `test_image_saving.py`

### journal

- `test_data_source.py`
- `test_gui_refactoring.py` - Тесты для рефакторинга GUI EvilEye
- `test_journal_button.py`
- `test_journal_button_simple.py`
- `test_journal_columns_compatibility.py`
- `test_journal_complete.py`
- `test_journal_complete_verification.py`
- `test_journal_directory.py`
- `test_journal_filters.py`
- `test_journal_final.py`
- `test_journal_final_complete.py`
- `test_journal_final_fix.py`
- `test_journal_final_images.py`
- `test_journal_final_no_gui.py`
- `test_journal_final_structure.py`
- `test_journal_fixes.py`
- `test_journal_gui.py`
- `test_journal_images.py`
- `test_journal_mapping.py`
- `test_journal_simple.py`
- `test_journal_simple_gui.py`
- `test_journal_time_and_double_click.py`
- `test_journal_updated.py`
- `test_journal_updates_when_open.py`
- `test_journal_with_images.py`
- `test_json_journal.py`
- `test_main_window_journal.py`
- `test_main_window_no_db.py`
- `test_main_window_roi_integration.py`
- `test_no_bounding_boxes_in_journal.py`
- `test_real_journal.py`

### labeling

- `test_labeling_improvements.py` - Test script to verify improvements in the labeling system.
- `test_labeling_system.py` - Test script to verify the labeling system functionality.
- `test_object_id_counter.py` - Test script for object_id counter initialization from existing JSON files.

### opencv

- `test_recording_opencv.py`

### pipeline

- `test_pipeline_capture_config.py` - Test script to verify PipelineCapture configuration.
- `test_pipeline_capture_launch.py` - Test script to verify PipelineCapture launch.
- `test_pipeline_capture_simple.py` - Simple test for PipelineCapture with simplified initialization.
- `test_pipeline_capture_sources.py` - Test script to verify PipelineCapture get_sources method.
- `test_pipeline_inheritance.py`
- `test_pipeline_refactoring.py` - Test script to verify pipeline refactoring.

### postgresql

- `test_database_connect.py` - Тест подключения к PostgreSQL базе данных.

### preprocessing

- `test_preprocessing_base.py`
- `test_preprocessing_vehicle_usage.py`

### registry

- `test_registry.py`
- `test_registry_debug.py`

### roi

- `test_roi_core.py`
- `test_roi_window_integration.py`

### text_rendering

- `test_font_scaling.py` - Test script for the improved font scaling system.
- `test_text_config_application.py` - Test script to verify that text_config is properly applied from configuration.
- `test_text_rendering.py` - Test script for the new text rendering system.

### video_file

- `test_retention.py`

### zone

- `test_zone_events_db_adapter.py`
- `test_zone_events_db_real.py`
- `test_zone_events_detector.py`

## UNIT тесты

### attributes

- `test_attributes_detection.py` - Тесты для системы атрибутов: ROI, ассоциации, тайминги, FSM.

### pipeline

- `test_pipeline_base_methods.py`
- `test_pipeline_registration.py`
- `test_preprocessing_pipeline_usage.py`

