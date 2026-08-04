import { useEffect, useState } from 'react';
import { Button } from '../../../components/ui';

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
}: {
  data: unknown;
  readOnly: boolean;
  onSave: (data: unknown) => Promise<void>;
}) {
  const [obj, setObj] = useState<HandlerCfg>(() => asObj(data));
  useEffect(() => setObj(asObj(data)), [data]);

  return (
    <div>
      <p className="hint">Objects handler: сохранение кадров/видео и retention.</p>
      <div className="toolbar" style={{ flexWrap: 'wrap', gap: 12 }}>
        <label>
          <input
            type="checkbox"
            disabled={readOnly}
            checked={Boolean(obj.enabled ?? true)}
            onChange={(e) => setObj({ ...obj, enabled: e.target.checked })}
          />{' '}
          enabled
        </label>
        <label>
          <input
            type="checkbox"
            disabled={readOnly}
            checked={Boolean(obj.save_images)}
            onChange={(e) => setObj({ ...obj, save_images: e.target.checked })}
          />{' '}
          save_images
        </label>
        <label>
          <input
            type="checkbox"
            disabled={readOnly}
            checked={Boolean(obj.save_videos)}
            onChange={(e) => setObj({ ...obj, save_videos: e.target.checked })}
          />{' '}
          save_videos
        </label>
        <label>
          retention_days{' '}
          <input
            type="number"
            disabled={readOnly}
            value={obj.retention_days ?? ''}
            onChange={(e) =>
              setObj({ ...obj, retention_days: e.target.value === '' ? undefined : Number(e.target.value) })
            }
            style={{ width: 80 }}
          />
        </label>
      </div>
      {!readOnly ? (
        <Button variant="primary" onClick={() => void onSave(Array.isArray(data) ? [obj] : obj)}>
          Сохранить handler
        </Button>
      ) : null}
    </div>
  );
}
