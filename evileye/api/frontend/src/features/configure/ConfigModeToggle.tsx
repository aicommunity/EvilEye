import { useEffect, useState } from 'react';
import { useI18n } from '../../i18n';
import type { SetupStatus } from '../../api';

const STORAGE_KEY = 'evileye.config.mode';

export type ConfigUiMode = 'basic' | 'advanced';

export function readStoredConfigMode(): ConfigUiMode {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v === 'advanced' || v === 'basic') return v;
  } catch {
    /* ignore */
  }
  return 'basic';
}

export function writeStoredConfigMode(mode: ConfigUiMode) {
  try {
    localStorage.setItem(STORAGE_KEY, mode);
  } catch {
    /* ignore */
  }
}

export function ConfigModeToggle({
  mode,
  onChange,
  needsSetup,
}: {
  mode: ConfigUiMode;
  onChange: (mode: ConfigUiMode) => void;
  needsSetup: boolean;
}) {
  const { t } = useI18n();
  return (
    <div className="config-mode-toggle" role="group" aria-label={t('setup.modeLabel')}>
      <button
        type="button"
        className={`btn btn-sm ${mode === 'basic' ? 'btn-primary' : 'btn-outline'}`}
        onClick={() => onChange('basic')}
      >
        {t('setup.modeBasic')}
      </button>
      <button
        type="button"
        className={`btn btn-sm ${mode === 'advanced' ? 'btn-primary' : 'btn-outline'}`}
        disabled={needsSetup}
        title={needsSetup ? t('setup.advancedLocked') : undefined}
        onClick={() => {
          if (needsSetup) return;
          onChange('advanced');
        }}
      >
        {t('setup.modeAdvanced')}
      </button>
    </div>
  );
}

export function useConfigUiMode(status: SetupStatus | null) {
  const needsSetup = Boolean(status?.needs_setup);
  const [mode, setMode] = useState<ConfigUiMode>(() => (needsSetup ? 'basic' : readStoredConfigMode()));

  useEffect(() => {
    if (needsSetup) {
      setMode('basic');
      return;
    }
    setMode(readStoredConfigMode());
  }, [needsSetup]);

  const change = (next: ConfigUiMode) => {
    if (needsSetup && next === 'advanced') return;
    writeStoredConfigMode(next);
    setMode(next);
  };

  return { mode, setMode: change, needsSetup };
}
