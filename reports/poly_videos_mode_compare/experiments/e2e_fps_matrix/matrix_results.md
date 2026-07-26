# E2E FPS matrix results

| exp | e2e_fps | e2e_ratio | staleness | in_band | pending_max | score | notes |
| --- | ---: | ---: | ---: | --- | ---: | ---: | --- |
| F2 | 30.0473 | 3.2300936327574896 | 6.3224 | True | 32.666666666666664 | 31.662346816378744 | - |
| F3 | 29.8988 | 3.15984823664937 | 6.4116 | True | 30.333333333333332 | 31.478724118324685 | - |
| F1 | 29.8544 | 3.238636610184201 | 6.3514 | True | 34.333333333333336 | 31.4737183050921 | - |
| F0 | 31.6007 | 3.4874355776764925 | 5.8027 | False | 30.0 | None | staleness_out_of_band, staleness_too_fresh |
| F4 | 29.9547 | 3.216784793814433 | 6.5694 | False | 32.666666666666664 | None | staleness_out_of_band, staleness_too_stale |
| F5 | 31.8494 | 3.342400486939731 | 5.6617 | False | 30.333333333333332 | None | staleness_out_of_band, staleness_too_fresh |
| F6 | 30.4329 | 3.282661690469 | 6.5559 | False | 32.0 | None | staleness_out_of_band, staleness_too_stale |

**Suggested winner:** `F2` (score=31.66)

Score = e2e_tracker_fps + 0.5×e2e_ratio (maximize). Disqualified if staleness not in [5.9, 6.5], staleness<5.9 (too fresh), drops>0, e2e_ratio<3.0, pending_max>45.
