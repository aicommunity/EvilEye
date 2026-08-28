import { usePlaybackController } from './usePlaybackController';
import { usePlaybackSeek } from './usePlaybackSeek';

/** Seek orchestration extracted from PlaybackPage (phase C3). */
export type PlaybackSeekApi = ReturnType<typeof usePlaybackSeek>;

export type PlaybackControllerApi = ReturnType<typeof usePlaybackController>;

export { usePlaybackSeek, usePlaybackController };
