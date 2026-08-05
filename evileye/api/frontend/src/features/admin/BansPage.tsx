import { useCallback, useEffect, useState } from 'react';
import { bansApi, type BanRecord } from '../../api';
import { Button } from '../../components/ui';
import { useToast } from '../../components/ui/Toast';
import { useI18n } from '../../i18n';

const DURATION_PRESETS: Array<{ key: string; sec: number | null }> = [
  { key: '30m', sec: 1800 },
  { key: '1h', sec: 3600 },
  { key: '24h', sec: 86400 },
  { key: 'permanent', sec: null },
];

function formatTs(value?: number | null): string {
  if (value == null) return '—';
  try {
    return new Date(value * 1000).toLocaleString();
  } catch {
    return String(value);
  }
}

export function BansPage() {
  const { showError, showSuccess } = useToast();
  const { t } = useI18n();
  const [items, setItems] = useState<BanRecord[]>([]);
  const [ip, setIp] = useState('');
  const [notes, setNotes] = useState('');
  const [durationKey, setDurationKey] = useState('1h');
  const [busy, setBusy] = useState(false);
  const [whitelist, setWhitelist] = useState<string[]>([]);

  const load = useCallback(async () => {
    try {
      const data = await bansApi.list(false);
      setItems(data.items ?? []);
      try {
        const prot = await bansApi.protection();
        const wl = prot.protection?.whitelist_ips;
        setWhitelist(Array.isArray(wl) ? wl.map(String) : []);
      } catch {
        setWhitelist([]);
      }
    } catch (e) {
      showError(e instanceof Error ? e.message : t('common.error'));
    }
  }, [showError, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const onCreate = async () => {
    const trimmed = ip.trim();
    if (!trimmed) return;
    const preset = DURATION_PRESETS.find((p) => p.key === durationKey);
    if (whitelist.includes(trimmed) || whitelist.some((w) => trimmed === w || trimmed.startsWith(w + '/'))) {
      const okWl = window.confirm(t('bans.confirmWhitelist'));
      if (!okWl) return;
    }
    if (preset?.sec == null) {
      const ok = window.confirm(t('bans.confirmPermanent'));
      if (!ok) return;
    }
    setBusy(true);
    try {
      await bansApi.create({
        ip: trimmed,
        reason: 'manual',
        notes: notes.trim(),
        duration_sec: preset?.sec ?? undefined,
      });
      showSuccess(t('bans.created'));
      setIp('');
      setNotes('');
      await load();
    } catch (e) {
      showError(e instanceof Error ? e.message : t('common.error'));
    } finally {
      setBusy(false);
    }
  };

  const onUnban = async (banIp: string) => {
    setBusy(true);
    try {
      await bansApi.remove(banIp);
      showSuccess(t('bans.removed'));
      await load();
    } catch (e) {
      showError(e instanceof Error ? e.message : t('common.error'));
    } finally {
      setBusy(false);
    }
  };

  const onPrune = async () => {
    setBusy(true);
    try {
      const res = await bansApi.prune();
      showSuccess(t('bans.pruned').replace('{n}', String(res.removed ?? 0)));
      await load();
    } catch (e) {
      showError(e instanceof Error ? e.message : t('common.error'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page bans-page">
      <header className="page-header">
        <div>
          <h2>{t('bans.title')}</h2>
          <p className="hint">{t('bans.hint')}</p>
        </div>
        <div className="page-actions">
          <Button variant="outline" onClick={() => void load()} disabled={busy}>
            {t('common.refresh')}
          </Button>
          <Button variant="outline" onClick={() => void onPrune()} disabled={busy}>
            {t('bans.prune')}
          </Button>
        </div>
      </header>

      <section className="users-create bans-create">
        <h3>{t('bans.add')}</h3>
        <div className="users-create-grid">
          <label className="users-create-field">
            <span>{t('bans.ip')}</span>
            <input value={ip} onChange={(e) => setIp(e.target.value)} placeholder="203.0.113.10 or 203.0.113.0/24" />
          </label>
          <label className="users-create-field">
            <span>{t('bans.durationLabel')}</span>
            <select value={durationKey} onChange={(e) => setDurationKey(e.target.value)}>
              {DURATION_PRESETS.map((p) => (
                <option key={p.key} value={p.key}>
                  {t(`bans.duration.${p.key}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="users-create-field">
            <span>{t('bans.notes')}</span>
            <input value={notes} onChange={(e) => setNotes(e.target.value)} />
          </label>
        </div>
        <Button onClick={() => void onCreate()} disabled={busy || !ip.trim()}>
          {t('bans.ban')}
        </Button>
      </section>

      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>{t('bans.ip')}</th>
              <th>{t('bans.reason')}</th>
              <th>{t('bans.source')}</th>
              <th>{t('bans.createdAt')}</th>
              <th>{t('bans.expires')}</th>
              <th>{t('bans.by')}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr>
                <td colSpan={7}>{t('bans.empty')}</td>
              </tr>
            ) : (
              items.map((ban) => (
                <tr key={`${ban.ip}-${ban.id || ban.created_at}`}>
                  <td>{ban.ip}</td>
                  <td>{ban.reason || '—'}</td>
                  <td>{ban.source || '—'}</td>
                  <td>{formatTs(ban.created_at)}</td>
                  <td>{ban.expires_at == null ? t('bans.duration.permanent') : formatTs(ban.expires_at)}</td>
                  <td>{ban.created_by || '—'}</td>
                  <td>
                    <Button size="sm" variant="outline" disabled={busy} onClick={() => void onUnban(ban.ip)}>
                      {t('bans.unban')}
                    </Button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
