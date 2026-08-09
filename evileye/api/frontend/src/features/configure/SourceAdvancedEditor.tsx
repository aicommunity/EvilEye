import { useCallback, useEffect, useMemo, useState } from 'react';
import { stateApi, streamSnapshotUrl } from '../../api';
import { Button, Modal } from '../../components/ui';
import { useToast } from '../../components/ui/Toast';
import { useI18n } from '../../i18n';
import { FormField, FormGrid } from './formLayout';
import { SourceSplitCanvas } from './SourceSplitCanvas';
import {
  applyRegionsToRow,
  canvasSizeFromCoords,
  cloneSourceRow,
  displaySourceName,
  padRegions,
  parseSourceRegions,
  validateSplitRegions,
  type PixelRect,
} from './sourceRowUtils';

const CAPTURE_TYPES = ['VideoCaptureGStreamer', 'VideoCaptureOpencv'] as const;
const SOURCE_KINDS = ['IpCamera', 'VideoFile', 'Device'] as const;
const API_PREFS = ['CAP_GSTREAMER', 'CAP_FFMPEG'] as const;

async function loadImage(url: string): Promise<HTMLImageElement | null> {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => resolve(null);
    img.src = url;
  });
}

/** Compose logical (cropped) snapshots onto a full-frame canvas using src_coords. */
async function composeFullFramePreview(
  runId: number,
  ids: number[],
  coords: PixelRect[],
  frameW: number,
  frameH: number,
): Promise<{ dataUrl: string; w: number; h: number } | null> {
  if (!ids.length || !coords.length) return null;
  const w = Math.max(1, Math.floor(frameW));
  const h = Math.max(1, Math.floor(frameH));
  const canvas = document.createElement('canvas');
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;
  ctx.fillStyle = '#111';
  ctx.fillRect(0, 0, w, h);

  let drew = 0;
  for (let i = 0; i < ids.length; i++) {
    const rect = coords[i];
    if (!rect) continue;
    const base = streamSnapshotUrl(runId, ids[i]);
    const url = `${base}${base.includes('?') ? '&' : '?'}t=${Date.now()}_${i}`;
    const img = await loadImage(url);
    if (!img) continue;
    const [x, y, rw, rh] = rect;
    ctx.drawImage(img, x, y, Math.max(1, rw), Math.max(1, rh));
    drew += 1;
  }
  if (!drew) return null;
  return { dataUrl: canvas.toDataURL('image/jpeg', 0.85), w, h };
}

export function SourceAdvancedEditor({
  open,
  configName,
  sourceIndex,
  initialRow,
  readOnly,
  onClose,
  onApplied,
}: {
  open: boolean;
  configName: string;
  sourceIndex: number;
  initialRow: Record<string, unknown>;
  readOnly: boolean;
  onClose: () => void;
  onApplied: (row: Record<string, unknown>) => void | Promise<void>;
}) {
  const { t } = useI18n();
  const { showError } = useToast();
  const [draft, setDraft] = useState(() => cloneSourceRow(initialRow));
  const [baseline, setBaseline] = useState(() => JSON.stringify(initialRow));
  const [selected, setSelected] = useState<number | null>(0);
  const [canvasBgUrl, setCanvasBgUrl] = useState<string | null>(null);
  const [applying, setApplying] = useState(false);
  const [naturalSize, setNaturalSize] = useState<{ w: number; h: number } | null>(null);
  const [previewRunId, setPreviewRunId] = useState<number | null>(null);

  useEffect(() => {
    if (!open) return;
    const cloned = cloneSourceRow(initialRow);
    setDraft(cloned);
    setBaseline(JSON.stringify(cloned));
    setSelected(0);
    setNaturalSize(null);
    setCanvasBgUrl(null);
    setPreviewRunId(null);
  }, [open, initialRow, sourceIndex]);

  const regions = useMemo(() => parseSourceRegions(draft), [draft]);
  const dirty = useMemo(() => JSON.stringify(draft) !== baseline, [draft, baseline]);

  const frameSize = useMemo(() => {
    if (regions.split && regions.coords.length) {
      const fromCoords = canvasSizeFromCoords(regions.coords);
      if (naturalSize) {
        return {
          w: Math.max(fromCoords.w, naturalSize.w),
          h: Math.max(fromCoords.h, naturalSize.h),
        };
      }
      return fromCoords;
    }
    return naturalSize ?? { w: 1920, h: 1080 };
  }, [naturalSize, regions.coords, regions.split]);

  const refreshPreview = useCallback(async () => {
    try {
      const res = await stateApi.cameras('current');
      const cams = res.items ?? [];
      const idSet = new Set(regions.ids);
      const matches = cams.filter(
        (c) => c.source_id != null && idSet.has(Number(c.source_id)) && c.run_state === 'running',
      );
      const anyMatch =
        matches[0] ??
        cams.find((c) => c.source_id != null && idSet.has(Number(c.source_id))) ??
        null;
      if (!anyMatch || anyMatch.run_id == null) {
        setCanvasBgUrl(null);
        setPreviewRunId(null);
        return;
      }
      const runId = Number(anyMatch.run_id);
      setPreviewRunId(runId);

      if (regions.split && regions.coords.length >= 1) {
        const composed = await composeFullFramePreview(
          runId,
          regions.ids,
          regions.coords,
          frameSize.w,
          frameSize.h,
        );
        if (composed) {
          setCanvasBgUrl(composed.dataUrl);
          setNaturalSize({ w: composed.w, h: composed.h });
          return;
        }
      }

      // Non-split (or compose failed): show single logical/full stream as canvas background.
      const sid = Number(anyMatch.source_id);
      const base = streamSnapshotUrl(runId, sid);
      const url = `${base}${base.includes('?') ? '&' : '?'}t=${Date.now()}`;
      const img = await loadImage(url);
      if (img && img.naturalWidth > 0) {
        setNaturalSize({ w: img.naturalWidth, h: img.naturalHeight });
        setCanvasBgUrl(url);
      } else {
        setCanvasBgUrl(null);
      }
    } catch {
      setCanvasBgUrl(null);
      setPreviewRunId(null);
    }
  }, [frameSize.h, frameSize.w, regions.coords, regions.ids, regions.split]);

  useEffect(() => {
    if (!open) return;
    void refreshPreview();
    const id = window.setInterval(() => void refreshPreview(), 2500);
    return () => window.clearInterval(id);
  }, [open, refreshPreview]);

  const patchDraft = (patch: Record<string, unknown>) => setDraft((prev) => ({ ...prev, ...patch }));

  const setRegions = (next: { split: boolean; ids: number[]; names: string[]; coords: PixelRect[] }) => {
    setDraft((prev) => applyRegionsToRow(prev, next));
  };

  const requestClose = () => {
    if (dirty && !readOnly && !window.confirm(t('setup.discardConfirm'))) return;
    onClose();
  };

  const handleApply = async () => {
    if (readOnly) return;
    const parsed = parseSourceRegions(draft);
    const err = validateSplitRegions(parsed);
    if (err) {
      showError(t('setup.splitValidation'));
      return;
    }
    const row = applyRegionsToRow(draft, parsed);
    setApplying(true);
    try {
      await onApplied(row);
    } catch (e) {
      showError(e instanceof Error ? e.message : t('common.saveFail'));
    } finally {
      setApplying(false);
    }
  };

  const addRegion = () => {
    const n = Math.max(2, regions.ids.length + 1);
    const padded = padRegions(n, regions.ids, regions.names, regions.coords, frameSize.w, frameSize.h);
    setRegions({ split: true, ...padded });
    setSelected(padded.ids.length - 1);
  };

  const removeSelectedRegion = () => {
    if (selected == null || selected < 0 || selected >= regions.ids.length) return;
    if (regions.ids.length <= 2) {
      // Turning off split when fewer than 2 remain
      setRegions({
        split: false,
        ids: [regions.ids[selected === 0 ? 1 : 0] ?? regions.ids[0] ?? 0],
        names: [regions.names[selected === 0 ? 1 : 0] ?? regions.names[0] ?? 'Cam1'],
        coords: [],
      });
      setSelected(null);
      return;
    }
    const ids = regions.ids.filter((_, i) => i !== selected);
    const names = regions.names.filter((_, i) => i !== selected);
    const coords = regions.coords.filter((_, i) => i !== selected);
    setRegions({ split: true, ids, names, coords });
    setSelected(Math.min(selected, ids.length - 1));
  };

  const titleName = displaySourceName(draft);

  return (
    <Modal
      open={open}
      title={t('setup.sourceAdvancedTitle', { name: titleName })}
      onClose={requestClose}
      wide
      footer={
        <>
          <Button variant="outline" onClick={requestClose}>
            {t('setup.cancel')}
          </Button>
          {!readOnly ? (
            <Button variant="primary" disabled={applying} onClick={() => void handleApply()}>
              {t('setup.apply')}
            </Button>
          ) : null}
        </>
      }
    >
      <div className="source-advanced-toolbar">
        <Button size="sm" variant="outline" className="source-advanced-back" onClick={requestClose}>
          {t('setup.backToSources')}
        </Button>
        <span className="hint" style={{ margin: 0 }}>
          {configName} · #{sourceIndex}
          {previewRunId != null ? ` · run #${previewRunId}` : ''}
        </span>
      </div>

      <div className="source-advanced-layout">
        <div className="source-advanced-preview-col">
          {!canvasBgUrl ? <p className="hint">{t('setup.noPreviewRun')}</p> : null}
          {regions.split ? <p className="hint">{t('setup.splitPreviewHint')}</p> : null}
          <SourceSplitCanvas
            width={frameSize.w}
            height={frameSize.h}
            coords={regions.split ? regions.coords : []}
            selected={selected}
            readOnly={readOnly || !regions.split}
            bgUrl={canvasBgUrl}
            onSelect={setSelected}
            onChangeRect={(index, rect) => {
              if (!regions.split) return;
              const coords = regions.coords.map((r) => [...r] as PixelRect);
              if (index < 0 || index >= coords.length) return;
              coords[index] = rect;
              setRegions({ split: true, ids: regions.ids, names: regions.names, coords });
            }}
          />
        </div>

        <div className="source-advanced-fields">
          <FormGrid>
            <FormField label={t('setup.captureType')}>
              <select
                disabled={readOnly}
                value={String(draft.type ?? 'VideoCaptureGStreamer')}
                onChange={(e) => patchDraft({ type: e.target.value })}
              >
                {CAPTURE_TYPES.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
            </FormField>
            <FormField label={t('setup.sourceType')}>
              <select
                disabled={readOnly}
                value={String(draft.source ?? 'IpCamera')}
                onChange={(e) => patchDraft({ source: e.target.value })}
              >
                {SOURCE_KINDS.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
            </FormField>
            <FormField label={t('setup.sourceAddress')}>
              <input
                disabled={readOnly}
                value={String(draft.camera ?? draft.uri ?? '')}
                onChange={(e) => patchDraft({ camera: e.target.value, uri: e.target.value })}
              />
            </FormField>
            <FormField label={t('setup.apiPreference')}>
              <select
                disabled={readOnly}
                value={String(draft.apiPreference ?? 'CAP_GSTREAMER')}
                onChange={(e) => patchDraft({ apiPreference: e.target.value })}
              >
                {API_PREFS.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
            </FormField>
            <FormField label={t('setup.desiredFps')}>
              <input
                type="number"
                disabled={readOnly}
                value={
                  draft.desired_fps != null
                    ? Number(draft.desired_fps)
                    : draft.fps != null
                      ? Number(draft.fps)
                      : ''
                }
                onChange={(e) => {
                  const n = e.target.value === '' ? null : Number(e.target.value);
                  patchDraft({ desired_fps: n, fps: n });
                }}
              />
            </FormField>
            <FormField label={t('setup.executionMode')}>
              <input
                disabled={readOnly}
                value={String(draft.execution_mode ?? '')}
                onChange={(e) => patchDraft({ execution_mode: e.target.value })}
                placeholder="process / thread"
              />
            </FormField>
            <FormField label={t('setup.loopPlay')}>
              <input
                type="checkbox"
                disabled={readOnly}
                checked={Boolean(draft.loop_play)}
                onChange={(e) => patchDraft({ loop_play: e.target.checked })}
              />
            </FormField>
            <FormField label={t('setup.splitEnable')}>
              <input
                type="checkbox"
                disabled={readOnly}
                checked={regions.split}
                onChange={(e) => {
                  if (e.target.checked) {
                    const padded = padRegions(2, regions.ids, regions.names, regions.coords, frameSize.w, frameSize.h);
                    setRegions({ split: true, ...padded });
                    setSelected(0);
                  } else {
                    setRegions({
                      split: false,
                      ids: [regions.ids[0] ?? 0],
                      names: [regions.names[0] ?? `Cam${(regions.ids[0] ?? 0) + 1}`],
                      coords: [],
                    });
                    setSelected(null);
                  }
                }}
              />
            </FormField>
          </FormGrid>

          {regions.split ? (
            <>
              <div className="source-split-actions">
                {!readOnly ? (
                  <>
                    <Button size="sm" variant="success" onClick={addRegion}>
                      {t('setup.addSplitRegion')}
                    </Button>
                    <Button
                      size="sm"
                      variant="danger"
                      disabled={selected == null}
                      onClick={removeSelectedRegion}
                    >
                      {t('setup.removeSplitRegion')}
                    </Button>
                  </>
                ) : null}
              </div>
              <h4 className="source-advanced-subtitle">{t('setup.splitRegions')}</h4>
              <table className="source-split-table journal-table">
                <thead>
                  <tr>
                    <th>id</th>
                    <th>name</th>
                    <th>x</th>
                    <th>y</th>
                    <th>w</th>
                    <th>h</th>
                  </tr>
                </thead>
                <tbody>
                  {regions.ids.map((id, i) => {
                    const c = regions.coords[i] ?? [0, 0, 1, 1];
                    return (
                      <tr
                        key={`${id}-${i}`}
                        className={selected === i ? 'run-row-highlight' : undefined}
                        onClick={() => setSelected(i)}
                      >
                        <td>
                          <input
                            type="number"
                            disabled={readOnly}
                            value={id}
                            onChange={(e) => {
                              const ids = [...regions.ids];
                              ids[i] = Number(e.target.value);
                              setRegions({ split: true, ids, names: regions.names, coords: regions.coords });
                            }}
                          />
                        </td>
                        <td>
                          <input
                            disabled={readOnly}
                            value={regions.names[i] ?? ''}
                            onChange={(e) => {
                              const names = [...regions.names];
                              names[i] = e.target.value;
                              setRegions({ split: true, ids: regions.ids, names, coords: regions.coords });
                            }}
                          />
                        </td>
                        {([0, 1, 2, 3] as const).map((ci) => (
                          <td key={ci}>
                            <input
                              type="number"
                              disabled={readOnly}
                              value={c[ci]}
                              onChange={(e) => {
                                const coords = regions.coords.map((r) => [...r] as PixelRect);
                                while (coords.length <= i) coords.push([0, 0, 100, 100]);
                                coords[i][ci] = Number(e.target.value);
                                setRegions({ split: true, ids: regions.ids, names: regions.names, coords });
                              }}
                            />
                          </td>
                        ))}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </>
          ) : null}
        </div>
      </div>
    </Modal>
  );
}
