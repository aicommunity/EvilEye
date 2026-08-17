import { describe, expect, it, vi } from 'vitest';
import { seekPlaybackVideo } from './playbackVideoSync';

function fakeVideo(currentTime = 10) {
  return {
    currentTime,
    pause: vi.fn(),
  } as unknown as HTMLVideoElement;
}

describe('seekPlaybackVideo', () => {
  it('seeks paused video on 1s steps without pausing again', () => {
    const video = fakeVideo(10);
    seekPlaybackVideo(video, 1011, 1000, { playing: false });
    expect(video.currentTime).toBe(11);
    expect(video.pause).not.toHaveBeenCalled();
  });

  it('does not seek paused video when already on the same frame', () => {
    const video = fakeVideo(11);
    seekPlaybackVideo(video, 1011, 1000, { playing: false });
    expect(video.currentTime).toBe(11);
  });

  it('does not pause while playing to catch up', () => {
    const video = fakeVideo(10);
    seekPlaybackVideo(video, 1012, 1000, { playing: true, thresholdSec: 0.35 });
    expect(video.currentTime).toBe(12);
    expect(video.pause).not.toHaveBeenCalled();
  });
});
