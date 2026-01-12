import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import QApplication
    pyqt_version = 6
except Exception:
    from PyQt5.QtWidgets import QApplication
    pyqt_version = 5

import numpy as np

from evileye.visualization_modules.roi_editor_window import ROIEditorWindow


def make_dummy_image(w: int = 320, h: int = 240):
    img = np.zeros((h, w, 3), dtype=np.uint8)
    # white background
    img[:] = (255, 255, 255)
    return img


def main():
    app = QApplication.instance() or QApplication(sys.argv)

    params = {"pipeline": {"detectors": []}, "visualizer": {}}
    win = ROIEditorWindow(params)

    # Track signal emission
    result = {"emitted": False, "accepted": None}

    def on_closed(rois_xyxy, source_id, detector_index, accepted):
        result["emitted"] = True
        result["accepted"] = accepted

    win.roi_editor_closed.connect(on_closed)

    # Provide context and image
    src_id = 0
    win.set_context(src_id, -1)
    cv_img = make_dummy_image()
    win.set_cv_image(src_id, cv_img)
    # No ROIs set — baseline empty state; ensure snapshot saved as empty
    win.set_rois_from_detector([])

    # Show and close immediately
    win.show()
    app.processEvents()
    win.close()
    app.processEvents()

    # Small wait to let signals propagate
    t0 = time.time()
    while not result["emitted"] and (time.time() - t0) < 2.0:
        app.processEvents()
        time.sleep(0.01)

    if not result["emitted"]:
        print("FAIL: roi_editor_closed signal was not emitted (possible dialog hang)")
        return 1
    if result["accepted"] is not False:
        print(f"FAIL: expected accepted=False when no changes, got {result['accepted']}")
        return 1

    print("OK: ROIEditorWindow closed without save dialog when no changes")
    return 0


if __name__ == "__main__":
    sys.exit(main())


