import { useEffect, useState } from 'react';
import { streamSnapshotUrl, type StateCamera, type StreamMetadata } from '../../api';
import { Badge, Button } from '../../components/ui';
import { OverlayCanvas } from './OverlayCanvas';
import { useRunMetadataWs } from './useRunMetadataWs';

export function CameraTile({
  camera,
  useMjpeg,
  active = true,
  onOpen,
  draggable,
  onDragStart,
  onDrop,
}: {
  camera: StateCamera;
  useMjpeg: boolean;
  active?: boolean;
  onOpen: () => void;
  draggable?: boolean;
  onDragStart?: () => void;
  onDrop?: () => void;
}) {
  const canPreview = camera.run_state === 'running';
  const [snapTs, setSnapTs] = useState(Date.now());
  const meta = useRunMetadataWs(
    canPreview && useMjpeg && active ? camera.run_id : null,
    camera.source_id,
  );

  useEffect(() => {
    if (!canPreview || useMjpeg || !active) return;
    const id = window.setInterval(() => setSnapTs(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [canPreview, useMjpeg, active]);

  const imgSrc =
    canPreview && active
      ? useMjpeg
        ? `/api/v1/runs/${camera.run_id}/stream.mjpg?fps=8${camera.source_id != null ? `&source_id=${camera.source_id}` : ''}`
        : `${streamSnapshotUrl(camera.run_id, camera.source_id)}${streamSnapshotUrl(camera.run_id, camera.source_id).includes('?') ? '&' : '?'}t=${snapTs}`
      : '';

  return (
    <article
      className="camera-card"
      draggable={draggable}
      onDragStart={onDragStart}
      onDragOver={(e) => e.preventDefault()}
      onDrop={onDrop}
    >
      <div className="camera-card-head">
        <span className="run-name">{camera.source_name}</span>
        <Badge state={camera.run_state}>{camera.run_state}</Badge>
      </div>
      <p className="hint">
        Run #{camera.run_id} · source #{camera.source_id ?? '—'}
      </p>
      {canPreview ? (
        <div className="camera-preview-wrap" style={{ position: 'relative' }}>
          {imgSrc ? (
            <img src={imgSrc} alt={camera.source_name} className="camera-preview" />
          ) : (
            <div className="camera-preview camera-preview-empty">Вне зоны видимости</div>
          )}
          {useMjpeg ? <OverlayCanvas meta={meta as StreamMetadata | null} /> : null}
        </div>
      ) : (
        <div className="camera-preview camera-preview-empty">Запуск остановлен</div>
      )}
      <div className="camera-actions">
        <Button size="sm" variant="outline" disabled={!canPreview} onClick={onOpen}>
          Открыть поток
        </Button>
      </div>
    </article>
  );
}
