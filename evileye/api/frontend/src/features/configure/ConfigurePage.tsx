import { useEffect, useState } from 'react';
import { Navigate, useParams } from 'react-router-dom';
import { setupApi, stateApi, type StateRun } from '../../api';
import { useToast } from '../../components/ui/Toast';
import { ConfigStudio } from './ConfigStudio';
import { configBasename } from './studioTabs';
import { useI18n } from '../../i18n';

export function ConfigurePage() {
  const { name: routeName } = useParams();
  const { showError } = useToast();
  const { t } = useI18n();
  const [configName, setConfigName] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (routeName) return;
    void (async () => {
      try {
        const data = (await stateApi.runs('current')) as { current_run?: StateRun | null };
        const path = data.current_run?.config_path;
        const fromRun = configBasename(path);
        if (fromRun) {
          setConfigName(fromRun);
          return;
        }
        const status = await setupApi.status();
        setConfigName(status.default_config || 'system.json');
      } catch (e) {
        try {
          const status = await setupApi.status();
          setConfigName(status.default_config || 'system.json');
        } catch {
          showError(e instanceof Error ? e.message : t('configure.noActiveRun'));
          setConfigName('system.json');
        }
      } finally {
        setLoaded(true);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- t is stable; language switch must not re-resolve
  }, [routeName, showError]);

  if (routeName) {
    return <Navigate to={`/admin/configs/${encodeURIComponent(routeName)}`} replace />;
  }

  if (!loaded) {
    return (
      <section className="panel active">
        <div className="card">
          <p className="hint">{t('configure.loading')}</p>
        </div>
      </section>
    );
  }

  // Prefer file mode so Basic setup works without an active run.
  return <ConfigStudio mode="file" configName={configName} currentBadge={false} />;
}
