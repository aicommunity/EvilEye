import { Link } from 'react-router-dom';
import { journalFrameUrl, journalPreviewUrl, journalVideoUrl, type JournalGroupedRow } from '../../api';
import { Button } from '../../components/ui';
import { bboxSvg, unixFromJournalTime, type JournalType } from './journalMath';

export function JournalDetailDrawer({
  row,
  journalType,
  onClose,
}: {
  row: JournalGroupedRow;
  journalType: JournalType;
  onClose: () => void;
}) {
  const mode: 'found' | 'lost' = row.has_found_preview || row.preview ? 'found' : 'lost';
  const previewPath = mode === 'found' ? row.preview : row.lost_preview;
  const videoPath =
    mode === 'found' ? row.found_video_path : row.lost_video_path || row.stream_video_path;
  const bbox = mode === 'found' ? row.bbox_found : row.bbox_lost;
  const zone = mode === 'found' ? row.zone_coords : null;
  const ts = unixFromJournalTime(row.time);

  return (
    <div className="modal open journal-detail-modal" role="dialog">
      <div className="modal-backdrop" onClick={onClose} />
      <div className="modal-content journal-detail-content">
        <header className="journal-detail-header">
          <h3>
            {String(row.event ?? 'Событие')} · {String(row.source ?? '')}
          </h3>
          <Button size="sm" variant="outline" onClick={onClose}>
            ×
          </Button>
        </header>
        <div id="journal-detail-body" className="modal-body">
          <p className="hint">{String(row.information ?? '')}</p>
          {previewPath ? (
            <div className="journal-preview-wrap" style={{ position: 'relative', maxWidth: 640 }}>
              <img
                className="journal-detail-media"
                src={journalPreviewUrl({
                  path: String(previewPath),
                  date: row.date_folder,
                  journalType,
                  mode,
                })}
                alt="preview"
                style={{ width: '100%' }}
              />
              <svg
                className="journal-preview-overlay"
                viewBox="0 0 100 100"
                preserveAspectRatio="none"
                style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}
                dangerouslySetInnerHTML={{ __html: bboxSvg(bbox as number[] | null, zone as number[][] | null) }}
              />
            </div>
          ) : null}
          {previewPath ? (
            <p>
              <a
                href={journalFrameUrl({
                  path: String(previewPath),
                  date: row.date_folder,
                  journalType,
                  mode,
                })}
                target="_blank"
                rel="noreferrer"
              >
                Полный кадр
              </a>
            </p>
          ) : null}
          {videoPath ? (
            <video controls src={journalVideoUrl({ path: String(videoPath) })} style={{ width: '100%', maxWidth: 640 }} />
          ) : null}
          <div className="toolbar" style={{ marginTop: '1rem' }}>
            {ts != null ? (
              <Link
                className="btn btn-primary btn-sm"
                to={`/playback?camera=${encodeURIComponent(String(row.source ?? ''))}&t=${ts}&row_key=${encodeURIComponent(String(row.row_key ?? ''))}`}
              >
                Открыть в Playback
              </Link>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}
