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
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [applying, setApplying] = useState(false);
  const [naturalSize, setNaturalSize] = useState<{ w: number; h: number } | null>(null);

  useEffect(() => {
    if (!open) return;
    const cloned = cloneSourceRow(initialRow);
    setDraft(cloned);
    setBaseline(JSON.stringify(cloned));
    setSelected(0);
    setNaturalSize(null);
  }, [open, initialRow, sourceIndex]);

  const regions = useMemo(() => parseSourceRegions(draft), [draft]);
  const dirty = useMemo(() => JSON.stringify(draft) !== baseline, [draft, baseline]);

  const frameSize = useMemo(() => {
    if (naturalSize && !regions.split) return naturalSize;
    const fromCoords = canvasSizeFromCoords(regions.coords);
    if (regions.coords.length) return fromCoords;
    return naturalSize ?? { w: 1920, h: 1080 };
  }, [naturalSize, regions.coords, regions.split]);

  const primaryId = regions.ids[0] ?? 0;

  const refreshPreview = useCallback(async () => {
    try {
      const res = await stateApi.cameras('current');
      const cams = res.items ?? [];
      const idSet = new Set(regions.ids);
      const match =
        cams.find((c) => c.source_id != null && idSet.has(Number(c.source_id)) && c.run_state === 'running') ??
        cams.find((c) => c.source_id === primaryId && c.run_state === 'running');
      if (match?.run_id != null && match.source_id != null) {
        const base = streamSnapshotUrl(match.run_id, match.source_id);
        setPreviewUrl(`${base}${base.includes('?') ? '&' : '?'}t=${Date.now()}`);
      } else {
        setPreviewUrl(null);
      }
    } catch {
      setPreviewUrl(null);
    }
  }, [primaryId, regions.ids]);

  useEffect(() => {
    if (!open) return;
    void refreshPreview();
    const id = window.setInterval(() => void refreshPreview(), 2000);
    return () => window.clearInterval(id);
  }, [open, refreshPreview]);

  useEffect(() => {
    if (!previewUrl || regions.split) return;
    const img = new Image();
    img.onload = () => {
      if (img.naturalWidth > 0 && img.naturalHeight > 0) {
        setNaturalSize({ w: img.naturalWidth, h: img.naturalHeight });
      }
    };
    img.src = previewUrl;
  }, [previewUrl, regions.split]);

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
        </span>
      </div>

      <div className="source-advanced-layout">
        <div className="source-advanced-preview-col">
          {previewUrl ? (
            <img
              src={previewUrl}
              alt=""
              className="source-advanced-preview-thumb"
              onLoad={(e) => {
                const img = e.currentTarget;
                if (!regions.split && img.naturalWidth > 0) {
                  setNaturalSize({ w: img.naturalWidth, h: img.naturalHeight });
                }
              }}
            />
          ) : (
            <p className="hint">{t('setup.noPreviewRun')}</p>
          )}
          {regions.split ? <p className="hint">{t('setup.splitPreviewHint')}</p> : null}
          <SourceSplitCanvas
            width={frameSize.w}
            height={frameSize.h}
            coords={regions.split ? regions.coords : []}
            selected={selected}
            readOnly={readOnly || !regions.split}
            bgUrl={regions.split ? null : previewUrl}
            onSelect={setSelected}
            onReplaceRect={(index, rect) => {
              if (!regions.split) return;
              const coords = [...regions.coords];
              if (index == null) {
                coords.push(rect);
                const padded = padRegions(
                  coords.length,
                  regions.ids,
                  regions.names,
                  coords,
                  frameSize.w,
                  frameSize.h,
                );
                setRegions({ split: true, ...padded });
                setSelected(padded.coords.length - 1);
              } else {
                coords[index] = rect;
                setRegions({ split: true, ids: regions.ids, names: regions.names, coords });
              }
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
              <FormField label="num_split">
                <input
                  type="number"
                  min={2}
                  disabled={readOnly}
                  value={regions.ids.length}
                  onChange={(e) => {
                    const n = Math.max(2, Number(e.target.value) || 2);
                    const padded = padRegions(n, regions.ids, regions.names, regions.coords, frameSize.w, frameSize.h);
                    setRegions({ split: true, ...padded });
                  }}
                />
              </FormField>
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
