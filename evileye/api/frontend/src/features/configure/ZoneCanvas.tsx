import { useCallback, useEffect, useRef, useState } from 'react';
import { configGet, editorsApi, stateApi, streamSnapshotUrl, type ZoneItem } from '../../api';
import { Button } from '../../components/ui';
import { useToast } from '../../components/ui/Toast';
import { useI18n } from '../../i18n';
import { listCamerasFromConfig, type ConfigCameraOption } from './cameraList';
import { ZoneDetectorParams } from './ZoneDetectorParams';

const ZONE_STROKE = 1.5;

function clamp01(v: number): number {
  return Math.max(0, Math.min(1, v));
}

function zoneLabel(zone: ZoneItem, index: number): string {
  return zone.name?.trim() || `zone_${index + 1}`;
}

function zoneBBox(points: [number, number][]): [number, number, number, number] {
  const xs = points.map((p) => p[0]);
  const ys = points.map((p) => p[1]);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}

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
  const [cameraOptions, setCameraOptions] = useState<ConfigCameraOption[]>([]);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [dragVertex, setDragVertex] = useState<{ zoneIndex: number; pointIndex: number } | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);

  const loadZones = useCallback(() => {
    void editorsApi
      .getZones(configName, sourceId)
      .then((r) => {
        setZones(r.zones ?? []);
        setSelectedIndex(null);
        setDraft([]);
      })
      .catch((e) => showError(e.message));
  }, [configName, sourceId, showError]);

  useEffect(() => {
    loadZones();
  }, [loadZones]);

  useEffect(() => {
    let cancelled = false;
    void configGet(configName)
      .then((cfg) => {
        if (cancelled) return;
        const fromConfig = listCamerasFromConfig(cfg);
        if (fromConfig.length) {
          setCameraOptions(fromConfig);
          return;
        }
        return stateApi.cameras('current').then((res) => {
          if (cancelled) return;
          const fallback = (res.items ?? [])
            .filter((c) => c.source_id != null)
            .map((c) => ({
              source_id: c.source_id as number,
              source_name: c.source_name || `Source ${c.source_id}`,
            }));
          setCameraOptions(fallback);
        });
      })
      .catch(() => {
        if (!cancelled) setCameraOptions([]);
      });
    return () => {
      cancelled = true;
    };
  }, [configName]);

  useEffect(() => {
    if (!cameraOptions.length) return;
    if (!cameraOptions.some((c) => c.source_id === sourceId)) {
      setDraft([]);
      setSelectedIndex(null);
      onSourceIdChange(cameraOptions[0].source_id);
    }
  }, [cameraOptions, onSourceIdChange, sourceId]);

  useEffect(() => {
    let cancelled = false;
    void stateApi
      .cameras('current')
      .then((res) => {
        if (cancelled) return;
        const cams = res.items ?? [];
        const match = cams.find((c) => c.source_id === sourceId && c.run_state === 'running');
        if (match) {
          const base = streamSnapshotUrl(match.run_id, sourceId);
          setBgUrl(`${base}${base.includes('?') ? '&' : '?'}t=${Date.now()}`);
        } else {
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

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (readOnly || selectedIndex == null) return;
      if (e.key !== 'Delete' && e.key !== 'Backspace') return;
      const target = e.target as HTMLElement | null;
      if (target?.closest('input, textarea, select')) return;
      e.preventDefault();
      setZones((prev) => prev.filter((_, i) => i !== selectedIndex));
      setSelectedIndex(null);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [readOnly, selectedIndex]);

  const selectedCamera = cameraOptions.find((c) => c.source_id === sourceId);

  const toNorm = (clientX: number, clientY: number): [number, number] => {
    const rect = wrapRef.current!.getBoundingClientRect();
    return [
      clamp01((clientX - rect.left) / rect.width),
      clamp01((clientY - rect.top) / rect.height),
    ];
  };

  const deleteSelected = () => {
    if (selectedIndex == null) return;
    setZones((prev) => prev.filter((_, i) => i !== selectedIndex));
    setSelectedIndex(null);
  };

  const clearAll = () => {
    setZones([]);
    setSelectedIndex(null);
    setDraft([]);
  };

  const updateVertex = (zoneIndex: number, pointIndex: number, point: [number, number]) => {
    setZones((prev) =>
      prev.map((z, zi) => {
        if (zi !== zoneIndex) return z;
        const points = z.points.map((p, pi) => (pi === pointIndex ? point : p)) as [number, number][];
        return { ...z, points };
      }),
    );
  };

  const saveZones = () => {
    void editorsApi
      .putZones(configName, sourceId, zones)
      .then((r) => {
        if (r.restart_required) showSuccess(t('common.savedRestart'));
        else showSuccess(t('common.savedApplied'));
        onSaved?.(Boolean(r.restart_required));
      })
      .catch((e) => showError(e.message));
  };

  const handleCameraChange = (nextId: number) => {
    setDraft([]);
    setSelectedIndex(null);
    onSourceIdChange(nextId);
  };

  return (
    <div>
      <div className="toolbar" style={{ flexWrap: 'wrap', gap: 8 }}>
        <label>
          {t('configure.editors.zoneCameraSelect')}{' '}
          {cameraOptions.length ? (
            <select
              value={sourceId}
              disabled={readOnly}
              onChange={(e) => handleCameraChange(Number(e.target.value))}
            >
              {cameraOptions.map((c) => (
                <option key={c.source_id} value={c.source_id}>
                  {c.source_name} (id={c.source_id})
                </option>
              ))}
            </select>
          ) : (
            <span className="hint">{t('configure.editors.zoneCameraUnknown', { id: sourceId })}</span>
          )}
        </label>
        {selectedCamera ? (
          <span className="hint">
            {t('configure.editors.zoneCameraLabel', { name: selectedCamera.source_name, id: sourceId })}
          </span>
        ) : null}
        <Button size="sm" variant={mode === 'rect' ? 'primary' : 'outline'} onClick={() => setMode('rect')}>
          {t('configure.editors.rect')}
        </Button>
        <Button size="sm" variant={mode === 'polygon' ? 'primary' : 'outline'} onClick={() => setMode('polygon')}>
          {t('configure.editors.polygon')}
        </Button>
        {!readOnly ? (
          <>
            <Button size="sm" variant="outline" disabled={selectedIndex == null} onClick={deleteSelected}>
              {t('configure.editors.deleteZone')}
            </Button>
            <Button size="sm" variant="outline" onClick={clearAll}>
              {t('configure.editors.clearZones')}
            </Button>
            {draft.length ? (
              <Button size="sm" variant="outline" onClick={() => setDraft([])}>
                {t('configure.editors.cancelDraft')}
              </Button>
            ) : null}
            <Button variant="primary" onClick={() => void saveZones()}>
              {t('configure.editors.saveZones')}
            </Button>
          </>
        ) : null}
      </div>

      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'flex-start' }}>
        <div
          ref={wrapRef}
          style={{
            position: 'relative',
            width: '100%',
            maxWidth: 640,
            flex: '1 1 320px',
            aspectRatio: '16/9',
            background: '#111',
            border: '1px solid var(--border)',
            backgroundImage: bgUrl ? `url(${bgUrl})` : undefined,
            backgroundSize: 'contain',
            backgroundRepeat: 'no-repeat',
            backgroundPosition: 'center',
            cursor: dragVertex ? 'grabbing' : undefined,
          }}
          onClick={(e) => {
            if (readOnly || dragVertex) return;
            if (e.target !== e.currentTarget && !(e.target as Element).closest('[data-zone-surface]')) return;
            setSelectedIndex(null);
            const p = toNorm(e.clientX, e.clientY);
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
            if (readOnly || mode !== 'polygon' || draft.length < 3) return;
            setZones((z) => [...z, { type: 'polygon', name: `zone_${z.length + 1}`, points: draft }]);
            setDraft([]);
          }}
          onMouseMove={(e) => {
            if (!dragVertex) return;
            const p = toNorm(e.clientX, e.clientY);
            updateVertex(dragVertex.zoneIndex, dragVertex.pointIndex, p);
          }}
          onMouseUp={() => setDragVertex(null)}
          onMouseLeave={() => setDragVertex(null)}
        >
          <svg
            viewBox="0 0 100 100"
            preserveAspectRatio="none"
            style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }}
          >
            {zones.map((z, i) => {
              const selected = i === selectedIndex;
              return (
                <polygon
                  key={i}
                  data-zone-surface="1"
                  points={z.points.map(([x, y]) => `${x * 100},${y * 100}`).join(' ')}
                  fill={selected ? 'rgba(245,158,11,0.25)' : 'rgba(59,130,246,0.15)'}
                  stroke={selected ? '#f59e0b' : '#3b82f6'}
                  strokeWidth={ZONE_STROKE}
                  vectorEffect="non-scaling-stroke"
                  style={{ pointerEvents: 'auto', cursor: readOnly ? 'default' : 'pointer' }}
                  onClick={(e) => {
                    e.stopPropagation();
                    if (!readOnly) setSelectedIndex(i);
                  }}
                />
              );
            })}
            {draft.length ? (
              <polyline
                points={draft.map(([x, y]) => `${x * 100},${y * 100}`).join(' ')}
                fill="none"
                stroke="#f59e0b"
                strokeWidth={ZONE_STROKE}
                vectorEffect="non-scaling-stroke"
              />
            ) : null}
            {!readOnly && selectedIndex != null && zones[selectedIndex]
              ? zones[selectedIndex].points.map((pt, pi) => (
                  <circle
                    key={`${selectedIndex}-${pi}`}
                    cx={pt[0] * 100}
                    cy={pt[1] * 100}
                    r={1.2}
                    fill="#f59e0b"
                    stroke="#fff"
                    strokeWidth={0.3}
                    vectorEffect="non-scaling-stroke"
                    style={{ pointerEvents: 'auto', cursor: 'grab' }}
                    onMouseDown={(e) => {
                      e.stopPropagation();
                      setDragVertex({ zoneIndex: selectedIndex, pointIndex: pi });
                    }}
                  />
                ))
              : null}
          </svg>
        </div>

        <div style={{ minWidth: 160, flex: '0 1 200px' }}>
          <h4 style={{ margin: '0 0 8px' }}>{t('configure.editors.zoneListTitle')}</h4>
          {zones.length === 0 ? (
            <p className="hint">{t('configure.editors.zoneListEmpty')}</p>
          ) : (
            <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
              {zones.map((z, i) => (
                <li key={i}>
                  <button
                    type="button"
                    className={i === selectedIndex ? 'journal-tab active' : 'journal-tab'}
                    style={{ width: '100%', textAlign: 'left', marginBottom: 4 }}
                    onClick={() => setSelectedIndex(i)}
                  >
                    {zoneLabel(z, i)} ({z.type}, {z.points.length} pts)
                  </button>
                </li>
              ))}
            </ul>
          )}
          {selectedIndex != null && zones[selectedIndex] ? (
            <div className="hint" style={{ marginTop: 8 }}>
              <div>{t('configure.editors.zoneSelectedInfo', { name: zoneLabel(zones[selectedIndex], selectedIndex) })}</div>
              <div>
                {t('configure.editors.zoneSelectedType', { type: zones[selectedIndex].type })}
              </div>
              <div>
                {t('configure.editors.zoneSelectedPoints', { count: zones[selectedIndex].points.length })}
              </div>
              {(() => {
                const [x1, y1, x2, y2] = zoneBBox(zones[selectedIndex].points);
                return (
                  <div>
                    {t('configure.editors.zoneSelectedBbox', {
                      x1: x1.toFixed(3),
                      y1: y1.toFixed(3),
                      x2: x2.toFixed(3),
                      y2: y2.toFixed(3),
                    })}
                  </div>
                );
              })()}
              <div>{t('configure.editors.zoneNameNotPersisted')}</div>
            </div>
          ) : null}
        </div>
      </div>

      <p className="hint">
        {bgUrl ? t('configure.editors.zoneHintLive') : t('configure.editors.zoneHintPlaceholder')}
        {t('configure.editors.zoneHintDraw')}
        {t('configure.editors.zoneHintEdit')}
        {t('configure.editors.zoneHintDetection')}
      </p>

      <ZoneDetectorParams configName={configName} readOnly={readOnly} onSaved={onSaved} />
    </div>
  );
}
