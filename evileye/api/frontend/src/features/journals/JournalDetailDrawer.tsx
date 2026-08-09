import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  journalFrameUrl,
  journalsApi,
  journalPreviewUrl,
  journalVideoUrl,
  type JournalGroupedRow,
} from '../../api';
import { Button } from '../../components/ui';
import { useI18n } from '../../i18n';
import { letterboxRect, redactMediaCredentials, rowKey, unixFromJournalTime, type JournalType } from './journalMath';

export function JournalDetailDrawer({
  row,
  journalType,
  onClose,
}: {
  row: JournalGroupedRow;
  journalType: JournalType;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const [enriched, setEnriched] = useState<JournalGroupedRow>(row);
  const [showVideo, setShowVideo] = useState(false);
  const mode: 'found' | 'lost' = enriched.has_found_preview || enriched.preview ? 'found' : 'lost';
  const previewPath = mode === 'found' ? enriched.preview : enriched.lost_preview;
  const videoPath =
    mode === 'found' ? enriched.found_video_path : enriched.lost_video_path || enriched.stream_video_path;
  const bbox = mode === 'found' ? enriched.bbox_found : enriched.bbox_lost;
  const zone = mode === 'found' ? enriched.zone_coords : null;
  const ts = unixFromJournalTime(enriched.time);
  const wrapRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const [box, setBox] = useState({ left: 0, top: 0, width: 0, height: 0 });

  useEffect(() => {
    setEnriched(row);
    setShowVideo(false);
    const key = rowKey(row);
    if (!key) return;
    let cancelled = false;
    void journalsApi.rowMeta(key, journalType).then((meta) => {
      if (!cancelled && meta) setEnriched((prev) => ({ ...prev, ...meta }));
    }).catch(() => null);
    return () => {
      cancelled = true;
    };
  }, [row, journalType]);

  useLayoutEffect(() => {
    const update = () => {
      const wrap = wrapRef.current;
      const img = imgRef.current;
      if (!wrap || !img || !img.naturalWidth) return;
      setBox(letterboxRect(wrap.clientWidth, wrap.clientHeight, img.naturalWidth, img.naturalHeight));
    };
    update();
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, [previewPath]);

  return (
    <div className="modal open journal-detail-modal" role="dialog">
      <div className="modal-backdrop" onClick={onClose} />
      <div className="modal-content journal-detail-content">
        <header className="journal-detail-header">
          <h3>
            {String(enriched.event ?? t('journals.eventFallback'))} ·{' '}
            {redactMediaCredentials(enriched.source ?? '')}
          </h3>
          <Button size="sm" variant="outline" onClick={onClose} aria-label={t('common.close')}>
            ×
          </Button>
        </header>
        <div id="journal-detail-body" className="modal-body">
          <p className="hint">{redactMediaCredentials(enriched.information ?? '')}</p>
          {previewPath ? (
            <div ref={wrapRef} className="journal-preview-wrap" style={{ position: 'relative', maxWidth: 640, minHeight: 200 }}>
              <img
                ref={imgRef}
                className="journal-detail-media"
                src={journalPreviewUrl({
                  path: String(previewPath),
                  date: enriched.date_folder,
                  journalType,
                  mode,
                })}
                alt={t('journals.preview')}
                style={{ width: '100%', display: 'block' }}
                onLoad={() => {
                  const wrap = wrapRef.current;
                  const img = imgRef.current;
                  if (!wrap || !img) return;
                  setBox(letterboxRect(wrap.clientWidth, wrap.clientHeight, img.naturalWidth, img.naturalHeight));
                }}
              />
                <svg
                className="journal-preview-overlay"
                viewBox="0 0 100 100"
                preserveAspectRatio="none"
                style={{
                  position: 'absolute',
                  left: box.left,
                  top: box.top,
                  width: box.width || '100%',
                  height: box.height || '100%',
                  pointerEvents: 'none',
                }}
              >
                {bbox && Array.isArray(bbox) && bbox.length === 4 ? (
                  <rect
                    x={`${Number(bbox[0]) * 100}%`}
                    y={`${Number(bbox[1]) * 100}%`}
                    width={`${(Number(bbox[2]) - Number(bbox[0])) * 100}%`}
                    height={`${(Number(bbox[3]) - Number(bbox[1])) * 100}%`}
                    fill="none"
                    stroke="#22c55e"
                    strokeWidth="2"
                  />
                ) : null}
                {zone && Array.isArray(zone) && zone.length >= 3 ? (
                  <polygon
                    points={zone.map((p) => `${Number(p[0]) * 100},${Number(p[1]) * 100}`).join(' ')}
                    fill="rgba(59,130,246,0.15)"
                    stroke="#3b82f6"
                    strokeWidth="2"
                  />
                ) : null}
              </svg>
            </div>
          ) : null}
          {previewPath ? (
            <p>
              <a
                href={journalFrameUrl({
                  path: String(previewPath),
                  date: enriched.date_folder,
                  journalType,
                  mode,
                })}
                target="_blank"
                rel="noreferrer"
              >
                {t('journals.fullFrame')}
              </a>
            </p>
          ) : null}
          {videoPath ? (
            showVideo ? (
              <video controls autoPlay src={journalVideoUrl({ path: String(videoPath) })} style={{ width: '100%', maxWidth: 640 }} />
            ) : (
              <Button size="sm" variant="outline" onClick={() => setShowVideo(true)}>
                {t('journals.playVideo')}
              </Button>
            )
          ) : null}
          <div className="toolbar" style={{ marginTop: '1rem' }}>
            {ts != null ? (
              <Link
                className="btn btn-primary btn-sm"
                to={`/playback?camera=${encodeURIComponent(String(enriched.source ?? ''))}&t=${ts}&row_key=${encodeURIComponent(String(enriched.row_key ?? ''))}`}
              >
                {t('journals.openPlayback')}
              </Link>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}
