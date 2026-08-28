/**
 * Shared video sync engine for archive playback tiles.
 * Wraps segment picking, applySync, and decoder recovery from PlaybackCameraView.
 */
export {
  usePlaybackCameraSlot as usePlaybackVideoEngine,
  type PlaybackMediaSlot,
} from './PlaybackCameraView';
