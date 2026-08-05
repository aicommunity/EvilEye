import { useEffect, useRef } from 'react';

export function SplitPlaybackCell({
  videoUrl,
  srcCoords,
  label,
  getPosition,
  playing,
  speed,
  startTs,
}: {
  videoUrl: string;
  srcCoords: [number, number, number, number];
  label: string;
  getPosition: () => number;
  playing: boolean;
  speed: number;
  startTs: number;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const getPositionRef = useRef(getPosition);
  getPositionRef.current = getPosition;

  useEffect(() => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return;

    const [sx, sy, sw, sh] = srcCoords;
    const draw = () => {
      if (video.readyState < 2) return;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      const cw = canvas.width;
      const ch = canvas.height;
      if (cw <= 0 || ch <= 0) return;
      ctx.drawImage(video, sx, sy, sw, sh, 0, 0, cw, ch);
    };

    video.addEventListener('timeupdate', draw);
    video.addEventListener('loadeddata', draw);
    draw();
    return () => {
      video.removeEventListener('timeupdate', draw);
      video.removeEventListener('loadeddata', draw);
    };
  }, [videoUrl, srcCoords]);

  useEffect(() => {
    const container = containerRef.current;
    const canvas = canvasRef.current;
    if (!container || !canvas) return;
    const ro = new ResizeObserver(() => {
      const rect = container.getBoundingClientRect();
      const [,, sw, sh] = srcCoords;
      const aspect = sw / sh;
      let w = rect.width;
      let h = w / aspect;
      if (h > rect.height) {
        h = rect.height;
        w = h * aspect;
      }
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;
      canvas.width = Math.max(1, Math.round(w));
      canvas.height = Math.max(1, Math.round(h));
    });
    ro.observe(container);
    return () => ro.disconnect();
  }, [srcCoords]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    video.playbackRate = speed;
    if (playing) void video.play().catch(() => null);
    else video.pause();
  }, [playing, speed, videoUrl]);

  useEffect(() => {
    let raf = 0;
    const tick = () => {
      const video = videoRef.current;
      if (video && videoUrl) {
        const local = Math.max(0, getPositionRef.current() - startTs);
        if (Math.abs(video.currentTime - local) > 0.4) {
          try {
            video.currentTime = local;
          } catch {
            /* ignore */
          }
        }
      }
      if (playing) raf = window.requestAnimationFrame(tick);
    };
    if (playing) tick();
    return () => {
      if (raf) window.cancelAnimationFrame(raf);
    };
  }, [playing, videoUrl, startTs]);

  return (
    <article className="camera-card playback-cell">
      <div className="camera-card-head">
        <span className="run-name">{label}</span>
      </div>
      <div ref={containerRef} className="split-playback-container">
        <video ref={videoRef} src={videoUrl} preload="auto" style={{ display: 'none' }} muted playsInline />
        <canvas ref={canvasRef} className="camera-preview" />
      </div>
    </article>
  );
}
