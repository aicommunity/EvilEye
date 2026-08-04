import { useEffect, useState } from 'react';
import { Button } from '../../../components/ui';

type DbCfg = {
  enabled?: boolean;
  host?: string;
  port?: number;
  database?: string;
  user?: string;
  password?: string;
  [key: string]: unknown;
};

function asObj(data: unknown): DbCfg {
  return data && typeof data === 'object' && !Array.isArray(data) ? (data as DbCfg) : {};
}

export function DatabaseForm({
  data,
  readOnly,
  onSave,
}: {
  data: unknown;
  readOnly: boolean;
  onSave: (data: unknown) => Promise<void>;
}) {
  const [obj, setObj] = useState<DbCfg>(() => asObj(data));
  useEffect(() => setObj(asObj(data)), [data]);

  return (
    <div>
      <p className="hint">PostgreSQL connection parameters.</p>
      <div className="toolbar" style={{ flexWrap: 'wrap', gap: 8, marginBottom: 8 }}>
        <label>
          <input
            type="checkbox"
            disabled={readOnly}
            checked={Boolean(obj.enabled)}
            onChange={(e) => setObj({ ...obj, enabled: e.target.checked })}
          />{' '}
          enabled
        </label>
        <label>
          host{' '}
          <input disabled={readOnly} value={String(obj.host ?? '')} onChange={(e) => setObj({ ...obj, host: e.target.value })} />
        </label>
        <label>
          port{' '}
          <input
            type="number"
            disabled={readOnly}
            value={obj.port ?? ''}
            onChange={(e) => setObj({ ...obj, port: e.target.value === '' ? undefined : Number(e.target.value) })}
            style={{ width: 80 }}
          />
        </label>
        <label>
          database{' '}
          <input
            disabled={readOnly}
            value={String(obj.database ?? '')}
            onChange={(e) => setObj({ ...obj, database: e.target.value })}
          />
        </label>
        <label>
          user{' '}
          <input disabled={readOnly} value={String(obj.user ?? '')} onChange={(e) => setObj({ ...obj, user: e.target.value })} />
        </label>
        <label>
          password{' '}
          <input
            type="password"
            disabled={readOnly}
            value={String(obj.password ?? '')}
            onChange={(e) => setObj({ ...obj, password: e.target.value })}
          />
        </label>
      </div>
      {!readOnly ? (
        <Button variant="primary" onClick={() => void onSave(obj)}>
          Сохранить database
        </Button>
      ) : null}
    </div>
  );
}
