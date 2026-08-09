import { useEffect, useState } from 'react';
import { Button } from '../../../components/ui';
import { useI18n } from '../../../i18n';

type VisCfg = {
  enabled?: boolean;
  fps?: number;
  display_fps?: number;
  show_boxes?: boolean;
  show_zones?: boolean;
  event_signal_enabled?: boolean;
  [key: string]: unknown;
};

function asObj(data: unknown): VisCfg {
  return data && typeof data === 'object' && !Array.isArray(data) ? (data as VisCfg) : {};
}

export function VisualizerForm({
  data,
  readOnly,
  onSave,
  onChange,
}: {
  data: unknown;
  readOnly: boolean;
  onSave: (data: unknown) => Promise<void>;
  onChange?: (data: unknown) => void;
}) {
  const { t } = useI18n();
  const [obj, setObj] = useState<VisCfg>(() => asObj(data));
  useEffect(() => setObj(asObj(data)), [data]);
  const update = (next: VisCfg) => {
    setObj(next);
    onChange?.(next);
  };
  const fps = obj.fps ?? obj.display_fps;

  return (
    <div>
      <p className="hint">{t('configure.forms.hintVisualizer')}</p>
      <div className="toolbar" style={{ flexWrap: 'wrap', gap: 12, marginBottom: 8 }}>
        <label>
          <input
            type="checkbox"
            disabled={readOnly}
            checked={Boolean(obj.enabled ?? true)}
            onChange={(e) => update({ ...obj, enabled: e.target.checked })}
          />{' '}
          enabled
        </label>
        <label>
          fps{' '}
          <input
            type="number"
            disabled={readOnly}
            value={fps ?? ''}
            onChange={(e) => update({ ...obj, fps: e.target.value === '' ? undefined : Number(e.target.value) })}
            className="config-input-num"
          />
        </label>
        <label>
          <input
            type="checkbox"
            disabled={readOnly}
            checked={Boolean(obj.show_boxes ?? true)}
            onChange={(e) => update({ ...obj, show_boxes: e.target.checked })}
          />{' '}
          show_boxes
        </label>
        <label>
          <input
            type="checkbox"
            disabled={readOnly}
            checked={Boolean(obj.show_zones ?? true)}
            onChange={(e) => update({ ...obj, show_zones: e.target.checked })}
          />{' '}
          show_zones
        </label>
        <label>
          <input
            type="checkbox"
            disabled={readOnly}
            checked={Boolean(obj.event_signal_enabled)}
            onChange={(e) => update({ ...obj, event_signal_enabled: e.target.checked })}
          />{' '}
          event_signal
        </label>
      </div>
      {!readOnly ? (
        <Button variant="primary" onClick={() => void onSave(obj)}>
          {t('configure.forms.saveSection', { section: 'visualizer' })}
        </Button>
      ) : null}
    </div>
  );
}
