import { useEffect } from 'react';
import { streamMjpgUrl, type StateCamera, type StreamMetadata } from '../../api';
import { Button } from '../../components/ui';
import { useMjpegLifecycle } from '../../hooks/useMjpegLifecycle';
import { useI18n } from '../../i18n';
import { OverlayCanvas } from './OverlayCanvas';
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
  const src = running
    ? streamMjpgUrl(camera.run_id, 8, camera.source_id ?? null)
    : '';

  useMjpegLifecycle(running ? camera.run_id : null, camera.source_id ?? null);
  const meta = useRunMetadataWs(running ? camera.run_id : null, camera.source_id ?? null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

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
      <div className="expanded-camera-media">
        {src ? (
          <>
            <img src={src} alt={camera.source_name} className="expanded-camera-frame" />
            <OverlayCanvas meta={meta as StreamMetadata | null} />
          </>
        ) : (
          <div className="camera-preview camera-preview-empty">{t('live.camera.stopped')}</div>
        )}
      </div>
    </div>
  );
}
