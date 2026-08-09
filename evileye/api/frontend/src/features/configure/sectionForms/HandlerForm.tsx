import { useEffect, useState } from 'react';
import { Button } from '../../../components/ui';
import { useI18n } from '../../../i18n';
import { formatInt, INT_STEP, parseIntInput } from '../numberFormat';

type HandlerCfg = {
  enabled?: boolean;
  save_images?: boolean;
  save_videos?: boolean;
  retention_days?: number;
  [key: string]: unknown;
};

function asObj(data: unknown): HandlerCfg {
  if (Array.isArray(data)) return (data[0] as HandlerCfg) ?? {};
  if (data && typeof data === 'object') return data as HandlerCfg;
  return {};
}

export function HandlerForm({
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
  const [obj, setObj] = useState<HandlerCfg>(() => asObj(data));
  useEffect(() => setObj(asObj(data)), [data]);
  const update = (next: HandlerCfg) => {
    setObj(next);
    onChange?.(next);
  };

  return (
    <div>
      <p className="hint">{t('configure.forms.hintHandler')}</p>
      <div className="toolbar" style={{ flexWrap: 'wrap', gap: 12 }}>
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
          <input
            type="checkbox"
            disabled={readOnly}
            checked={Boolean(obj.save_images)}
            onChange={(e) => update({ ...obj, save_images: e.target.checked })}
          />{' '}
          save_images
        </label>
        <label>
          <input
            type="checkbox"
            disabled={readOnly}
            checked={Boolean(obj.save_videos)}
            onChange={(e) => update({ ...obj, save_videos: e.target.checked })}
          />{' '}
          save_videos
        </label>
        <label>
          retention_days{' '}
          <input
            type="number"
            step={INT_STEP}
            disabled={readOnly}
            value={obj.retention_days != null ? formatInt(Number(obj.retention_days)) : ''}
            onChange={(e) => update({ ...obj, retention_days: parseIntInput(e.target.value) })}
            className="config-input-num"
          />
        </label>
      </div>
      {!readOnly ? (
        <Button variant="primary" onClick={() => void onSave(Array.isArray(data) ? [obj] : obj)}>
          {t('configure.forms.saveSection', { section: 'handler' })}
        </Button>
      ) : null}
    </div>
  );
}
