# Remote branch inventory (TD-PS-D5)

Snapshot: 2026-11-22, after `git fetch origin` without prune. 45 remote branches. Nothing here was deleted. Deletion is a separate owner decision; this file is only the list.

"Merged into develop" means `git branch -r --merged develop` contains the remote-tracking ref. A merged branch can still be removed only after the owner checks that no one uses it.

## autorefactor_* (6)

- `origin/autorefactor` — merged into develop
- `origin/autorefactor_capture` — merged into develop
- `origin/autorefactor_db` — merged into develop
- `origin/autorefactor_detection` — merged into develop
- `origin/autorefactor_preprocessor` — not merged into develop
- `origin/autorefactor_tracking` — merged into develop

## hotfix (6)

- `origin/13-hotfix` — merged into develop
- `origin/14-hotfix` — merged into develop
- `origin/15-hotfix` — merged into develop
- `origin/dev_hotfixes` — merged into develop
- `origin/hotfix` — merged into develop
- `origin/hotfix_reconnect` — merged into develop

`origin/12-webhotifx` is spelled like a hotfix and is merged into develop. It is listed again under other.

## experiments (1)

- `origin/experiments` — not merged into develop

## other (31, excluding `origin/develop`)

Merged into develop:

- `origin/12-webhotifx`
- `origin/api-refactoring`
- `origin/attr_events`
- `origin/benchmarks`
- `origin/codex/restore-zone-events`
- `origin/events_online`
- `origin/feat/reid`
- `origin/fix/audit-corrections`
- `origin/full_web_control`
- `origin/gstreamer`
- `origin/gui_refactor`
- `origin/journal_upd`
- `origin/labels`
- `origin/main`
- `origin/mt_refactoring`
- `origin/mt_refactoring2`
- `origin/mt_support`
- `origin/multiprocessing`
- `origin/perf_fixes`
- `origin/plugin_support`
- `origin/preprocessing`
- `origin/recording`
- `origin/refactor/reid-buffer`
- `origin/rest-api`
- `origin/web_update`
- `origin/win_deploy`

Not merged into develop:

- `origin/async_refactor`
- `origin/autor_det_pass1_bad`
- `origin/camera_calibration`
- `origin/cap_test`
- `origin/det_memleack`

## Not merged, so do not treat as cleanup

`autorefactor_preprocessor`, `experiments`, `async_refactor`, `autor_det_pass1_bad`, `camera_calibration`, `cap_test`, `det_memleack`.
