import { useEffect, useState } from 'react';
import { Navigate, useParams } from 'react-router-dom';
import { stateApi, type StateRun } from '../../api';
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
        setConfigName(configBasename(path));
      } catch (e) {
        showError(e instanceof Error ? e.message : t('configure.noActiveRun'));
        setConfigName(null);
      } finally {
        setLoaded(true);
      }
    })();
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

  return <ConfigStudio mode="current" configName={configName} currentBadge />;
}
