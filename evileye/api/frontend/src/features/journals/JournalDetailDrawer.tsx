import { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  journalFrameUrl,
  journalsApi,
  journalPreviewUrl,
  journalVideoUrl,
  type JournalGroupedRow,
  type StreamMetadata,
} from '../../api';
import { Button } from '../../components/ui';
import { useI18n } from '../../i18n';
import { MetadataOverlayLayer } from '../overlay/MetadataOverlayLayer';
import { useImageLetterbox } from '../overlay/useMediaLetterbox';
import { redactMediaCredentials, rowKey, unixFromJournalTime, type JournalType } from './journalMath';

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
  const [imgLoaded, setImgLoaded] = useState(0);
  const mode: 'found' | 'lost' = enriched.has_found_preview || enriched.preview ? 'found' : 'lost';
  const previewPath = mode === 'found' ? enriched.preview : enriched.lost_preview;
  const videoPath =
    mode === 'found' ? enriched.found_video_path : enriched.lost_video_path || enriched.stream_video_path;
  const bbox = mode === 'found' ? enriched.bbox_found : enriched.bbox_lost;
  const zone = mode === 'found' ? enriched.zone_coords : null;
  const ts = unixFromJournalTime(enriched.time);
  const wrapRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const layoutBox = useImageLetterbox(wrapRef, imgRef, [previewPath, imgLoaded]);

  const snapshotMeta = useMemo((): StreamMetadata | null => {
    const objects =
      bbox && Array.isArray(bbox) && bbox.length === 4
        ? [
            {
              bbox: bbox.map(Number) as [number, number, number, number],
              class_name: enriched.class_name != null ? String(enriched.class_name) : null,
            },
          ]
        : [];
    const zones =
      zone && Array.isArray(zone) && zone.length >= 3
        ? [
            {
              points: zone.map((p) => [Number(p[0]), Number(p[1])] as [number, number]),
            },
          ]
        : [];
    if (!objects.length && !zones.length) return null;
    return { objects, zones };
  }, [bbox, zone, enriched.class_name]);

  useEffect(() => {
    setEnriched(row);
    setShowVideo(false);
    setImgLoaded(0);
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
                onLoad={() => setImgLoaded((n) => n + 1)}
              />
              <MetadataOverlayLayer meta={snapshotMeta} layoutBox={layoutBox} density="full" />
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
