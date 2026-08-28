import { useEffect, useRef, useState } from 'react';
import { editorsApi, stateApi, streamSnapshotUrl, type ZoneItem } from '../../api';
import { Button } from '../../components/ui';
import { useToast } from '../../components/ui/Toast';
import { useI18n } from '../../i18n';
import { formatInt, INT_STEP, parseIntInput } from './numberFormat';

export function ZoneCanvas({
  configName,
  sourceId,
  onSourceIdChange,
  readOnly,
  onSaved,
}: {
  configName: string;
  sourceId: number;
  onSourceIdChange: (id: number) => void;
  readOnly: boolean;
  onSaved?: (restartRequired: boolean) => void;
}) {
  const { showError, showSuccess } = useToast();
  const { t } = useI18n();
  const [zones, setZones] = useState<ZoneItem[]>([]);
  const [mode, setMode] = useState<'rect' | 'polygon'>('rect');
  const [draft, setDraft] = useState<[number, number][]>([]);
  const [bgUrl, setBgUrl] = useState<string | null>(null);
  const [cameraLabel, setCameraLabel] = useState<string | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void editorsApi
      .getZones(configName, sourceId)
      .then((r) => setZones(r.zones ?? []))
      .catch((e) => showError(e.message));
  }, [configName, sourceId, showError]);

  useEffect(() => {
    let cancelled = false;
    void stateApi
      .cameras('current')
      .then((res) => {
        if (cancelled) return;
        const cams = res.items ?? [];
        const match = cams.find((c) => c.source_id === sourceId && c.run_state === 'running');
        if (match) {
          setCameraLabel(match.source_name || null);
          const base = streamSnapshotUrl(match.run_id, sourceId);
          setBgUrl(`${base}${base.includes('?') ? '&' : '?'}t=${Date.now()}`);
        } else {
          setCameraLabel(null);
          setBgUrl(null);
        }
      })
      .catch(() => {
        if (!cancelled) setBgUrl(null);
      });
    return () => {
      cancelled = true;
    };
  }, [sourceId]);

  const toNorm = (e: React.MouseEvent): [number, number] => {
    const rect = wrapRef.current!.getBoundingClientRect();
    return [(e.clientX - rect.left) / rect.width, (e.clientY - rect.top) / rect.height];
  };

  return (
    <div>
      <div className="toolbar">
        <label>
          {cameraLabel
            ? t('configure.editors.zoneCameraLabel', { name: cameraLabel, id: sourceId })
            : t('configure.editors.zoneCameraUnknown', { id: sourceId })}{' '}
          <input
            type="number"
            step={INT_STEP}
            min={0}
            value={formatInt(sourceId)}
            onChange={(e) => onSourceIdChange(parseIntInput(e.target.value) ?? 0)}
          />
        </label>
        <Button size="sm" variant={mode === 'rect' ? 'primary' : 'outline'} onClick={() => setMode('rect')}>
          Rect
        </Button>
        <Button size="sm" variant={mode === 'polygon' ? 'primary' : 'outline'} onClick={() => setMode('polygon')}>
          Polygon
        </Button>
        {!readOnly ? (
          <Button
            variant="primary"
            onClick={() =>
              void editorsApi
                .putZones(configName, sourceId, zones)
                .then((r) => {
                  if (r.restart_required) showSuccess(t('common.savedRestart'));
                  else showSuccess(t('common.savedApplied'));
                  onSaved?.(Boolean(r.restart_required));
                })
                .catch((e) => showError(e.message))
            }
          >
            {t('configure.editors.saveZones')}
          </Button>
        ) : null}
      </div>
      <div
        ref={wrapRef}
        style={{
          position: 'relative',
          width: '100%',
          maxWidth: 640,
          aspectRatio: '16/9',
          background: '#111',
          border: '1px solid var(--border)',
          backgroundImage: bgUrl ? `url(${bgUrl})` : undefined,
          backgroundSize: 'contain',
          backgroundRepeat: 'no-repeat',
          backgroundPosition: 'center',
        }}
        onClick={(e) => {
          if (readOnly) return;
          const p = toNorm(e);
          if (mode === 'polygon') {
            setDraft((d) => [...d, p]);
            return;
          }
          if (draft.length === 0) setDraft([p]);
          else {
            const a = draft[0];
            setZones((z) => [
              ...z,
              {
                type: 'rect',
                name: `zone_${z.length + 1}`,
                points: [a, [p[0], a[1]], p, [a[0], p[1]]],
              },
            ]);
            setDraft([]);
          }
        }}
        onDoubleClick={() => {
          if (mode === 'polygon' && draft.length >= 3) {
            setZones((z) => [...z, { type: 'polygon', name: `zone_${z.length + 1}`, points: draft }]);
            setDraft([]);
          }
        }}
      >
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}>
          {zones.map((z, i) => (
            <polygon
              key={i}
              points={z.points.map(([x, y]) => `${x * 100},${y * 100}`).join(' ')}
              fill="rgba(59,130,246,0.15)"
              stroke="#3b82f6"
              strokeWidth="2"
            />
          ))}
          {draft.length ? (
            <polyline
              points={draft.map(([x, y]) => `${x * 100},${y * 100}`).join(' ')}
              fill="none"
              stroke="#f59e0b"
              strokeWidth="2"
            />
          ) : null}
        </svg>
      </div>
      <p className="hint">
        {bgUrl ? t('configure.editors.zoneHintLive') : t('configure.editors.zoneHintPlaceholder')}
        {t('configure.editors.zoneHintDraw')}
        {t('configure.editors.zoneHintDetection')}
      </p>
    </div>
  );
}
