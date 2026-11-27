# TD-PS-D6 / TD-PS-D7 acceptance log

Budget when the reference clip and weights are present: median `TrackersOut/DetectorsIn` >= 0.92 over 3 runs of 60 seconds, model `models/yolo11m.pt`. The gate does not measure FPS or p95.

| when | tree | median | runs | budget | verdict |
|---|---|---|---|---|---|
| 2026-11-22 12:14 | this host, not the reference setup | n/a | measurement error | >= 0.92 | OPEN |

## 2026-11-22 attempt

Host: Linux, NVIDIA GeForce GTX 1660 SUPER, ffmpeg 4.4.2.

Command (substitute assets; the reference clip `videos/2-GTK_UMPN_ICHI_20250912_082734_trim.mp4` and `models/yolo11m.pt` are not on this machine):

```bash
python scripts/tdps7_acceptance_gate.py \
    --video /home/user/EvilEye/148170-video.mp4 \
    --model models/yolov8n.pt \
    --seconds 10 --runs 1 --timeout 120
```

The available file is 3840x2160 HEVC, not the 2688x1520 H.264 reference. Exit code 2. `DetectorsIn=0`. The pipeline stopped in initialization because `AttributeClassifier` could not open `models/y8mhardhats.pt` (`logs/20261122_121441_evileye_errors.log`). No tracker-delivery ratio was computed, so TD-PS-D6 and TD-PS-D7 stay open.

The harness was corrected in the same change: the generated config is written under `configs/` (so the process chdirs to the repo root and relative model paths resolve), and the score uses `detector_in` / `tracker_out` returned by `run_once`. Previously the gate passed a config dict into a path parameter and then parsed an empty log.
