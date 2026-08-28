import { useCallback, useEffect, useRef, useState } from 'react';
import { configGet, editorsApi, stateApi, streamSnapshotUrl } from '../../api';
import { Button } from '../../components/ui';
import { useToast } from '../../components/ui/Toast';
import { useI18n } from '../../i18n';
import { listCamerasFromConfig, type ConfigCameraOption } from './cameraList';

const ROI_STROKE = 1.5;

function clamp01(v: number): number {
  return Math.max(0, Math.min(1, v));
}

function roiLabel(index: number): string {
  return `roi_${index + 1}`;
}

function normalizeRoi(r: number[]): number[] {
  const [x1, y1, x2, y2] = r;
  return [Math.min(x1, x2), Math.min(y1, y2), Math.max(x1, x2), Math.max(y1, y2)];
}

function roiCorners(r: number[]): [number, number][] {
  const [x1, y1, x2, y2] = normalizeRoi(r);
  return [
    [x1, y1],
    [x2, y1],
    [x2, y2],
    [x1, y2],
  ];
}

function updateRoiCorner(r: number[], cornerIndex: number, point: [number, number]): number[] {
  const [px, py] = point;
  const [x1, y1, x2, y2] = normalizeRoi(r);
  switch (cornerIndex) {
    case 0:
      return normalizeRoi([px, py, x2, y2]);
    case 1:
      return normalizeRoi([x1, py, px, y2]);
    case 2:
      return normalizeRoi([x1, y1, px, py]);
    case 3:
      return normalizeRoi([px, y1, x2, py]);
    default:
      return r;
  }
}

export function RoiCanvas({
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
  const [rois, setRois] = useState<number[][]>([]);
  const [drawing, setDrawing] = useState<number[] | null>(null);
  const [bgUrl, setBgUrl] = useState<string | null>(null);
  const [cameraOptions, setCameraOptions] = useState<ConfigCameraOption[]>([]);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [dragCorner, setDragCorner] = useState<{ roiIndex: number; cornerIndex: number } | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);

  const loadRois = useCallback(() => {
    void editorsApi
      .getRoi(configName, sourceId)
      .then((r) => {
        setRois((r.rois ?? []).map(normalizeRoi));
        setSelectedIndex(null);
        setDrawing(null);
      })
      .catch((e) => showError(e.message));
  }, [configName, sourceId, showError]);

  useEffect(() => {
    loadRois();
  }, [loadRois]);

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
      setDrawing(null);
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
      setRois((prev) => prev.filter((_, i) => i !== selectedIndex));
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
    setRois((prev) => prev.filter((_, i) => i !== selectedIndex));
    setSelectedIndex(null);
  };

  const clearAll = () => {
    setRois([]);
    setSelectedIndex(null);
    setDrawing(null);
  };

  const saveRois = () => {
    void editorsApi
      .putRoi(configName, sourceId, rois)
      .then((r) => {
        if (r.restart_required) showSuccess(t('common.savedRestart'));
        else showSuccess(t('common.savedApplied'));
        onSaved?.(Boolean(r.restart_required));
      })
      .catch((e) => showError(e.message));
  };

  const handleCameraChange = (nextId: number) => {
    setDrawing(null);
    setSelectedIndex(null);
    onSourceIdChange(nextId);
  };

  const updateCorner = (roiIndex: number, cornerIndex: number, point: [number, number]) => {
    setRois((prev) =>
      prev.map((r, i) => (i === roiIndex ? updateRoiCorner(r, cornerIndex, point) : r)),
    );
  };

  const displayRois = [...rois, ...(drawing ? [drawing] : [])];

  return (
    <div>
      <div className="toolbar" style={{ flexWrap: 'wrap', gap: 8 }}>
        <label>
          {t('configure.editors.roiCameraSelect')}{' '}
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
        {!readOnly ? (
          <>
            <Button size="sm" variant="outline" disabled={selectedIndex == null} onClick={deleteSelected}>
              {t('configure.editors.deleteRoi')}
            </Button>
            <Button size="sm" variant="outline" onClick={clearAll}>
              {t('configure.editors.clearRois')}
            </Button>
            <Button variant="primary" onClick={() => void saveRois()}>
              {t('configure.editors.saveRoi')}
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
            cursor: dragCorner ? 'grabbing' : undefined,
          }}
          onClick={(e) => {
            if (readOnly || dragCorner || drawing) return;
            if (e.target !== e.currentTarget && !(e.target as Element).closest('[data-roi-surface]')) return;
            setSelectedIndex(null);
          }}
          onMouseDown={(e) => {
            if (readOnly || dragCorner) return;
            if ((e.target as Element).closest('[data-roi-surface], circle')) return;
            const [x, y] = toNorm(e.clientX, e.clientY);
            setDrawing([x, y, x, y]);
            setSelectedIndex(null);
          }}
          onMouseMove={(e) => {
            if (dragCorner) {
              const p = toNorm(e.clientX, e.clientY);
              updateCorner(dragCorner.roiIndex, dragCorner.cornerIndex, p);
              return;
            }
            if (!drawing) return;
            const [x, y] = toNorm(e.clientX, e.clientY);
            setDrawing([drawing[0], drawing[1], x, y]);
          }}
          onMouseUp={() => {
            if (dragCorner) {
              setDragCorner(null);
              return;
            }
            if (!drawing) return;
            const normalized = normalizeRoi(drawing);
            const [x1, y1, x2, y2] = normalized;
            if (Math.abs(x2 - x1) > 0.005 && Math.abs(y2 - y1) > 0.005) {
              setRois((prev) => [...prev, normalized]);
            }
            setDrawing(null);
          }}
          onMouseLeave={() => {
            if (dragCorner) setDragCorner(null);
            if (drawing) setDrawing(null);
          }}
        >
          <svg
            viewBox="0 0 100 100"
            preserveAspectRatio="none"
            style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }}
          >
            {displayRois.map((r, i) => {
              const isDraft = i >= rois.length;
              const roiIndex = isDraft ? -1 : i;
              const selected = !isDraft && roiIndex === selectedIndex;
              const [x1, y1, x2, y2] = normalizeRoi(r);
              return (
                <rect
                  key={isDraft ? 'draft' : i}
                  data-roi-surface="1"
                  x={x1 * 100}
                  y={y1 * 100}
                  width={(x2 - x1) * 100}
                  height={(y2 - y1) * 100}
                  fill={selected ? 'rgba(245,158,11,0.25)' : 'rgba(34,197,94,0.15)'}
                  stroke={selected ? '#f59e0b' : isDraft ? '#86efac' : '#22c55e'}
                  strokeWidth={ROI_STROKE}
                  vectorEffect="non-scaling-stroke"
                  style={{ pointerEvents: isDraft ? 'none' : 'auto', cursor: readOnly ? 'default' : 'pointer' }}
                  onClick={(e) => {
                    e.stopPropagation();
                    if (!readOnly && roiIndex >= 0) setSelectedIndex(roiIndex);
                  }}
                />
              );
            })}
            {!readOnly && selectedIndex != null && rois[selectedIndex]
              ? roiCorners(rois[selectedIndex]).map((pt, ci) => (
                  <circle
                    key={`${selectedIndex}-${ci}`}
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
                      setDragCorner({ roiIndex: selectedIndex, cornerIndex: ci });
                    }}
                  />
                ))
              : null}
          </svg>
        </div>

        <div style={{ minWidth: 160, flex: '0 1 200px' }}>
          <h4 style={{ margin: '0 0 8px' }}>{t('configure.editors.roiListTitle')}</h4>
          {rois.length === 0 ? (
            <p className="hint">{t('configure.editors.roiListEmpty')}</p>
          ) : (
            <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
              {rois.map((r, i) => {
                const [x1, y1, x2, y2] = normalizeRoi(r);
                return (
                  <li key={i}>
                    <button
                      type="button"
                      className={i === selectedIndex ? 'journal-tab active' : 'journal-tab'}
                      style={{ width: '100%', textAlign: 'left', marginBottom: 4 }}
                      onClick={() => setSelectedIndex(i)}
                    >
                      {roiLabel(i)} ({x1.toFixed(2)}, {y1.toFixed(2)} – {x2.toFixed(2)}, {y2.toFixed(2)})
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>

      <p className="hint">
        {bgUrl ? t('configure.editors.bgLive') : t('configure.editors.bgPlaceholder')}
        {!readOnly ? ` ${t('configure.editors.roiHintDraw')}` : ''}
      </p>
    </div>
  );
}
