import threading
import os
import subprocess
import multiprocessing
from typing import Optional, Dict
from evileye.core.logger import get_module_logger
from evileye.controller.controller import Controller
from evileye.api.core.broker_access import get_broker

""" Module for managing pipelines """

class PipelineState:
    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class PipelineRunner:
    def __init__(self, pipeline_id: int, config_body: dict, name: str = None):
        self.pipeline_id = pipeline_id
        self.config_body = config_body
        self.pipeline_name = name or f"Pipeline-{pipeline_id}" 
        self.controller = None
        self.state = PipelineState.CREATED
        self.error: Optional[str] = None
        self.logger = get_module_logger("api.pipeline_runner")

    def start(self) -> None:
        if self.state in (PipelineState.RUNNING, PipelineState.STARTING):
            self.logger.info(f"Pipeline '{self.pipeline_id}' already running or starting")
            return
        try:
            os.environ["EVILEYE_PIPELINE_ID"] = str(self.pipeline_id)
            self.logger.info(f"Set EVILEYE_PIPELINE_ID={self.pipeline_id} for controller")            
            # Ensure no GUI in API mode
            controller_cfg = self.config_body.setdefault("controller", {})
            controller_cfg["gui_enabled"] = False
            controller_cfg["show_main_gui"] = False
            pipeline_cfg = self.config_body.setdefault("pipeline", {})
            pipeline_cfg["name"] = self.pipeline_name
            self.logger.info(f"Set pipeline name to '{self.pipeline_name}' for streaming")

            if self.controller is None:
                self.controller = Controller()
                self.controller.init(self.config_body)

            self.state = PipelineState.STARTING
            self.logger.info(f"Starting controller for pipeline '{self.pipeline_id}'")
            self.controller.start()
            self.logger.info(f"Controller.start() completed for pipeline '{self.pipeline_id}'")
            # Give controller a moment to initialize
            import time
            time.sleep(5.0)  
            self.state = PipelineState.RUNNING
            self.logger.info(f"Pipeline '{self.pipeline_id}' running")

        except Exception as e:
            self.state = PipelineState.ERROR
            self.error = str(e)
            self.logger.error(f"Pipeline '{self.pipeline_id}' failed to start: {e}")


    def stop(self) -> None:
        self.logger.info(f"Pipeline '{self.pipeline_id}' stop() called")
        if self.controller is None:
            self.state = PipelineState.STOPPED
            self.logger.info(f"Pipeline '{self.pipeline_id}' stopped (no controller)")
            return
        if self.state in (PipelineState.STOPPING, PipelineState.STOPPED):
            self.logger.info(f"Pipeline '{self.pipeline_id}' already stopping or stopped")
            return
        self.state = PipelineState.STOPPING
        self.logger.info(f"Pipeline '{self.pipeline_id}' state set to STOPPING")
        try:
            if self.controller:
                self.logger.info(f"Stopping controller for pipeline '{self.pipeline_id}'")
                try:
                    self.controller.stop()
                    self.logger.info(f"Controller stopped for pipeline '{self.pipeline_id}'")
                except Exception as e:
                    self.logger.error(f"Error stopping controller: {e}")
                
                self.logger.info(f"Releasing controller for pipeline '{self.pipeline_id}'")
                try:
                    self.controller.release()
                    self.logger.info(f"Controller released for pipeline '{self.pipeline_id}'")
                except Exception as e:
                    self.logger.error(f"Error releasing controller: {e}")
            
            self.logger.info(f"Checking for child processes for pipeline '{self.pipeline_id}'")
            processes = multiprocessing.active_children()
            if processes:
                self.logger.info(f"Cleaning up {len(processes)} child processes for pipeline '{self.pipeline_id}'")
                for process in processes:
                    if process.is_alive():
                        self.logger.info(f"Terminating child process {process.pid}")
                        try:
                            process.terminate()
                            process.join(timeout=1.0)  
                            if process.is_alive():
                                self.logger.warning(f"Force killing child process {process.pid}")
                                process.kill()
                                process.join(timeout=0.5)
                        except Exception as e:
                            self.logger.error(f"Error killing process {process.pid}: {e}")
            else:
                self.logger.info(f"No child processes found for pipeline '{self.pipeline_id}'")
            
            try:
                if get_broker().stop_stream(str(self.pipeline_id)):
                    self.logger.info(f"Stopped stream for pipeline '{self.pipeline_id}'")
            except Exception as e:
                self.logger.error(f"Error stopping stream for pipeline '{self.pipeline_id}': {e}")
            
            self.state = PipelineState.STOPPED
            self.logger.info(f"Pipeline '{self.pipeline_id}' stopped successfully")
        except Exception as e:
            self.state = PipelineState.ERROR
            self.error = str(e)
            self.logger.error(f"Pipeline '{self.pipeline_id}' failed to stop: {e}")


class PipelineManager:
    def __init__(self):
        self._lock = threading.RLock()
        self._items: Dict[int, PipelineRunner] = {}
        self._shutdown_called = False
        self.logger = get_module_logger("api.pipeline_manager")

    def create(self, pid: int, config_body: dict, name: str = None) -> Dict:
        with self._lock:
            if pid in self._items:
                raise ValueError("Pipeline already exists")
            runner = PipelineRunner(pid, config_body, name)
            self._items[pid] = runner
            self.logger.info(f"Pipeline '{pid}' created with name '{runner.pipeline_name}'")
            return self._describe_locked(pid, runner)

    def delete(self, pid: int) -> Dict:
        with self._lock:
            runner = self._items.get(pid)
            if runner is None:
                raise KeyError("Pipeline not found")
            if runner.state == PipelineState.RUNNING:
                raise RuntimeError("Stop pipeline before delete")
            self._items.pop(pid)
            self.logger.info(f"Pipeline '{pid}' deleted")
            return {"id": pid, "status": "deleted"}

    def start(self, pid: int) -> Dict:
        with self._lock:
            runner = self._items.get(pid)
            if runner is None:
                raise KeyError("Pipeline not found")
        
        runner.start()
        
        with self._lock:
            return {
                "id": pid,
                "name": runner.pipeline_name,
                "state": runner.state,
                "error": runner.error,
            }

    def stop(self, pid: int) -> Dict:
        with self._lock:
            runner = self._items.get(pid)
            if runner is None:
                raise KeyError("Pipeline not found")
        
        runner.stop()
        
        with self._lock:
            return {
                "id": pid,
                "name": runner.pipeline_name,
                "state": runner.state,
                "error": runner.error,
            }

    def list(self) -> Dict[int, Dict]:
        with self._lock:
            return {pid: self._describe_locked(pid, r) for pid, r in self._items.items()}

    def describe(self, pid: int) -> Dict:
        with self._lock:
            runner = self._items.get(pid)
            if runner is None:
                raise KeyError("Pipeline not found")
            return self._describe_locked(pid, runner)

    def _get_runner(self, pid: int) -> Optional[PipelineRunner]:
        """Get runner for a specific pipeline (thread-safe)."""
        with self._lock:
            return self._items.get(pid)
    
    def _describe_locked(self, pid: int, runner: PipelineRunner) -> Dict:
        return {
            "id": pid,
            "name": runner.pipeline_name,
            "state": runner.state,
            "error": runner.error,
        }

    def shutdown(self) -> None:
        with self._lock:
            if self._shutdown_called:
                self.logger.info("PipelineManager shutdown already called, skipping")
                return
            self._shutdown_called = True
        
        self.logger.info("PipelineManager shutdown initiated")
        
        with self._lock:
            ids = list(self._items.keys())
        
        self.logger.info(f"Stopping {len(ids)} pipelines: {ids}")
        
        for pid in ids:
            try:
                self.logger.info(f"Stopping pipeline '{pid}'")
                self.stop(pid)
            except Exception as e:
                self.logger.error(f"Error stopping pipeline '{pid}': {e}")
        
        import time
        time.sleep(1.0)
        
        processes = multiprocessing.active_children()
        if processes:
            self.logger.warning(f"Found {len(processes)} active processes after pipeline stop, force cleaning up...")
            for process in processes:
                if process.is_alive():
                    self.logger.warning(f"Force terminating process {process.pid} ({process.name})")
                    try:
                        process.terminate()
                        process.join(timeout=0.5)
                        if process.is_alive():
                            self.logger.error(f"Process {process.pid} still alive, force killing")
                            process.kill()
                            process.join(timeout=0.2)
                    except Exception as e:
                        self.logger.error(f"Error killing process {process.pid}: {e}")
        
        remaining = multiprocessing.active_children()
        if remaining:
            self.logger.error(f"CRITICAL: Still {len(remaining)} processes alive after cleanup!")
            for process in remaining:
                self.logger.error(f"Process {process.pid} ({process.name}) still alive")
                try:
                    if hasattr(process, 'kill'):
                        process.kill()
                    else:
                        if os.name == 'nt':  
                            subprocess.run(['taskkill', '/F', '/PID', str(process.pid)], 
                                         capture_output=True)
                        else:  
                            os.kill(process.pid, 9)  
                except Exception as e:
                    self.logger.error(f"Failed to kill process {process.pid}: {e}")
        
        self.logger.info("PipelineManager shutdown completed")


