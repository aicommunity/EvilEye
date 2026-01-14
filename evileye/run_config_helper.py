import json
import os
import sys
from pathlib import Path
from typing import Optional

try:
    from PyQt6.QtWidgets import QApplication, QMessageBox
    from PyQt6.QtCore import QEventLoop, Qt, QTimer
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import QApplication, QMessageBox
    from PyQt5.QtCore import QEventLoop, Qt, QTimer
    pyqt_version = 5

from evileye.controller import controller
from evileye.visualization_modules.main_window import MainWindow
from evileye.visualization_modules.startup_progress_window import StartupProgressWindow
from evileye.visualization_modules.controller_init_thread import ControllerInitThread
from evileye.utils.utils import normalize_config_path
from evileye.core.logger import get_module_logger
from evileye.gui import GUIManager, GUIMode, determine_gui_mode


def run_config(config_path: str, gui: bool = True, autoclose: bool = False) -> int:
    """Run EvilEye configuration using provided configuration.

    Args:
        config_path: Path to configuration file
        gui: CLI flag for GUI (True/False/None). If None, determined from config.
        autoclose: Auto-close when video ends
        
    Returns:
        Qt application exit code (0 for success)
    """
    logger = get_module_logger("run_config")

    config_file_name = normalize_config_path(config_path)
    config_dir = os.path.dirname(os.path.abspath(config_file_name))
    if config_dir:
        if os.path.basename(config_dir) == 'configs':
            parent_dir = os.path.dirname(config_dir)
            os.chdir(parent_dir)
            logger.info(f"Changed working directory to parent of configs folder: {parent_dir}")
        else:
            os.chdir(config_dir)
            logger.info(f"Changed working directory to: {config_dir}")

    with open(config_file_name) as config_file:
        config_data = json.load(config_file)

    logger.info("Configuration loaded successfully")

    # Ensure controller section exists
    controller_cfg = config_data.setdefault("controller", {})

    # Scheduled restart defaults (used by CLI-level scheduler and potential future GUI integration)
    sched_cfg = controller_cfg.setdefault("scheduled_restart", {})
    sched_cfg.setdefault("enabled", False)
    sched_cfg.setdefault("mode", "daily_time")          # daily_time | interval
    sched_cfg.setdefault("time", "01:00")               # HH:MM, local time
    sched_cfg.setdefault("interval_minutes", 0)         # used for interval mode
    
    # Determine GUI mode from config and CLI arguments
    gui_mode = determine_gui_mode(config_data, cli_gui=gui if gui is not None else None)
    logger.info(f"GUI mode determined: {gui_mode.value}")

    if autoclose:
        # Disable looping for all sources so that video files actually finish
        sources = config_data.get("pipeline", {}).get("sources", [])
        for source in sources:
            source["loop_play"] = False
        # Ensure controller section exists and propagate autoclose flag
        controller_cfg["autoclose"] = True
        logger.info("Auto-close enabled (loop_play disabled, controller.autoclose=True)")

    # No CLI recording overrides; use only config

    # Step 1: Initialize core (Controller) - always done first
    logger.info("Step 1: Initializing core system (Controller)")
    
    # Create initialization thread for core components
    init_thread = ControllerInitThread(config_data)
    initialization_result = {'controller': None, 'error': None, 'completed': False}
    
    # Progress callback for initialization
    progress_callback = None
    progress_window = None
    qt_app = None
    
    # Step 2: Initialize GUI based on mode
    gui_manager = None
    qt_app = None
    
    if gui_mode == GUIMode.HEADLESS:
        logger.info("Headless mode: skipping GUI initialization")
        # No GUI components, no QApplication
    else:
        # Create GUI manager for HIDDEN or VISIBLE modes
        logger.info(f"Step 2: Initializing GUI (mode: {gui_mode.value})")
        gui_manager = GUIManager(gui_mode, config_data, logger=logger)
        qt_app = gui_manager.create_gui_application()
        
        # Show progress window only in VISIBLE mode
        if gui_mode == GUIMode.VISIBLE:
            progress_window = StartupProgressWindow()
            progress_window.show()
            progress_window.raise_()
            qt_app.processEvents()
            logger.info("Progress window displayed")
            
            def on_progress_updated(value, stage_text):
                if progress_window:
                    progress_window.update_progress(value, stage_text)
                    qt_app.processEvents()
            progress_callback = on_progress_updated
    
    # Set progress callback for controller initialization
    if progress_callback:
        init_thread.progress_updated.connect(progress_callback)
    
    main_window_created = {'done': False}
    
    def on_initialization_complete(controller_instance):
        initialization_result['controller'] = controller_instance
        initialization_result['completed'] = True
        logger.info("Controller initialization completed")
        
        # Step 3: Connect GUI to controller (if GUI mode)
        if gui_mode != GUIMode.HEADLESS and gui_manager:
            try:
                logger.info("Step 3: Connecting GUI to controller")
                _connect_gui_to_controller(
                    controller_instance, config_file_name, config_data, 
                    gui_manager, logger, progress_window
                )
                logger.info("GUI connected to controller successfully")
                main_window_created['done'] = True
            except Exception as e:
                logger.error(f"Error connecting GUI to controller: {e}", exc_info=True)
                main_window_created['done'] = True
                raise
        else:
            # Headless mode: just start controller
            logger.info("Starting controller (headless mode)")
            controller_instance.start()
            main_window_created['done'] = True
    
    def on_initialization_failed(error_message):
        initialization_result['error'] = error_message
        initialization_result['completed'] = True
        main_window_created['done'] = True
        if progress_window:
            progress_window.close()
        logger.error(f"Controller initialization failed: {error_message}")
        if gui_mode != GUIMode.HEADLESS:
            QMessageBox.critical(None, "Initialization Error", 
                               f"Failed to initialize application:\n\n{error_message}")
        sys.exit(1)
    
    init_thread.initialization_complete.connect(on_initialization_complete)
    init_thread.initialization_failed.connect(on_initialization_failed)
    
    # Start core initialization
    logger.info("Starting controller initialization in background thread")
    init_thread.start()
    
    # Wait for initialization to complete
    if qt_app:
        # GUI mode: process events while waiting
        while not initialization_result['completed'] or not main_window_created['done']:
            qt_app.processEvents()
    else:
        # Headless mode: just wait (no event loop)
        import time
        while not initialization_result['completed'] or not main_window_created['done']:
            time.sleep(0.01)
    
    # Check result
    if initialization_result['error']:
        logger.error("Controller initialization failed")
        sys.exit(1)
    
    controller_instance = initialization_result['controller']
    
    # Step 4: Start application event loop
    if gui_mode == GUIMode.HEADLESS:
        logger.info("Headless mode: no visible GUI, starting minimal event loop")
        # In headless mode, controller runs until sources end; we still need a minimal
        # Qt event loop for timers and signal delivery.
        try:
            import os as _os
            _os.environ.setdefault("QT_NO_GLIB", "1")
        except Exception:
            pass
        qt_app = QApplication.instance() or QApplication(sys.argv)

        # Periodically check controller state and quit the event loop when it stops.
        # This is required so that headless runs with --autoclose (or other stop
        # conditions) actually terminate and allow the CLI scheduler to start the
        # next run.
        if qt_app is not None and controller_instance is not None:
            def _check_controller_finished():
                try:
                    if not controller_instance.is_running():
                        logger.info("Controller stopped in headless mode, quitting Qt event loop")
                        qt_app.quit()
                except Exception as e:
                    try:
                        logger.error(f"Error while checking controller state in headless mode: {e}", exc_info=True)
                    except Exception:
                        # Avoid cascading failures during shutdown
                        pass

            timer = QTimer(qt_app)
            timer.setInterval(1000)  # check every second
            timer.timeout.connect(_check_controller_finished)
            timer.start()

        logger.info("Controller started in headless mode, entering Qt event loop...")
        ret = qt_app.exec()
    else:
        logger.info("Starting main application loop")
        ret = qt_app.exec()
    
    logger.info(f"Application finished with code: {ret}")
    return ret


def _connect_gui_to_controller(controller_instance, config_file_name, config_data, 
                                gui_manager: GUIManager, logger, progress_window=None):
    """
    Connect GUI components to controller.
    
    This function creates GUI components БЕЗ controller and connects them to the controller
    through the visualization adapter after controller initialization.
    """
    try:
        # Update progress if available
        if progress_window:
            progress_window.update_progress(90, "Creating GUI components...")
        
        # Create MainWindow БЕЗ controller (все виджеты создаются пустыми)
        logger.info("Creating MainWindow without controller...")
        main_window = MainWindow(1600, 720)
        gui_manager.main_window = main_window
        
        if progress_window:
            progress_window.update_progress(92, "Initializing GUI components...")
        
        # Update controller's GUI flags
        controller_instance.show_main_gui = (gui_manager.mode == GUIMode.VISIBLE)
        controller_instance.show_journal = config_data.get('controller', {}).get('show_journal', False)
        
        # Устанавливаем данные в MainWindow из controller ПЕРЕД созданием визуализатора
        # Это нужно для создания labels, которые визуализатор будет использовать
        logger.info("Setting controller data in MainWindow...")
        main_window.set_controller(controller_instance, config_file_name, config_data)
        logger.info("Controller data set in MainWindow")
        
        # Initialize visualizer using legacy method (init_main_window)
        # Визуализатор создается ПОСЛЕ установки данных, чтобы labels уже существовали
        logger.info("Initializing visualizer through controller...")
        controller_instance.init_main_window(main_window, main_window.slots, main_window.signals)
        logger.info("Visualizer initialized through controller")
        
        if progress_window:
            progress_window.update_progress(95, "Starting controller components...")
        
        # Start controller
        controller_instance.start()
        
        if progress_window:
            progress_window.update_progress(99, "Finalizing startup...")
        
        # Show GUI based on mode
        if gui_manager.mode == GUIMode.VISIBLE:
            gui_manager.show_gui()
            # Open journal if needed (from config)
            controller_config = config_data.get('controller', {})
            if controller_config.get('show_journal', False):
                # Journal window is created lazily, so we need to check if it exists or can be created
                if hasattr(main_window, 'db_journal_win') and main_window.db_journal_win:
                    main_window.open_journal()
                elif hasattr(main_window, '_deferred_journal_creation'):
                    # Journal will be created on first open
                    main_window.open_journal()
        elif gui_manager.mode == GUIMode.HIDDEN:
            # Hidden mode: start flag monitor
            gui_manager._start_flag_monitor()
            logger.info("Hidden GUI mode: GUI will be shown when flag file is detected")
        
        if progress_window:
            progress_window.update_progress(100, "Ready!")
            progress_window.hide()
            progress_window.close()
            progress_window.deleteLater()
            qt_app = gui_manager.get_qt_application()
            if qt_app:
                qt_app.processEvents()
        
        logger.info("GUI connected to controller successfully")
        
    except Exception as e:
        logger.error(f"Error connecting GUI to controller: {e}", exc_info=True)
        if progress_window:
            try:
                progress_window.close()
            except:
                pass
        raise


def _create_main_window_and_start(controller_instance, config_file_name, config_data, qt_app, gui, logger, progress_window=None):
    """Создать главное окно и запустить контроллер"""
    try:
        # Обновляем прогресс при создании главного окна
        if progress_window:
            progress_window.update_progress(90, "Creating main window...")
            qt_app.processEvents()
        
        logger.info("Creating main window (no-show in headless mode)")
        try:
            # Create MainWindow БЕЗ controller (все виджеты создаются пустыми)
            a = MainWindow(1600, 720)
            logger.info("MainWindow instance created successfully")
        except Exception as e:
            logger.error(f"Error creating MainWindow: {e}", exc_info=True)
            raise
        
        logger.info("DEBUG: After MainWindow creation, before progress update")
        if progress_window:
            logger.info("DEBUG: Updating progress to 92%")
            try:
                progress_window.update_progress(92, "Initializing main window components...")
                logger.info("DEBUG: Progress updated to 92%")
            except Exception as e:
                logger.error(f"DEBUG: Error updating progress: {e}", exc_info=True)
        else:
            logger.info("DEBUG: progress_window is None")
        
        logger.info("DEBUG: MainWindow instance created, calling init_main_window...")
        controller_instance.init_main_window(a, a.slots, a.signals)
        logger.info(f"init_main_window completed, show_main_gui={controller_instance.show_main_gui}, gui={gui}")
        
        # Устанавливаем данные в MainWindow из controller
        logger.info("Setting controller data in MainWindow...")
        a.set_controller(controller_instance, config_file_name, config_data)
        logger.info("Controller data set in MainWindow")
        
        # Устанавливаем callback для обновления прогресса при запуске модулей
        logger.info("Setting up progress callback...")
        if progress_window:
            def start_progress_callback(value, stage_text):
                # Минимальный callback без блокирующих операций
                try:
                    if progress_window and hasattr(progress_window, 'progress_bar'):
                        # Используем значение напрямую, так как start() теперь использует 95-98%
                        progress_window.progress_bar.setValue(value)
                        if stage_text and hasattr(progress_window, 'stage_label'):
                            progress_window.stage_label.setText(stage_text)
                except Exception:
                    # Игнорируем ошибки в callback, чтобы не блокировать выполнение
                    pass
            controller_instance.progress_callback = start_progress_callback
            logger.info("Progress callback set up")
        else:
            # Убираем callback, если окно прогресса не доступно
            controller_instance.progress_callback = None
            logger.info("Progress callback disabled (no progress window)")

        logger.info("DEBUG: After callback setup")
        if progress_window:
            logger.info("DEBUG: progress_window exists, updating to 95%")
            try:
                progress_window.progress_bar.setValue(95)
                progress_window.stage_label.setText("Starting controller components...")
                logger.info("DEBUG: Progress updated to 95%")
            except Exception as e:
                logger.error(f"DEBUG: Error updating progress: {e}", exc_info=True)
        else:
            logger.info("DEBUG: progress_window is None")

        logger.info("DEBUG: About to call controller.start()...")
        try:
            controller_instance.start()
            logger.info("Controller started successfully")
        except Exception as e:
            logger.error(f"Error starting controller: {e}", exc_info=True)
            raise
        
        if progress_window:
            progress_window.update_progress(99, "Finalizing startup...")
            qt_app.processEvents()
        
        # Закрываем прогресс-бар после завершения запуска всех модулей
        if progress_window:
            progress_window.update_progress(100, "Ready!")
            qt_app.processEvents()
            logger.info("Closing progress window")
            try:
                if progress_window.isVisible():
                    progress_window.hide()  # Скрываем окно
                progress_window.close()  # Закрываем окно
                progress_window.setParent(None)  # Удаляем ссылку на родителя
                progress_window.deleteLater()  # Планируем удаление окна
                qt_app.processEvents()  # Обновляем GUI, чтобы окно закрылось
                logger.info("Progress window closed")
            except Exception as e:
                logger.warning(f"Error closing progress window: {e}")
        
        # Показываем главное окно ПОСЛЕ завершения start() и закрытия прогресс-бара
        if gui and controller_instance.show_main_gui:
            logger.info("Showing main window")
            a.show()
            a.raise_()  # Поднимаем окно на передний план
            a.activateWindow()  # Активируем окно
            qt_app.processEvents()  # Обновляем GUI
            logger.info("Main window displayed and activated")
            if controller_instance.show_journal:
                a.open_journal()
                logger.info("Journal opened")
        else:
            logger.info(f"Main window not shown: gui={gui}, show_main_gui={controller_instance.show_main_gui}")
    except Exception as e:
        logger.error(f"Error in _create_main_window_and_start: {e}", exc_info=True)
        if progress_window:
            try:
                progress_window.close()
            except:
                pass
        raise


