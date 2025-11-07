# Покрытие модулей тестами

Статистика покрытия модулей тестами.

## По модулям

### capture

Тестов: 3

- `test_gstreamer_rtsp_connection.py` (integration)
- `test_record_video_fragment.py` (integration)
- `test_recording_opencv.py` (integration)

### core

Тестов: 73

- `test_attributes_detection.py` (unit)
- `test_attributes_detection.py` (integration)
- `test_background_option.py` (integration)
- `test_botsort.py` (integration)
- `test_cli_working_directory.py` (integration)
- `test_controller_no_database.py` (integration)
- `test_correct_image_saving.py` (integration)
- `test_data_flow.py` (integration)
- `test_data_source.py` (integration)
- `test_deploy_samples_update.py` (integration)
- `test_detection.py` (integration)
- `test_double_click_functionality.py` (integration)
- `test_final_image_saving.py` (integration)
- `test_font_scaling.py` (integration)
- `test_frequent_updates.py` (integration)
- `test_image_fixes.py` (integration)
- `test_image_paths.py` (integration)
- `test_image_saving.py` (integration)
- `test_journal_button.py` (integration)
- `test_journal_button_simple.py` (integration)
- `test_journal_columns_compatibility.py` (integration)
- `test_journal_complete.py` (integration)
- `test_journal_complete_verification.py` (integration)
- `test_journal_directory.py` (integration)
- `test_journal_filters.py` (integration)
- `test_journal_final.py` (integration)
- `test_journal_final_complete.py` (integration)
- `test_journal_final_fix.py` (integration)
- `test_journal_final_images.py` (integration)
- `test_journal_final_no_gui.py` (integration)
- `test_journal_final_structure.py` (integration)
- `test_journal_fixes.py` (integration)
- `test_journal_gui.py` (integration)
- `test_journal_images.py` (integration)
- `test_journal_mapping.py` (integration)
- `test_journal_simple.py` (integration)
- `test_journal_simple_gui.py` (integration)
- `test_journal_time_and_double_click.py` (integration)
- `test_journal_updated.py` (integration)
- `test_journal_updates_when_open.py` (integration)
- `test_journal_with_images.py` (integration)
- `test_json_journal.py` (integration)
- `test_labeling_improvements.py` (integration)
- `test_labeling_system.py` (integration)
- `test_load_config_no_db.py` (integration)
- `test_main_window_journal.py` (integration)
- `test_main_window_no_db.py` (integration)
- `test_minimal_no_db.py` (integration)
- `test_no_bounding_boxes_in_journal.py` (integration)
- `test_no_database_fixes.py` (integration)
- `test_object_id_counter.py` (integration)
- `test_object_tracking_botsort.py` (integration)
- `test_path_resolution.py` (integration)
- `test_pipeline_base_methods.py` (unit)
- `test_pipeline_capture_config.py` (integration)
- `test_pipeline_capture_launch.py` (integration)
- `test_pipeline_capture_simple.py` (integration)
- `test_pipeline_capture_sources.py` (integration)
- `test_pipeline_inheritance.py` (integration)
- `test_pipeline_refactoring.py` (integration)
- `test_pipeline_registration.py` (unit)
- `test_preprocessing_base.py` (integration)
- `test_preprocessing_pipeline_usage.py` (unit)
- `test_preprocessing_vehicle_usage.py` (integration)
- `test_real_double_click.py` (integration)
- `test_real_journal.py` (integration)
- `test_realtime_updates.py` (integration)
- `test_registry.py` (integration)
- `test_registry_debug.py` (integration)
- `test_relative_paths.py` (integration)
- `test_simple_no_database.py` (integration)
- `test_text_config_application.py` (integration)
- `test_text_rendering.py` (integration)

### database_controller

Тестов: 3

- `test_database_connect.py` (integration)
- `test_database_connect.py` (integration)
- `test_zone_events_db_real.py` (integration)

### events_detectors

Тестов: 2

- `test_zone_events_db_adapter.py` (integration)
- `test_zone_events_detector.py` (integration)

### run_config_helper

Тестов: 1

- `test_gstreamer_reconnect_recording.py` (integration)

### video_recorder

Тестов: 1

- `test_retention.py` (integration)

### visualization_modules

Тестов: 4

- `test_gui_refactoring.py` (integration)
- `test_main_window_roi_integration.py` (integration)
- `test_roi_core.py` (integration)
- `test_roi_window_integration.py` (integration)

## Статистика по типам

- **integration**: 83
- **unit**: 4

## Статистика по категориям

- **attributes**: 2
- **botsort**: 2
- **controller**: 12
- **database**: 4
- **detection**: 2
- **gstreamer**: 3
- **image_saving**: 4
- **journal**: 31
- **labeling**: 3
- **opencv**: 1
- **pipeline**: 9
- **postgresql**: 1
- **preprocessing**: 2
- **registry**: 2
- **roi**: 2
- **text_rendering**: 3
- **video_file**: 1
- **zone**: 3
