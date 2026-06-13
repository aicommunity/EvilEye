# Database Option in Controller

## Overview

The EvilEye controller now supports an optional `use_database` parameter that allows the system to run without a database connection. This is useful for:

- Development and testing without database setup
- Demo scenarios where database persistence is not needed
- Systems where database connectivity is not available
- Performance testing without database overhead

## Configuration

### Enable Database (Default Behavior)

```json
{
  "controller": {
    "use_database": true,
    "fps": 30
  }
}
```

### Disable Database

```json
{
  "controller": {
    "use_database": false,
    "fps": 30
  }
}
```

### Default Value

If `use_database` is not specified in the configuration, it defaults to `true` for backward compatibility.

## Behavior Changes

### When `use_database: true` (Default)

- Database controller is initialized
- Database adapters are created
- Object handler uses database for persistence
- Events are saved to database
- Memory consumption includes database components
- Database journal window is available in GUI

### When `use_database: false`

- Database controller is NOT initialized (`db_controller = None`)
- Database adapters are NOT created
- Object handler works without database (in-memory only)
- Events are processed but not saved to database
- Memory consumption excludes database components
- Database journal window is NOT created (GUI button is disabled)
- Console message: "Database functionality disabled. Running without database connection."

## Components Affected

### Database Components (Disabled when `use_database: false`)

- `DatabaseControllerPg`
- `DatabaseAdapterObjects`
- `DatabaseAdapterCamEvents`
- `DatabaseAdapterFieldOfViewEvents`
- `DatabaseAdapterZoneEvents`
- `DatabaseJournalWindow`

### Components That Still Work

- `ObjectsHandler` (without database persistence)
- `CamEventsDetector`
- `FieldOfViewEventsDetector`
- `ZoneEventsDetector`
- `EventsProcessor` (without database adapters)
- `EventsDetectorsController`
- All pipeline components (sources, preprocessors, detectors, trackers)
- Main GUI window (without database journal)

## Implementation Details

### New Methods Added

- `_init_object_handler_without_db()` - Initializes object handler without database
- `_init_events_detectors_without_db()` - Initializes events detectors without database
- `_init_events_processor_without_db()` - Initializes events processor without database

### Modified Methods

- `init()` - Now checks `use_database` before initializing database components
- `update_params()` - Handles database config updates conditionally
- `collect_memory_consumption()` - Only collects database memory if database is enabled
- `start()` - Only starts database components if database is enabled
- `stop()` - Only stops database components if database is enabled

### Components Fixed for No-Database Operation

#### ObjectsHandler
- **Problem**: Tried to access `db_controller.get_params()` and `db_controller.get_cameras_params()` when `db_controller` was `None`
- **Fix**: Added null checks and fallback to empty dictionaries
- **Problem**: Called `db_adapter.insert()` and `db_adapter.update()` when `db_adapter` was `None`
- **Fix**: Added null checks before calling database adapter methods
- **Problem**: Called `db_controller.get_project_id()` and `db_controller.get_job_id()` when `db_controller` was `None`
- **Fix**: Added null checks with fallback to `0`
- **Problem**: Accessed `db_params['image_dir']` when `db_params` was empty
- **Fix**: Added fallback to default directory `'EvilEyeData'`

#### EventsProcessor
- **Problem**: Called `db_controller.query()` when `db_controller` was `None`
- **Fix**: Added null checks in `get_last_id()` method
- **Problem**: Called `events_adapters[event.get_name()].insert()` when adapters were empty
- **Fix**: Added checks for adapter existence before calling methods

#### Controller
- **Problem**: Called `db_controller.connect()` and `db_adapter.start()` when database was disabled
- **Fix**: Added conditional checks in `start()` and `stop()` methods
- **Problem**: Tried to load database configuration when database was disabled
- **Fix**: Moved database configuration loading inside `use_database` check

#### MainWindow (GUI)
- **Problem**: Created `DatabaseJournalWindow` even when database was disabled, causing exceptions
- **Fix**: Added conditional creation of `DatabaseJournalWindow` based on `use_database` flag
- **Problem**: Database journal action was still enabled when database was disabled
- **Fix**: Disabled database journal action and added tooltip when database is disabled
- **Problem**: Called `db_journal_win.close()` when window was `None`
- **Fix**: Added null checks before closing database journal window

#### DatabaseJournalWindow
- **Problem**: Tried to access database configuration keys when database was disabled
- **Fix**: Added validation to prevent creation without proper database configuration

### Backward Compatibility

- Default value is `true` to maintain existing behavior
- All existing configurations will work without modification
- Database functionality is fully preserved when enabled

## Example Configuration

### Minimal Configuration Without Database

```json
{
  "controller": {
    "use_database": false,
    "fps": 30,
    "show_main_gui": false,
    "show_journal": false
  },
  "sources": [
    {
      "source": "VideoFile",
      "source_ids": [0],
      "file_path": "videos/sample_video.mp4"
    }
  ],
  "pipeline": {
    "pipeline_class": "PipelineSurveillance"
  },
  "objects_handler": {
    "max_objects": 100
  },
  "events_detectors": {
    "CamEventsDetector": {
      "enabled": false
    },
    "FieldOfViewEventsDetector": {
      "enabled": false
    },
    "ZoneEventsDetector": {
      "enabled": false
    }
  },
  "events_processor": {
    "enabled": false
  },
  "visualizer": {
    "gui_enabled": false
  }
}
```

## Use Cases

### Development and Testing

```json
{
  "controller": {
    "use_database": false
  }
}
```

### Production with Database

```json
{
  "controller": {
    "use_database": true
  }
}
```

### Conditional Configuration

You can use environment variables or configuration management to conditionally enable/disable database:

```python
import os

config = {
    "controller": {
        "use_database": os.getenv("USE_DATABASE", "true").lower() == "true"
    }
}
```

## Performance Impact

### With Database Disabled

- Faster startup time (no database connection)
- Lower memory usage (no database components)
- No database I/O overhead
- Suitable for real-time processing without persistence
- GUI works without database journal functionality

### With Database Enabled

- Full persistence and data retention
- Event logging and historical data
- Database query capabilities
- Standard production behavior
- Full GUI functionality including database journal

## Troubleshooting

### Common Issues

1. **Configuration not recognized**: Ensure `use_database` is in the `controller` section
2. **Database still initializing**: Check that `use_database` is set to `false`
3. **Missing components**: Verify that required components are properly configured
4. **GUI database journal error**: Ensure `use_database` is `false` to disable database journal

### Debug Information

When database is disabled, the controller will print:
```
Database functionality disabled. Running without database connection.
```

### Testing

Use the provided test scripts to verify no-database functionality:

```bash
python test_no_database_fixes.py
python test_main_window_no_db.py
```

These will test:
- ObjectsHandler without database
- EventsProcessor without database
- Controller integration without database
- MainWindow without database
- Database journal window handling

## Migration Guide

### From Previous Versions

No migration required. The default behavior remains the same.

### To Disable Database

Simply add `"use_database": false` to your controller configuration.

### To Enable Database

Either set `"use_database": true` or remove the parameter (defaults to `true`).

## Technical Notes

### Null Safety

All components now properly handle `None` database controllers and adapters:
- ObjectsHandler gracefully handles missing database
- EventsProcessor works with empty adapter lists
- Controller skips database operations when disabled
- MainWindow handles missing database journal window

### Memory Management

When database is disabled:
- No database connection pools are created
- No database adapters consume memory
- Object tracking still works in memory
- Events are processed but not persisted
- GUI components are reduced (no database journal)

### Image Storage

When database is disabled:
- Images are still saved to local filesystem
- Default directory is `'EvilEyeData'`
- Directory structure is maintained for compatibility

### GUI Behavior

When database is disabled:
- Database journal button is disabled with tooltip
- Database journal window is not created
- Main GUI functionality remains intact
- Zone management and other features still work
