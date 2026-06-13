"""Shared-memory + spawn: disable auto resource_tracker tracking for /psm_ segments.

Python registers each SharedMemory attach in a global resource_tracker subprocess.
With spawn and cross-process unlink that produces KeyError on UNREGISTER and leaked
/psm_ noise. We track SHM lifecycle explicitly in SharedFrameTransport instead.
"""


def apply_resource_tracker_patch() -> None:
    import multiprocessing.resource_tracker as mrt

    if getattr(mrt, "_evileye_patched", False):
        return
    mrt._evileye_patched = True

    if not hasattr(mrt, "_evileye_original_register"):
        mrt._evileye_original_register = mrt.register
        mrt._evileye_original_unregister = mrt.unregister

    def _register(name, rtype):
        if rtype == "shared_memory":
            return
        return mrt._evileye_original_register(name, rtype)

    def _unregister(name, rtype):
        if rtype == "shared_memory":
            return
        return mrt._evileye_original_unregister(name, rtype)

    mrt.register = _register
    mrt.unregister = _unregister

    _orig_main = mrt.main

    def _main(fd):
        import signal
        import sys
        import warnings

        from multiprocessing.resource_tracker import (
            _CLEANUP_FUNCS,
            _HAVE_SIGMASK,
            _IGNORED_SIGNALS,
        )

        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        if _HAVE_SIGMASK:
            signal.pthread_sigmask(signal.SIG_UNBLOCK, _IGNORED_SIGNALS)

        for f in (sys.stdin, sys.stdout):
            try:
                f.close()
            except Exception:
                pass

        cache = {rtype: set() for rtype in _CLEANUP_FUNCS.keys()}
        try:
            with open(fd, "rb") as f:
                for line in f:
                    try:
                        cmd, name, rtype = line.strip().decode("ascii").split(":")
                        if _CLEANUP_FUNCS.get(rtype) is None:
                            continue
                        if cmd == "REGISTER":
                            cache[rtype].add(name)
                        elif cmd == "UNREGISTER":
                            cache[rtype].discard(name)
                        elif cmd == "PROBE":
                            pass
                    except Exception:
                        try:
                            sys.excepthook(*sys.exc_info())
                        except Exception:
                            pass
        finally:
            for rtype, rtype_cache in cache.items():
                for name in list(rtype_cache):
                    try:
                        _CLEANUP_FUNCS[rtype](name)
                    except Exception:
                        pass

    mrt.main = _main
