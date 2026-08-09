#!/usr/bin/env python3
"""
EvilEye Command Line Interface

Provides command-line tools for running the EvilEye surveillance system.
"""

import json
import sys
import os
import shutil
import subprocess
import logging
import signal
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime, timedelta
import time

import typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from evileye.utils.utils import normalize_config_path
from evileye.core.logging_config import setup_evileye_logging, log_system_info
from evileye.core.logger import get_module_logger
from evileye.core.config_validator import ConfigValidator


def _get_scheduled_restart_defaults() -> dict:
    """Return default scheduled restart configuration."""
    return {
        "enabled": False,
        "mode": "daily_time",
        "time": "01:00",
        "interval_minutes": 0,
    }


def _load_scheduled_restart_config(config_path: Path, logger: logging.Logger) -> dict:
    """Load scheduled_restart section from controller config, with safe defaults."""
    cfg = _get_scheduled_restart_defaults()
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        controller_cfg = data.get("controller") or {}
        sched_cfg = controller_cfg.get("scheduled_restart") or {}
        if isinstance(sched_cfg, dict):
            cfg.update({k: sched_cfg.get(k, cfg[k]) for k in cfg.keys()})
    except Exception as e:
        try:
            logger.warning(f"Failed to load scheduled_restart from {config_path}: {e}")
        except Exception:
            pass
    # Normalize types
    cfg["enabled"] = bool(cfg.get("enabled"))
    cfg["mode"] = str(cfg.get("mode") or "daily_time")
    cfg["time"] = str(cfg.get("time") or "01:00")
    try:
        cfg["interval_minutes"] = int(cfg.get("interval_minutes") or 0)
    except Exception:
        cfg["interval_minutes"] = 0
    return cfg


def _parse_time_str(time_str: str) -> Tuple[int, int]:
    """Parse HH:MM string into (hour, minute)."""
    try:
        parts = time_str.strip().split(":")
        if len(parts) != 2:
            raise ValueError(f"Invalid time format: {time_str}")
        hour = int(parts[0])
        minute = int(parts[1])
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError(f"Invalid time value: {time_str}")
        return hour, minute
    except Exception as e:
        raise ValueError(f"Invalid time string '{time_str}': {e}") from e


def _get_next_daily_time(now: datetime, time_str: str) -> datetime:
    """Return next datetime for given HH:MM after 'now'."""
    hour, minute = _parse_time_str(time_str)
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate = candidate + timedelta(days=1)
    return candidate


def _get_next_interval(now: datetime, interval_minutes: int) -> datetime:
    """Return next datetime after given interval (in minutes)."""
    if interval_minutes <= 0:
        interval_minutes = 1
    return now + timedelta(minutes=interval_minutes)


def _scheduler_stop_grace_sec() -> float:
    try:
        return max(30.0, float(os.getenv("EVILEYE_SCHEDULER_STOP_GRACE_SEC", "120") or "120"))
    except (TypeError, ValueError):
        return 120.0


def _scheduler_gpu_settle_sec() -> float:
    try:
        return max(0.0, float(os.getenv("EVILEYE_SCHEDULER_GPU_SETTLE_SEC", "8") or "8"))
    except (TypeError, ValueError):
        return 8.0


def _scheduler_prepare_next_launch(logger: logging.Logger) -> None:
    """Cleanup orphaned MP workers and wait for GPU memory to settle before relaunch."""
    try:
        from evileye.core.mp_session_registry import cleanup_stale_sessions

        cleaned = cleanup_stale_sessions()
        if cleaned:
            logger.info(
                "[scheduler] Cleaned up %d stale MP worker process(es) before launch",
                cleaned,
            )
    except Exception as exc:
        logger.warning("[scheduler] Stale session cleanup failed: %s", exc)

    settle = _scheduler_gpu_settle_sec()
    if settle > 0:
        logger.info(
            "[scheduler] Waiting %.1fs for GPU memory to settle before launch",
            settle,
        )
        time.sleep(settle)


def _scheduler_terminate_child(proc: subprocess.Popen, logger: logging.Logger) -> None:
    """Terminate the scheduled child process and its process group."""
    from evileye.core.process_control import terminate_tree

    pid = proc.pid
    grace_sec = _scheduler_stop_grace_sec()
    try:
        terminate_tree(int(pid), grace_sec=grace_sec)
    except Exception as exc:
        logger.error("[scheduler] Error terminating process %s: %s", pid, exc, exc_info=True)
        try:
            proc.kill()
        except Exception:
            pass
        return
    try:
        proc.wait(timeout=10)
        logger.info("[scheduler] Process %s terminated", pid)
    except subprocess.TimeoutExpired:
        logger.error(
            "[scheduler] Process %s did not exit after terminate within 10s, but continuing anyway",
            pid,
        )
    except Exception as exc:
        logger.warning("[scheduler] Error waiting for process %s: %s", pid, exc)


def _run_with_scheduler(
        base_cmd: list,
        config_path: Path,
        logger: logging.Logger,
) -> None:
    """Run process.py in a loop according to scheduled_restart section in config."""
    sched_cfg = _load_scheduled_restart_config(config_path, logger)
    if not sched_cfg.get("enabled"):
        # Fallback to single run if scheduler is disabled
        logger.info("Scheduled restart is disabled in config, running single process.")
        # Устанавливаем переменную окружения для определения запуска через CLI
        env = os.environ.copy()
        env['EVILEYE_CLI_LAUNCHED'] = '1'
        subprocess.run(base_cmd, check=True, cwd=os.getcwd(), env=env)
        return

    mode = (sched_cfg.get("mode") or "daily_time").lower()
    time_str = sched_cfg.get("time") or "01:00"
    interval_minutes = int(sched_cfg.get("interval_minutes") or 0)

    logger.info(
        f"Starting scheduled restart loop: enabled={sched_cfg.get('enabled')}, "
        f"mode={mode}, time={time_str}, interval_minutes={interval_minutes}"
    )

    iteration = 0
    prev_iteration_end_time = None
    stop_requested = False

    def _request_stop(signum, _frame) -> None:
        nonlocal stop_requested
        stop_requested = True
        logger.info("[scheduler] Received signal %s, will stop scheduler loop", signum)

    prev_sigterm = signal.signal(signal.SIGTERM, _request_stop)
    prev_sighup = signal.signal(signal.SIGHUP, _request_stop) if hasattr(signal, "SIGHUP") else None

    try:
        while True:
            if stop_requested:
                logger.info("[scheduler] Stop requested before next iteration, exiting")
                break

            iteration += 1
            if iteration > 1:
                _scheduler_prepare_next_launch(logger)
            iteration_start_time = datetime.now()
            if prev_iteration_end_time is not None:
                logger.info(
                    f"[scheduler] Starting iteration {iteration}: previous iteration ended at "
                    f"{prev_iteration_end_time.isoformat()}, starting at {iteration_start_time.isoformat()}, "
                    f"gap between iterations: {(iteration_start_time - prev_iteration_end_time).total_seconds():.1f}s"
                )
            else:
                logger.info(
                    f"[scheduler] Starting iteration {iteration}: first iteration, starting at "
                    f"{iteration_start_time.isoformat()}"
                )
            logger.info(f"[scheduler] Iteration {iteration}: launching process: {' '.join(base_cmd)}")
            console.print(f"[green][scheduler] Iteration {iteration}: launching[/green] {' '.join(base_cmd)}")

            try:
                # Запускаем дочерний процесс без блокирующего ожидания
                # Устанавливаем переменную окружения для определения запуска через CLI
                env = os.environ.copy()
                env['EVILEYE_CLI_LAUNCHED'] = '1'
                proc = subprocess.Popen(
                    base_cmd,
                    cwd=os.getcwd(),
                    env=env,
                    start_new_session=True,
                )
            except Exception as e:
                logger.error(f"[scheduler] Failed to start process: {e}", exc_info=True)
                console.print(f"[red]Failed to start process: {e}[/red]")
                raise typer.Exit(1)

            start_time = datetime.now()

            # Время следующего запуска по расписанию
            if mode == "interval":
                next_run = _get_next_interval(start_time, interval_minutes)
            else:
                next_run = _get_next_daily_time(start_time, time_str)

            logger.info(f"[scheduler] Next launch scheduled at {next_run.isoformat()}")
            console.print(f"[blue][scheduler] Next launch at {next_run.isoformat()}[/blue]")

            # Логируем информацию о времени до следующего запуска
            time_until_next = (next_run - start_time).total_seconds()
            hours_until_next = time_until_next / 3600.0
            if hours_until_next > 12:
                days_until_next = hours_until_next / 24.0
                logger.info(
                    f"[scheduler] ===== NEXT SCHEDULED RESTART: {next_run.strftime('%Y-%m-%d %H:%M:%S')} "
                    f"({days_until_next:.1f} days / {hours_until_next:.1f} hours from now) ====="
                )
                console.print(
                    f"[green][scheduler] Next scheduled restart: {next_run.strftime('%Y-%m-%d %H:%M:%S')} "
                    f"({days_until_next:.1f} days / {hours_until_next:.1f} hours)[/green]"
                )
            elif hours_until_next > 1:
                logger.info(
                    f"[scheduler] ===== NEXT SCHEDULED RESTART: {next_run.strftime('%Y-%m-%d %H:%M:%S')} "
                    f"({hours_until_next:.1f} hours from now) ====="
                )
                console.print(
                    f"[green][scheduler] Next scheduled restart: {next_run.strftime('%Y-%m-%d %H:%M:%S')} "
                    f"({hours_until_next:.1f} hours)[/green]"
                )
            else:
                minutes_until_next = time_until_next / 60.0
                logger.info(
                    f"[scheduler] ===== NEXT SCHEDULED RESTART: {next_run.strftime('%Y-%m-%d %H:%M:%S')} "
                    f"({minutes_until_next:.1f} minutes from now) ====="
                )
                console.print(
                    f"[green][scheduler] Next scheduled restart: {next_run.strftime('%Y-%m-%d %H:%M:%S')} "
                    f"({minutes_until_next:.1f} minutes)[/green]"
                )

            # Флаг: нужно ли продолжать внешний цикл (ещё один запуск) после этой итерации
            continue_scheduler = True
            # Немедленный перезапуск без ожидания next_run (расписание / crash / memory leak)
            immediate_restart = False

            try:
                # Цикл до естественного завершения процесса ИЛИ до наступления времени перезапуска
                while True:
                    if stop_requested:
                        logger.info("[scheduler] Stop requested, terminating child and exiting loop")
                        if proc.poll() is None:
                            try:
                                _scheduler_terminate_child(proc, logger)
                            except Exception:
                                try:
                                    proc.kill()
                                except Exception:
                                    pass
                        continue_scheduler = False
                        break

                    now = datetime.now()
                    retcode = proc.poll()

                    if retcode is not None:
                        duration = (now - start_time).total_seconds()
                        logger.info(
                            f"[scheduler] Iteration {iteration} finished with return code={retcode} "
                            f"(duration={duration:.1f}s)"
                        )

                        # Return code 2 = memory leak restart requested
                        if retcode == 2:
                            logger.info(
                                "[scheduler] Memory leak detected: restarting immediately "
                                "(skipping scheduled wait)"
                            )
                            console.print(
                                "[yellow][scheduler] Memory leak restart: launching next iteration immediately[/yellow]"
                            )
                            continue_scheduler = True
                            immediate_restart = True
                            break

                        # Graceful exit (code 0) before next_run = user/manual shutdown.
                        if retcode == 0 and now < next_run:
                            logger.info(
                                "[scheduler] Process finished before next scheduled time — "
                                "stopping scheduler loop (respecting manual/normal shutdown)"
                            )
                            continue_scheduler = False
                            break

                        # Unexpected crash (SIGKILL, SIGSEGV, OOM, etc.) — auto-restart immediately.
                        if retcode != 0 and now < next_run:
                            logger.warning(
                                "[scheduler] Unexpected child death (return code=%s) before next "
                                "scheduled time — auto-restarting iteration immediately",
                                retcode,
                            )
                            console.print(
                                f"[yellow][scheduler] Unexpected exit (code={retcode}): "
                                f"relaunching next iteration immediately[/yellow]"
                            )
                            continue_scheduler = True
                            immediate_restart = True
                            break

                        break

                    if now >= next_run:
                        # Наступило время планового перезапуска — аккуратно останавливаем текущий процесс
                        logger.info(
                            f"[scheduler] Time {now.isoformat()} reached, terminating process pid={proc.pid} "
                            f"for scheduled restart"
                        )
                        console.print(
                            f"[yellow][scheduler] Stopping current run (pid={proc.pid}) for scheduled restart[/yellow]"
                        )
                        try:
                            _scheduler_terminate_child(proc, logger)
                        except Exception as e:
                            logger.error(f"[scheduler] Error terminating process {proc.pid}: {e}", exc_info=True)

                        # Финальная проверка, что процесс действительно завершился
                        final_retcode = proc.poll()
                        if final_retcode is None:
                            logger.error(
                                f"[scheduler] Process {proc.pid} is still running after termination attempts, "
                                f"but continuing to next iteration"
                            )
                        else:
                            logger.info(
                                f"[scheduler] Process {proc.pid} confirmed terminated with return code {final_retcode}"
                            )

                        termination_time = datetime.now()
                        logger.info(
                            f"[scheduler] Process termination completed at {termination_time.isoformat()}, "
                            f"continue_scheduler={continue_scheduler}, proceeding to next iteration immediately"
                        )
                        continue_scheduler = True
                        immediate_restart = True
                        break

                    time.sleep(1.0)

            except KeyboardInterrupt:
                logger.info("[scheduler] Interrupted by user, terminating child and stopping loop")
                if proc.poll() is None:
                    try:
                        _scheduler_terminate_child(proc, logger)
                    except Exception:
                        try:
                            proc.kill()
                        except Exception:
                            pass
                raise typer.Exit(0)

            # Если процесс завершился сам до наступления следующего планового запуска —
            # выходим из основного цикла и НЕ перезапускаем приложение снова.
            if not continue_scheduler:
                prev_iteration_end_time = datetime.now()
                logger.info(
                    f"[scheduler] Iteration {iteration} ended normally, scheduler loop stopping. "
                    f"End time: {prev_iteration_end_time.isoformat()}"
                )
                break

            # Crash / memory-leak / scheduled stop: next iteration without waiting for next_run
            if immediate_restart:
                logger.info(
                    "[scheduler] Immediate restart requested, launching next iteration without wait"
                )
                continue

            # Если процесс завершился сам (не по расписанию), вычисляем следующее время запуска
            # и ждём до этого времени перед запуском следующей итерации
            now = datetime.now()
            prev_iteration_end_time = now  # Сохраняем время завершения итерации

            # Вычисляем следующее время запуска для следующей итерации
            if mode == "interval":
                next_run = _get_next_interval(now, interval_minutes)
            else:  # daily_time
                next_run = _get_next_daily_time(now, time_str)
                time_until_next = (next_run - now).total_seconds()
                if time_until_next > 12 * 3600:  # Больше 12 часов = точно завтра
                    logger.info(
                        f"[scheduler] Next scheduled time is tomorrow ({next_run.isoformat()}), "
                        f"waiting until then for next iteration."
                    )
                else:
                    logger.info(
                        f"[scheduler] Next scheduled time is {next_run.isoformat()}, "
                        f"waiting {time_until_next:.1f}s until next iteration"
                    )

            # Ждём до следующего времени запуска
            sleep_seconds = max(0.0, (next_run - now).total_seconds())
            if sleep_seconds > 0:
                logger.info(
                    f"[scheduler] Waiting {sleep_seconds:.1f} seconds until next scheduled launch "
                    f"at {next_run.isoformat()}"
                )
                console.print(
                    f"[blue][scheduler] Waiting {sleep_seconds:.1f}s until next launch at "
                    f"{next_run.isoformat()}[/blue]"
                )

                logger.info(
                    f"[scheduler] Starting wait loop: current_time={now.isoformat()}, "
                    f"next_run={next_run.isoformat()}, sleep_seconds={sleep_seconds:.1f}"
                )
                num_intervals = int(sleep_seconds / 60.0) + (1 if sleep_seconds % 60.0 > 0 else 0)
                logger.info(
                    f"[scheduler] Wait will be split into {num_intervals} interval(s) of up to 60 seconds each"
                )

                try:
                    remaining_seconds = sleep_seconds
                    interval_count = 0
                    while remaining_seconds > 0:
                        if stop_requested:
                            logger.info("[scheduler] Stop requested during wait, stopping scheduler loop")
                            console.print("[yellow][scheduler] Stop requested during wait, stopping loop[/yellow]")
                            return
                        interval_count += 1
                        sleep_interval = min(60.0, remaining_seconds)
                        logger.info(
                            f"[scheduler] Wait interval {interval_count}: sleeping for {sleep_interval:.1f}s, "
                            f"{remaining_seconds:.1f}s remaining until next launch"
                        )
                        time.sleep(sleep_interval)
                        remaining_seconds -= sleep_interval
                        if remaining_seconds > 0:
                            logger.info(
                                f"[scheduler] Wait interval {interval_count} completed: "
                                f"{remaining_seconds:.1f}s remaining until next launch at {next_run.isoformat()}"
                            )
                        else:
                            logger.info(
                                f"[scheduler] Wait interval {interval_count} completed: "
                                f"all wait time elapsed, ready for next launch"
                            )

                    wait_end_time = datetime.now()
                    logger.info(
                        f"[scheduler] Wait loop completed: started at {now.isoformat()}, "
                        f"ended at {wait_end_time.isoformat()}, total wait duration: "
                        f"{(wait_end_time - now).total_seconds():.1f}s"
                    )
                    logger.info(
                        f"[scheduler] Ready to start next iteration, next_run time: {next_run.isoformat()}"
                    )
                    prev_iteration_end_time = wait_end_time
                except KeyboardInterrupt:
                    logger.info("[scheduler] Interrupted during wait, stopping scheduler loop")
                    console.print("[yellow][scheduler] Interrupted during wait, stopping loop[/yellow]")
                    raise typer.Exit(0)
    finally:
        signal.signal(signal.SIGTERM, prev_sigterm)
        if prev_sighup is not None:
            signal.signal(signal.SIGHUP, prev_sighup)


# Create CLI app
app = typer.Typer(
    name="evileye",
    help="Intelligence video surveillance system",
    add_completion=False,
)

console = Console()


def setup_logging(verbose: bool = False) -> None:
    """Setup logging configuration"""
    level = "DEBUG" if verbose else "INFO"
    setup_evileye_logging(log_level=level, log_to_console=True, log_to_file=True)


@app.command()
def run(
        config: Optional[Path] = typer.Argument(None, help="Configuration file path"),
        video: Optional[str] = typer.Option(None, "--video", help="Video file to process"),
        gui: bool = typer.Option(True, "--gui/--no-gui", help="Launch with gui interface"),
        autoclose: bool = typer.Option(False, "--autoclose/--no-autoclose",
                                       help="Automatic close application when video ends"),
        verbose: bool = typer.Option(False, "--verbose", help="Enable verbose logging"),
) -> None:
    """
    Launch EvilEye system.

    This is the primary operational mode: the runtime owns the lifecycle
    of the system and may start the web server module from configuration.

    Example:
        evileye run configs/test_sources_detectors_trackers_mc.json
        evileye run --video /path/to/video.mp4
    """
    # Setup logging
    setup_logging(verbose=verbose)
    logger = get_module_logger("cli")
    log_system_info(logger)

    # Build command arguments
    cmd = [sys.executable, str(Path(__file__).parent / "process.py")]
    config_path: Optional[Path] = None

    if config:
        # Normalize config path and check if it exists
        normalized_config = Path(normalize_config_path(config))
        if not normalized_config.exists():
            logger.error(f"Configuration file not found: {normalized_config}")
            console.print(f"[red]Configuration file not found: {normalized_config}[/red]")
            raise typer.Exit(1)
        cmd.extend(["--config", str(normalized_config)])
        logger.info(f"Using configuration: {normalized_config}")
        config_path = normalized_config
    elif video:
        cmd.extend(["--video", video])
        logger.info(f"Using video file: {video}")
    else:
        # Use default config
        default_config = Path("configs/test_sources_detectors_trackers_mc.json")
        if default_config.exists():
            cmd.extend(["--config", str(default_config)])
            logger.info(f"Using default configuration: {default_config}")
            config_path = default_config
        else:
            logger.error("Configuration file not specified and default configuration not found")
            console.print("[red]No configuration file specified and default not found[/red]")
            console.print("Please specify a config file: [yellow]evileye run <config_file>[/yellow]")
            raise typer.Exit(1)

    # Add GUI flag based on boolean value
    if gui:
        cmd.append("--gui")
        logger.info("GUI enabled")
    else:
        cmd.append("--no-gui")
        logger.info("GUI disabled")

    # Add autoclose flag based on boolean value
    if autoclose:
        cmd.append("--autoclose")
        logger.info("Auto-close enabled")
    else:
        cmd.append("--no-autoclose")
        logger.info("Auto-close disabled")

    # Recording is configured only via config file; no CLI flags

    try:
        logger.info(f"Launching command: {' '.join(cmd)}")
        console.print(f"[green]Launching with command:[/green] {' '.join(cmd)}")
        # If we have a configuration file, check for scheduled_restart section
        if config_path is not None:
            _run_with_scheduler(cmd, config_path, logger)
        else:
            # No configuration file -> no scheduler, run once
            # Устанавливаем переменную окружения для определения запуска через CLI
            env = os.environ.copy()
            env['EVILEYE_CLI_LAUNCHED'] = '1'
            subprocess.run(cmd, check=True, cwd=os.getcwd(), env=env)
        logger.info("Command executed successfully")
    except subprocess.CalledProcessError as e:
        logger.error(f"Launch error: {e}")
        console.print(f"[red]Error launching: {e}[/red]")
        raise typer.Exit(1)
    except KeyboardInterrupt:
        logger.info("Launch interrupted by user")
        console.print("[yellow]Launch interrupted by user[/yellow]")
        raise typer.Exit(0)


@app.command("server")
def start_api(
        host: str = typer.Option("127.0.0.1", "--host", help="Bind host"),
        port: int = typer.Option(8181, "--port", help="Bind port"),
        reload: bool = typer.Option(True, "--reload/--no-reload", help="Auto-reload on code changes"),
        workers: int = typer.Option(1, "--workers", help="Number of worker processes"),
        verbose: bool = typer.Option(False, "--verbose", help="Enable verbose logging"),
        log_level: str = typer.Option("info", "--log-level", help="Logging level"),
        config: Optional[str] = typer.Option(None, "--config",
                                             help="Auto-run selected config after server starts (name or file path)"),
        ssl_certfile: Optional[str] = typer.Option(None, "--ssl-certfile", help="TLS certificate file (PEM)"),
        ssl_keyfile: Optional[str] = typer.Option(None, "--ssl-keyfile", help="TLS private key file (PEM)")

) -> None:
    """
    Start EvilEye FastAPI web server.

    This is a service/administrative mode. For the primary operational
    scenario prefer `evileye run`, where the system is started first and
    the web server works as its module.

    Examples:
        evileye server --host 0.0.0.0 --port 8000
        evileye server --config poly-videos.json
        evileye server --config ./configs/poly-videos.json
    """

    import time
    import urllib.request
    import urllib.error

    setup_logging(verbose=verbose)
    logger = get_module_logger("cli")
    log_system_info(logger)

    # Use server.py instead of process.py for API server
    cmd = [sys.executable, str(Path(__file__).parent / "server.py")]
    cmd.extend(["--host", host, "--port", str(port), "--log-level", log_level])

    if not reload:
        cmd.append("--no-reload")
    if workers != 1:
        cmd.extend(["--workers", str(workers)])
    if verbose:
        cmd.append("--verbose")

    if config:
        cmd.extend(["--config", config])
    if ssl_certfile:
        cmd.extend(["--ssl-certfile", ssl_certfile])
    if ssl_keyfile:
        cmd.extend(["--ssl-keyfile", ssl_keyfile])

    try:
        logger.info(f"Starting web server (server.py): {' '.join(cmd)}")
        console.print(f"[green]Starting web server on {host}:{port}[/green]")
        subprocess.run(cmd, check=True, cwd=os.getcwd())
    except subprocess.CalledProcessError as e:
        logger.error(f"Web server failed: {e}")
        console.print(f"[red]Web server failed: {e}[/red]")
        raise typer.Exit(1)
    except KeyboardInterrupt:
        logger.info("Web server interrupted by user")
        console.print("[yellow]Web server interrupted by user[/yellow]")
        raise typer.Exit(0)


@app.command()
def validate(
        config: Path = typer.Argument(
            ...,
            help="Path to configuration JSON file",
            file_okay=True,
            dir_okay=False,
        ),
) -> None:
    """
    Validate EvilEye configuration file.
    
    Example:
        evileye validate single_cam.json
        evileye validate configs/single_cam.json
    """
    try:
        # Normalize config path
        normalized_config = Path(normalize_config_path(config))

        if not normalized_config.exists():
            console.print(f"[red]Configuration file not found: {normalized_config}[/red]")
            raise typer.Exit(1)

        with open(normalized_config, 'r') as f:
            pipeline_config = json.load(f)

        # Базовая валидация структуры
        validate_config(pipeline_config)

        # Расширенная валидация через ConfigValidator
        validator = ConfigValidator()
        is_valid, error_msg = validator.validate_full_config(pipeline_config)
        if not is_valid:
            console.print(f"[yellow]Configuration validation warning: {error_msg}[/yellow]")
            console.print("[yellow]Continuing with potentially invalid configuration...[/yellow]")
        else:
            console.print(f"[green]Configuration {normalized_config} is valid![/green]")

    except Exception as e:
        console.print(f"[red]Configuration validation failed: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def list_configs() -> None:
    """
    List available configuration files.
    """
    config_dir = Path("configs")

    if not config_dir.exists():
        console.print("[red]Configs directory not found[/red]")
        raise typer.Exit(1)

    config_files = list(config_dir.glob("*.json"))

    if not config_files:
        console.print("[yellow]No configuration files found[/yellow]")
        return

    table = Table(title="Available Configurations")
    table.add_column("Name", style="cyan")
    table.add_column("Size", style="magenta")
    table.add_column("Description", style="green")

    for config_file in sorted(config_files):
        size = config_file.stat().st_size
        description = get_config_description(config_file)

        table.add_row(
            config_file.name,
            f"{size} bytes",
            description,
        )

    console.print(table)


def _monitor_source_dir() -> Path:
    """Locate packaged or repo-checkout monitor assets for site deploy."""
    candidates = [
        Path(__file__).parent / "deploy_monitor",
        Path(__file__).resolve().parents[1] / "deploy" / "monitor",
    ]
    for candidate in candidates:
        if (candidate / "scripts" / "install_timer.sh").is_file():
            return candidate
    raise FileNotFoundError(
        "Monitor assets not found. Expected evileye/deploy_monitor or deploy/monitor "
        "with scripts/install_timer.sh"
    )


def _deploy_monitor_assets(site_dir: Path) -> None:
    """
    Copy watchdog/monitor scripts into <site>/monitor/.

    Does not enable systemd timers or start EvilEye — only files and empty runtime dirs.
    Re-running updates scripts/systemd from the package without wiping incidents/logs.
    """
    source = _monitor_source_dir()
    monitor_dir = site_dir / "monitor"
    scripts_dst = monitor_dir / "scripts"
    systemd_dst = monitor_dir / "systemd"

    scripts_dst.mkdir(parents=True, exist_ok=True)
    systemd_dst.mkdir(parents=True, exist_ok=True)

    copied_scripts = 0
    for src in sorted((source / "scripts").glob("*")):
        if not src.is_file():
            continue
        shutil.copy2(src, scripts_dst / src.name)
        # Ensure shell scripts are executable on Unix.
        if src.suffix == ".sh" or src.name.endswith(".sh"):
            mode = (scripts_dst / src.name).stat().st_mode
            (scripts_dst / src.name).chmod(mode | 0o111)
        copied_scripts += 1

    copied_units = 0
    systemd_src = source / "systemd"
    if systemd_src.is_dir():
        for src in sorted(systemd_src.glob("*")):
            if not src.is_file():
                continue
            shutil.copy2(src, systemd_dst / src.name)
            copied_units += 1

    readme_src = source / "README.md"
    if readme_src.is_file():
        shutil.copy2(readme_src, monitor_dir / "README.md")

    # Runtime directories (empty placeholders; never start services here).
    for name in ("incidents", "reports", "logs"):
        # logs live at site root; incidents/reports under monitor/
        if name == "logs":
            (site_dir / "logs").mkdir(parents=True, exist_ok=True)
        else:
            (monitor_dir / name).mkdir(parents=True, exist_ok=True)

    hint = monitor_dir / "INSTALL_HINT.txt"
    if sys.platform.startswith("win"):
        hint.write_text(
            "Monitor assets were deployed by `evileye deploy`.\n"
            "Linux install_timer.sh does not run on Windows.\n\n"
            "Native Windows watchdog:\n"
            "  evileye watchdog-install --config configs/single_video.json\n"
            "  evileye watchdog-check --config configs/single_video.json\n"
            "  evileye watchdog-uninstall\n\n"
            "Docker Desktop deployments: use docker/windows/Install-Watchdog.ps1 instead.\n",
            encoding="utf-8",
        )
    else:
        hint.write_text(
            "Monitor scripts were deployed by `evileye deploy`.\n"
            "They are NOT started automatically.\n\n"
            "To enable the user systemd watchdog on this machine:\n"
            f"  DEPLOY_DIR={site_dir} {scripts_dst / 'install_timer.sh'}\n\n"
            "Manual health check:\n"
            f"  DEPLOY_DIR={site_dir} {scripts_dst / 'health_check.sh'}\n\n"
            "Cross-platform native watchdog (also works on Linux):\n"
            "  evileye watchdog-install --config configs/single_video.json\n",
            encoding="utf-8",
        )

    console.print(
        f"[green]Deployed monitor assets "
        f"({copied_scripts} scripts, {copied_units} systemd templates) → {monitor_dir}[/green]"
    )
    console.print(
        "[blue]Note:[/blue] watchdog timers were [bold]not[/bold] enabled; "
        f"run install_timer.sh when ready (see {hint.name})."
    )


@app.command()
def deploy() -> None:
    """
    Deploy EvilEye site files to the current directory.

    This command:
    1. Copies credentials_proto.json to credentials.json (if missing)
    2. Creates configs/ and logs/ folders if missing
    3. Deploys monitor/watchdog scripts and systemd templates (does not start services)
    """

    current_dir = Path.cwd()
    console.print(f"[blue]Deploying EvilEye files to: {current_dir}[/blue]")

    # Step 1: Copy credentials_proto.json to credentials.json
    credentials_proto = Path(__file__).parent / "credentials_proto.json"
    credentials_target = current_dir / "credentials.json"

    if credentials_target.exists():
        console.print("[yellow]credentials.json already exists, skipping...[/yellow]")
    else:
        if credentials_proto.exists():
            try:
                shutil.copy2(credentials_proto, credentials_target)
                console.print(f"[green]Copied credentials_proto.json to credentials.json[/green]")
            except Exception as e:
                console.print(f"[red]Error copying credentials file: {e}[/red]")
                raise typer.Exit(1)
        else:
            console.print("[red]credentials_proto.json not found in package[/red]")
            raise typer.Exit(1)

    # Step 2: Create configs folder
    configs_dir = current_dir / "configs"
    if configs_dir.exists():
        console.print("[yellow]configs folder already exists, skipping...[/yellow]")
    else:
        try:
            configs_dir.mkdir(parents=True, exist_ok=True)
            console.print(f"[green]Created configs folder[/green]")
        except Exception as e:
            console.print(f"[red]Error creating configs folder: {e}[/red]")
            raise typer.Exit(1)

    # Step 3: Monitor / watchdog assets (files only — no systemd enable, no process start)
    try:
        _deploy_monitor_assets(current_dir)
    except FileNotFoundError as e:
        console.print(f"[red]Error deploying monitor assets: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error deploying monitor assets: {e}[/red]")
        raise typer.Exit(1)

    # Step 4: Ensure OS service for Web UI (does not fail the whole deploy)
    try:
        from evileye.service_manager import ensure_service
        from evileye.service_manager.minimal_config import ensure_system_config

        ensure_system_config(current_dir)
        svc = ensure_service(site_dir=current_dir, force_user=True)
        if svc.ok:
            console.print(f"[green]{svc.message}[/green]")
        else:
            console.print(f"[yellow]Service ensure skipped/failed: {svc.message}[/yellow]")
            console.print("[dim]Run manually: evileye service-install[/dim]")
    except Exception as e:
        console.print(f"[yellow]Service ensure skipped: {e}[/yellow]")
        console.print("[dim]Run manually: evileye service-install[/dim]")

    console.print("[green]Deployment completed successfully![/green]")
    console.print(
        "[dim]Next: open the Web UI, set admin password, complete Basic setup. "
        "Optional watchdog: monitor/scripts/install_timer.sh[/dim]"
    )


@app.command("service-install")
def service_install(
    config: Optional[Path] = typer.Argument(
        None,
        help="Optional config name/path for auto-run after server start",
    ),
    host: str = typer.Option("0.0.0.0", "--host", help="Bind host for the service"),
    port: int = typer.Option(8181, "--port", help="Bind port for the service"),
    user: bool = typer.Option(False, "--user", help="Force systemd --user unit (Linux)"),
    system: bool = typer.Option(False, "--system", help="Force system unit (may need sudo)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print unit/plan without applying"),
) -> None:
    """
    Install and start EvilEye as an OS service (Web UI server).

    Without CONFIG starts `evileye server` only (minimal post-install mode).
    Re-running updates the unit and restarts (idempotent ensure).
    Use `evileye service-uninstall` to remove the service.
    """
    from evileye.service_manager import install_service

    cfg = str(config) if config is not None else None
    # Default to user unit when neither flag set on non-root installs
    force_user = user or (not system)
    force_system = system
    if user and system:
        console.print("[red]Cannot combine --user and --system[/red]")
        raise typer.Exit(1)

    try:
        result = install_service(
            site_dir=Path.cwd(),
            config=cfg,
            host=host,
            port=port,
            force_user=force_user and not force_system,
            force_system=force_system,
            dry_run=dry_run,
        )
    except Exception as e:
        console.print(f"[red]service-install failed: {e}[/red]")
        raise typer.Exit(1)

    if dry_run and result.unit_text:
        console.print("[blue]Dry-run unit file:[/blue]")
        console.print(result.unit_text)

    if result.ok:
        console.print(f"[green]{result.message}[/green]")
    else:
        style = "yellow" if result.warn_only else "red"
        console.print(f"[{style}]{result.message}[/{style}]")
        if not result.warn_only:
            raise typer.Exit(1)


@app.command("service-uninstall")
def service_uninstall(
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be removed"),
) -> None:
    """Stop and remove the EvilEye OS service installed by service-install."""
    from evileye.service_manager import uninstall_service

    try:
        result = uninstall_service(site_dir=Path.cwd(), dry_run=dry_run)
    except Exception as e:
        console.print(f"[red]service-uninstall failed: {e}[/red]")
        raise typer.Exit(1)

    console.print(f"[green]{result.message}[/green]")


@app.command("watchdog-install")
def watchdog_install(
    config: Optional[str] = typer.Option(
        None,
        "--config",
        help="Config to watch (default: configs/system.json or configs/single_video.json)",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show plan without registering tasks"),
) -> None:
    """Install native watchdog (Scheduled Task on Windows; scripts elsewhere)."""
    from evileye.watchdog_native import install_watchdog

    cfg = config or "configs/system.json"
    if not Path(cfg).exists() and Path("configs/single_video.json").exists():
        cfg = "configs/single_video.json"
    try:
        result = install_watchdog(config=cfg, dry_run=dry_run)
    except Exception as exc:
        console.print(f"[red]watchdog-install failed: {exc}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]Watchdog installed[/green] backend={result.get('backend')} config={cfg}")
    if dry_run:
        console.print(str(result))


@app.command("watchdog-uninstall")
def watchdog_uninstall(
    dry_run: bool = typer.Option(False, "--dry-run", help="Show plan without removing"),
) -> None:
    """Remove native watchdog Scheduled Tasks / scripts."""
    from evileye.watchdog_native import uninstall_watchdog

    try:
        uninstall_watchdog(dry_run=dry_run)
    except Exception as exc:
        console.print(f"[red]watchdog-uninstall failed: {exc}[/red]")
        raise typer.Exit(1)
    console.print("[green]Watchdog uninstalled[/green]")


@app.command("watchdog-check")
def watchdog_check(
    config: Optional[str] = typer.Option(
        None,
        "--config",
        help="Config stem/path to watch",
    ),
    no_restart: bool = typer.Option(False, "--no-restart", help="Only report, do not restart"),
) -> None:
    """Run one native watchdog health check."""
    from evileye.watchdog_native import health_check

    cfg = config
    if not cfg:
        install_meta = Path("monitor/watchdog_install.json")
        if install_meta.exists():
            try:
                cfg = json.loads(install_meta.read_text(encoding="utf-8")).get("config")
            except Exception:
                cfg = None
    cfg = cfg or "configs/single_video.json"
    entry = health_check(config=cfg, do_restart=not no_restart)
    console.print(f"status={entry.get('status')} reason={entry.get('reason')}")


@app.command("watchdog-morning")
def watchdog_morning() -> None:
    """Write morning watchdog report under monitor/reports/."""
    from evileye.watchdog_native import morning_report

    path = morning_report()
    console.print(f"[green]Report written:[/green] {path}")


@app.command("setup-web")
def setup_web(
    check: bool = typer.Option(False, "--check", help="Only check environment; do not install or build"),
    scope: str = typer.Option(
        "user",
        "--scope",
        help="pip install scope: user (~/.local) or system (sudo pip)",
        case_sensitive=False,
    ),
    build: Optional[bool] = typer.Option(
        None,
        "--build/--no-build",
        help="Build SPA with npm (default: build only if static is missing)",
    ),
    force: bool = typer.Option(False, "--force", help="Reinstall missing Python packages and rebuild SPA"),
) -> None:
    """
    Check and prepare Web UI dependencies (Python API packages + SPA static).

    pip --scope user|system installs missing Python packages. Frontend npm
    packages stay local to evileye/api/frontend (never global).
    """
    from evileye import setup_web as sw

    scope_norm = (scope or "user").strip().lower()
    if scope_norm not in {"user", "system"}:
        console.print("[red]--scope must be 'user' or 'system'[/red]")
        raise typer.Exit(1)

    report = sw.collect_web_setup_report()
    table = Table(title="EvilEye Web UI environment")
    table.add_column("Check", style="cyan")
    table.add_column("Status")
    table.add_column("Detail")
    for item in report.items:
        status = "[green]OK[/green]" if item.ok else "[red]FAIL[/red]"
        table.add_row(item.name, status, item.detail)
    console.print(table)

    if check:
        if report.ok:
            console.print("[green]Web UI environment looks ready.[/green]")
            raise typer.Exit(0)
        if report.needs_libturbojpeg():
            console.print(f"[yellow]{sw.LIBTURBOJPEG_HINT}[/yellow]")
        console.print("[red]Web UI environment check failed.[/red]")
        raise typer.Exit(1)

    if report.ok and not force and build is not True:
        console.print("[green]Web UI environment already ready; nothing to do.[/green]")
        console.print("[dim]Use --force to rebuild SPA or reinstall packages.[/dim]")
        raise typer.Exit(0)

    if scope_norm == "system" and not check:
        confirm = typer.confirm(
            "Install missing Python packages system-wide with sudo?",
            default=False,
        )
        if not confirm:
            console.print("[yellow]Aborted (system scope not confirmed).[/yellow]")
            raise typer.Exit(1)

    missing = report.missing_pip_packages()
    if missing or force:
        # On --force, still only install packages that fail import unless force wants all web pkgs
        to_install = missing if missing else ([] if not force else [])
        if force and not to_install:
            # Re-check: force with everything ok → skip pip
            pass
        if to_install:
            console.print(f"[blue]Installing Python packages ({scope_norm}): {', '.join(to_install)}[/blue]")
            try:
                sw.pip_install(to_install, scope=scope_norm)
            except Exception as exc:
                console.print(f"[red]pip install failed: {exc}[/red]")
                raise typer.Exit(1)

    # Re-check turbojpeg native after pip
    report_after_pip = sw.collect_web_setup_report()
    if report_after_pip.needs_libturbojpeg():
        console.print(f"[yellow]{sw.LIBTURBOJPEG_HINT}[/yellow]")

    should_build = force or build is True or report.needs_frontend_build() or report_after_pip.needs_frontend_build()
    if build is False:
        should_build = False

    if should_build:
        if report_after_pip.needs_node() or report.needs_node():
            console.print(
                "[red]Node.js/npm required to build the SPA. "
                "Install with: sudo apt install nodejs npm[/red]"
            )
            raise typer.Exit(1)
        console.print("[blue]Building frontend (npm install && npm run build)…[/blue]")
        try:
            sw.build_frontend()
        except Exception as exc:
            console.print(f"[red]Frontend build failed: {exc}[/red]")
            raise typer.Exit(1)

    final = sw.collect_web_setup_report()
    if final.ok:
        console.print("[green]Web UI setup completed successfully.[/green]")
        raise typer.Exit(0)

    if final.needs_libturbojpeg():
        console.print(f"[yellow]{sw.LIBTURBOJPEG_HINT}[/yellow]")
        # Native lib missing: SPA/API still usable with OpenCV fallback.
        if all(
            item.ok
            for item in final.items
            if item.name != "python:turbojpeg_native"
            and item.name in {
                "python:fastapi",
                "python:uvicorn",
                "python:pydantic",
                "python:itsdangerous",
                "python:turbojpeg",
                "static",
            }
        ):
            console.print(
                "[yellow]Setup finished with TurboJPEG native library missing "
                "(preview will use OpenCV fallback).[/yellow]"
            )
            raise typer.Exit(0)

    console.print("[red]Web UI setup incomplete.[/red]")
    raise typer.Exit(1)


@app.command()
def deploy_samples() -> None:
    """
    Deploy sample configurations with working examples.
    
    This command:
    1. Runs regular deploy command
    2. Downloads sample videos from internet
    3. Copies pre-configured sample configurations
    4. Creates documentation for samples
    """
    current_dir = Path.cwd()
    console.print(f"[blue]Deploying EvilEye sample configurations to: {current_dir}[/blue]")

    # First run regular deploy
    deploy()

    # Create videos directory
    videos_dir = current_dir / "videos"
    if not videos_dir.exists():
        videos_dir.mkdir()
        console.print("[green]Created videos folder[/green]")
    else:
        console.print("[yellow]videos folder already exists, skipping...[/yellow]")

    # Download sample videos
    console.print("\n[blue]Downloading sample videos...[/blue]")
    try:
        from evileye.utils.download_samples import download_sample_videos
        video_results = download_sample_videos(str(videos_dir), parallel=False)

        successful_videos = sum(1 for r in video_results.values()
                                if "downloaded" in r["status"] or r["status"] == "exists")
        total_videos = len(video_results)

        if successful_videos > 0:
            console.print(f"[green]Downloaded {successful_videos}/{total_videos} sample videos[/green]")
        else:
            console.print("[yellow]No videos downloaded, but continuing with sample configs...[/yellow]")

    except Exception as e:
        console.print(f"[yellow]Video download failed: {e}[/yellow]")
        console.print("[blue]Continuing with sample configs (you can add videos manually)...[/blue]")

    # Copy sample configurations
    console.print("\n[blue]Copying sample configurations...[/blue]")
    samples_dir = Path(__file__).parent / "samples_configs"
    configs_dir = current_dir / "configs"

    sample_configs = [
        "single_video.json",
        "single_video_split.json",
        "single_ip_camera.json",
        "multi_videos.json",
        "pipeline_capture.json",
        "single_video_rtdetr.json",
        "multi_videos_rtdetr.json",
        "single_video_rfdetr.json",
        "single_video_gstreamer.json",
        "ip_camera_gstreamer.json",
        "usb_camera_gstreamer.json",
        "image_sequence_gstreamer_jpg.json",
        "image_sequence_gstreamer_folder.json"
    ]

    copied_count = 0
    for config_name in sample_configs:
        source_path = samples_dir / config_name
        dest_path = configs_dir / config_name

        if source_path.exists():
            shutil.copy2(source_path, dest_path)
            console.print(f"[green]Copied {config_name}[/green]")
            copied_count += 1
        else:
            console.print(f"[yellow]Sample config {config_name} not found[/yellow]")

    # Create README for samples
    readme_content = """# EvilEye Sample Configurations

This directory contains sample configurations for EvilEye system.

## Available Samples:

### Video Processing
- **single_video.json** - Single video file processing (planes_sample.mp4)
- **single_video_split.json** - Single video with 2-way split processing (sample_split.mp4)
- **multi_videos.json** - Multiple video files with multi-camera tracking (6p-c0.avi, 6p-c1.avi)
- **single_video_gstreamer.json** - Single video file processing with GStreamer backend (planes_sample.mp4)

### GStreamer Backend Examples
- **ip_camera_gstreamer.json** - IP camera stream processing with GStreamer backend (RTSP)
- **usb_camera_gstreamer.json** - USB camera processing with GStreamer backend (/dev/video0)
- **image_sequence_gstreamer_jpg.json** - JPEG image sequence processing with GStreamer backend
- **image_sequence_gstreamer_folder.json** - All images in folder processing with GStreamer backend

### RT-DETR Detector Examples
- **single_video_rtdetr.json** - Single video with RT-DETR detector (planes_sample.mp4)
- **multi_videos_rtdetr.json** - Multiple videos with RT-DETR detector (6p-c0.avi, 6p-c1.avi)

### RF-DETR Detector Examples
- **single_video_rfdetr.json** - Single video with RF-DETR detector (planes_sample.mp4)

### IP Camera Processing  
- **single_ip_camera.json** - Single IP camera stream processing

## Video Files:

The following video files are downloaded to `videos/` directory:
- **planes_sample.mp4** - Sample video with planes for single video processing
- **sample_split.mp4** - Video with two camera views for split processing
- **6p-c0.avi** - Multi-camera tracking video (camera 0)
- **6p-c1.avi** - Multi-camera tracking video (camera 1)

## Usage:

```bash
# Run single video example
evileye run configs/single_video.json

# Run video split example  
evileye run configs/single_video_split.json

# Run multi-video example
evileye run configs/multi_videos.json

# Run IP camera example
evileye run configs/single_ip_camera.json

# Run RT-DETR examples
evileye run configs/single_video_rtdetr.json
evileye run configs/multi_videos_rtdetr.json

# Run RF-DETR example
evileye run configs/single_video_rfdetr.json

# Run GStreamer examples
evileye run configs/single_video_gstreamer.json
evileye run configs/ip_camera_gstreamer.json
evileye run configs/usb_camera_gstreamer.json
evileye run configs/image_sequence_gstreamer_jpg.json
evileye run configs/image_sequence_gstreamer_folder.json
```

## Configuration Features:

### Single Video (single_video.json)
- Processes planes_sample.mp4
- Single camera view
- Object detection and tracking
- Enhanced text rendering with 42pt font size

### Video Split (single_video_split.json)
- Processes sample_split.mp4 with 2-way split
- Two camera views from single video
- Separate detection and tracking for each view
- Multi-camera tracking disabled

### Multi Videos (multi_videos.json)
- Processes 6p-c0.avi and 6p-c1.avi
- Multi-camera tracking enabled
- Cross-camera object association
- Enhanced text rendering

### IP Camera (single_ip_camera.json)
- IP camera stream processing
- Real-time object detection
- Enhanced text rendering

### RT-DETR Detectors
- **single_video_rtdetr.json** - Single video with RT-DETR detector
- **multi_videos_rtdetr.json** - Multiple videos with RT-DETR detector
- Uses Ultralytics RT-DETR model (rtdetr-l.pt)
- Real-time detection transformer architecture
- High accuracy object detection

### RF-DETR Detector
- **single_video_rfdetr.json** - Single video with RF-DETR detector
- Uses Roboflow RF-DETR model (rfdetr-nano)
- Transformer-based real-time detection
- Optimized for speed and accuracy

## Notes:

- Sample videos are downloaded to `videos/` directory
- All configurations include admin database credentials
- Enhanced text rendering with configurable font sizes
- Background can be enabled/disabled via text_config

## Customization:

You can modify these configurations or use them as templates:
```bash
# Create your own config based on samples
evileye-create my_config --sources 2 --pipeline PipelineSurveillance
```

For more information, see the main README.md file.
"""

    readme_path = configs_dir / "README_SAMPLES.md"
    with open(readme_path, 'w') as f:
        f.write(readme_content)

    console.print(f"[green]Copied {copied_count} sample configurations[/green]")
    console.print("[green]Created README_SAMPLES.md[/green]")

    console.print("\n[green]Sample deployment completed successfully![/green]")
    console.print("\n[blue]Available sample configurations:[/blue]")
    for config_name in sample_configs:
        if (configs_dir / config_name).exists():
            console.print(f"  [yellow]- {config_name}[/yellow]")

    console.print("\n[blue]Try running a sample:[/blue]")
    console.print("  [yellow]evileye run configs/single_video.json[/yellow]")
    console.print("\n[blue]Downloaded video files:[/blue]")
    for video_name in ["planes_sample.mp4", "sample_split.mp4", "6p-c0.avi", "6p-c1.avi"]:
        if (videos_dir / video_name).exists():
            console.print(f"  [green]{video_name}[/green]")
        else:
            console.print(f"  [yellow]{video_name} (not downloaded)[/yellow]")


@app.command()
def create(
        config_name: str = typer.Argument(None, help="Configuration name"),
        sources: int = typer.Option(0, "--sources", help="Number of sources"),
        pipeline: str = typer.Option("PipelineSurveillance", "--pipeline", help="Pipeline class"),
        source_type: str = typer.Option("video_file", "--source-type", help="Source type"),
        output_dir: str = typer.Option("configs", "--output-dir", help="Output directory"),
        force: bool = typer.Option(False, "--force", help="Overwrite existing file"),
        list_pipelines: bool = typer.Option(False, "--list-pipelines", help="List available pipelines"),
        detector_model: Optional[str] = typer.Option(None, "--detector-model", help="Detector model path"),
        tracker_type: Optional[str] = typer.Option(None, "--tracker-type", help="Tracker type"),
        db_enabled: Optional[bool] = typer.Option(None, "--db/--no-db", help="Enable/disable database"),
) -> None:
    """
    Create new EvilEye configuration file.
    
    Examples:
        evileye create my_config --sources 2
        evileye create my_config --sources 1 --source-type ip_camera
        evileye create test --pipeline PipelineSurveillance --sources 3
        evileye create --list-pipelines
    """
    import os
    import json
    from pathlib import Path
    from evileye.controller.controller import Controller

    # Handle list pipelines
    if list_pipelines:
        try:
            controller_instance = Controller()
            pipeline_classes = controller_instance.get_available_pipeline_classes()

            if not pipeline_classes:
                console.print("[yellow]No pipeline classes found.[/yellow]")
                return

            table = Table(title="Available Pipeline Classes")
            table.add_column("Index", style="cyan")
            table.add_column("Class Name", style="green")

            for i, class_name in enumerate(pipeline_classes, 1):
                table.add_row(str(i), class_name)

            console.print(table)
            console.print(f"\n[blue]Total: {len(pipeline_classes)} pipeline class(es)[/blue]")
            console.print(
                "[blue]Use --pipeline <class_name> to specify a pipeline when creating a configuration.[/blue]")
            return

        except Exception as e:
            console.print(f"[red]Error listing pipeline classes: {e}[/red]")
            raise typer.Exit(1)

    # Validate config_name is provided when not listing pipelines
    if not config_name:
        console.print("[red]Configuration name is required![/red]")
        console.print("[yellow]Usage: evileye create <config_name>[/yellow]")
        console.print("[yellow]Use --help for more information.[/yellow]")
        raise typer.Exit(1)

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Determine output file path
    if not config_name.endswith('.json'):
        config_name += '.json'

    output_path = os.path.join(output_dir, config_name)

    # Check if file already exists
    if os.path.exists(output_path) and not force:
        console.print(f"[red]Configuration file '{output_path}' already exists![/red]")
        console.print("[yellow]Use --force to overwrite or choose a different name.[/yellow]")
        raise typer.Exit(1)

    # Build optional parameters
    detector_params = {}
    if detector_model:
        detector_params['model_path'] = detector_model

    tracker_params = {}
    if tracker_type:
        tracker_params['tracker_type'] = tracker_type

    database_params = {}
    if db_enabled is not None:
        # Only pass safe database parameters (no credentials)
        database_params = {
            "image_dir": "EvilEyeData",
            "preview_width": 300,
            "preview_height": 150
        }

    # Create configuration
    console.print(f"[blue]Creating configuration:[/blue]")
    console.print(f"   Pipeline: {pipeline}")
    console.print(f"   Sources: {sources}")
    console.print(f"   Source type: {source_type}")
    console.print(f"   Output: {output_path}")

    try:
        controller_instance = Controller()
        config_data = controller_instance.create_config(
            num_sources=sources,
            pipeline_class=pipeline,
            source_type=source_type,
            detector_params=detector_params if detector_params else None,
            tracker_params=tracker_params if tracker_params else None,
            database_params=database_params if database_params else None
        )

        # Write configuration to file
        with open(output_path, 'w') as f:
            json.dump(config_data, f, indent=4)

        console.print(f"[green]Configuration created successfully![/green]")
        console.print(f"   File: {output_path}")
        console.print(f"   Size: {os.path.getsize(output_path)} bytes")

    except Exception as e:
        console.print(f"[red]Error creating configuration: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def info() -> None:
    """
    Display EvilEye system information.
    """
    from . import __version__

    table = Table(title="EvilEye System Information")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Version", __version__)
    table.add_row("Python", sys.version)
    table.add_row("Platform", sys.platform)

    # Check for GPU support
    try:
        import torch
        if torch.cuda.is_available():
            gpu_info = f"CUDA {torch.version.cuda} ({torch.cuda.device_count()} devices)"
        else:
            gpu_info = "Not available"
    except ImportError:
        gpu_info = "PyTorch not installed"

    table.add_row("GPU Support", gpu_info)

    # Check for OpenCV
    try:
        import cv2
        opencv_version = cv2.__version__
    except ImportError:
        opencv_version = "Not installed"

    table.add_row("OpenCV", opencv_version)

    console.print(table)


def validate_config(config: dict) -> None:
    """Validate pipeline configuration"""
    required_sections = ["pipeline"]

    for section in required_sections:
        if section not in config:
            raise ValueError(f"Missing required section: {section}")

    pipeline_config = config.get("pipeline", {})
    required_pipeline_sections = ["sources"]

    for section in required_pipeline_sections:
        if section not in pipeline_config:
            raise ValueError(f"Missing required pipeline section: {section}")

    # Validate sources
    sources = pipeline_config.get("sources", [])
    if not sources:
        raise ValueError("At least one source must be configured")

    for i, source in enumerate(sources):
        if "source" not in source:
            raise ValueError(f"Source {i}: missing 'source' field")
        if "camera" not in source:
            raise ValueError(f"Source {i}: missing 'camera' field")


def get_config_description(config_file: Path) -> str:
    """Get description for configuration file"""
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)

        pipeline_config = config.get("pipeline", {})
        sources = pipeline_config.get("sources", [])

        if not sources:
            return "No sources configured"

        source_types = [source.get("source", "unknown") for source in sources]
        return f"{len(sources)} source(s): {', '.join(source_types)}"

    except Exception:
        return "Invalid configuration"


def main() -> None:
    """Main entry point for CLI"""
    app()


if __name__ == "__main__":
    main()
