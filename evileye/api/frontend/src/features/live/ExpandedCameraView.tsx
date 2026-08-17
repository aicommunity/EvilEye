import { useEffect, useRef, useState } from 'react';
import { type StateCamera, type StreamMetadata } from '../../api';
import { Button } from '../../components/ui';
import { useMjpegStream } from '../../hooks/useMjpegStream';
import { useI18n } from '../../i18n';
import { OverlayCanvas } from './OverlayCanvas';
import { useImageLetterbox } from './useImageLetterbox';
import { useRunMetadataWs } from './useRunMetadataWs';

export function ExpandedCameraView({
  camera,
  onClose,
}: {
  camera: StateCamera;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const running = camera.run_state === 'running';
  const mediaRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const { phase, src, error, retry, onImgError, onImgLoad, attempt } = useMjpegStream({
    rid: running ? camera.run_id : null,
    sourceId: camera.source_id ?? null,
    fps: 8,
    enabled: running,
  });
  const meta = useRunMetadataWs(running ? camera.run_id : null, camera.source_id ?? null);
  const [imgLoaded, setImgLoaded] = useState(0);
  const layoutBox = useImageLetterbox(mediaRef, imgRef, [src, attempt, imgLoaded]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const showPlaceholder = !running || !src || phase === 'warming' || phase === 'error';

  const handleImgLoad = () => {
    onImgLoad();
    setImgLoaded((n) => n + 1);
  };

  return (
    <div className="expanded-camera-view">
      <div className="expanded-camera-toolbar">
        <strong>{camera.source_name}</strong>
        <span className="hint">
          {t('live.camera.runLabel', { id: camera.run_id, sid: camera.source_id ?? '—' })}
        </span>
        <Button size="sm" variant="outline" onClick={onClose}>
          {t('live.expandClose')}
        </Button>
      </div>
      <div className="expanded-camera-media" ref={mediaRef}>
        {!running ? (
          <div className="expanded-camera-placeholder">{t('live.camera.stopped')}</div>
        ) : (
          <>
            {src ? (
              <>
                <img
                  ref={imgRef}
                  key={attempt}
                  src={src}
                  alt={camera.source_name}
                  className="expanded-camera-frame"
                  onError={onImgError}
                  onLoad={handleImgLoad}
                />
                <OverlayCanvas meta={meta as StreamMetadata | null} layoutBox={layoutBox} density="full" />
              </>
            ) : null}
            {showPlaceholder && !src ? (
              <div className="expanded-camera-placeholder">
                {phase === 'error' || error ? (
                  <>
                    <p>{t('live.stream.streamError')}</p>
                    <Button size="sm" variant="outline" onClick={retry}>
                      {t('live.stream.retry')}
                    </Button>
                  </>
                ) : (
                  <p>{t('live.stream.connecting')}</p>
                )}
              </div>
            ) : null}
            {phase === 'error' && src ? (
              <div className="expanded-camera-placeholder expanded-camera-placeholder--overlay">
                <p>{t('live.stream.streamError')}</p>
                <Button size="sm" variant="outline" onClick={retry}>
                  {t('live.stream.retry')}
                </Button>
              </div>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}
