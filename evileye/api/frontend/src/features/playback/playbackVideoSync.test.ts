import { describe, expect, it, vi } from 'vitest';
import { resetPlaybackClockOwner, seekPlaybackVideo, shouldEmitPlaybackClock } from './playbackVideoSync';

function fakeVideo(currentTime = 10, extra: Partial<HTMLVideoElement> = {}) {
  return {
    currentTime,
    pause: vi.fn(),
    seeking: false,
    readyState: 4,
    ...extra,
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

  it('does not pause the video during transient seek settling', () => {
    const video = fakeVideo(3);
    seekPlaybackVideo(video, 1005, 1000, { playing: true, scrubbing: true });
    expect(video.currentTime).toBe(5);
    expect(video.pause).not.toHaveBeenCalled();
  });

  it('clamps seek target to the current playable segment end', () => {
    const video = fakeVideo(0, { duration: 10 });
    seekPlaybackVideo(video, 1015, 1000, { playing: false, segmentEndTs: 1010 });
    expect(video.currentTime).toBeCloseTo(9.999, 3);
  });
});

describe('shouldEmitPlaybackClock', () => {
  it('lets the first ready camera own the clock and keeps lock while that owner seeks', () => {
    resetPlaybackClockOwner();
    const cam1 = fakeVideo(0, { seeking: true, readyState: 1 });
    const cam4 = fakeVideo(0, { seeking: false, readyState: 4 });
    expect(shouldEmitPlaybackClock('Cam1', cam1)).toBe(false);
    expect(shouldEmitPlaybackClock('Cam4', cam4)).toBe(true);
    // Cam4 is owner; while Cam4 seeks, do not hand the clock to Cam1.
    expect(shouldEmitPlaybackClock('Cam4', fakeVideo(0, { seeking: true, readyState: 4 }))).toBe(false);
    expect(shouldEmitPlaybackClock('Cam1', fakeVideo(0, { seeking: false, readyState: 4 }))).toBe(false);
    expect(shouldEmitPlaybackClock('Cam4', fakeVideo(0, { seeking: false, readyState: 4 }))).toBe(true);
    resetPlaybackClockOwner();
    expect(shouldEmitPlaybackClock('Cam1', fakeVideo(0, { seeking: false, readyState: 4 }))).toBe(true);
  });

  it('does not seek again while a seek is already in flight', () => {
    const video = fakeVideo(10, { seeking: true });
    seekPlaybackVideo(video, 1015, 1000, { playing: true, thresholdSec: 0.35 });
    expect(video.currentTime).toBe(10);
  });
});
