import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  configsList,
  configGet,
  configUpdate,
  configListSections,
  configGetSection,
  configPutSection,
  configValidate,
  ApiError,
} from '../../api';
import { Button } from '../../components/ui';
import { useToast } from '../../components/ui/Toast';
import { useAuth } from '../../auth/AuthContext';
import { SourcesForm } from './sectionForms/SourcesForm';
import { DetectorsForm } from './sectionForms/DetectorsForm';
import { TrackersForm } from './sectionForms/TrackersForm';
import { EventsForm } from './sectionForms/EventsForm';
import { HandlerForm } from './sectionForms/HandlerForm';
import { DatabaseForm } from './sectionForms/DatabaseForm';
import { VisualizerForm } from './sectionForms/VisualizerForm';
import { GenericSectionForm } from './sectionForms/GenericSectionForm';
import { JsonAdvancedTab } from './JsonAdvancedTab';
import { ConfigHistoryPanel } from './ConfigHistoryPanel';
import { RoiCanvas } from './RoiCanvas';
import { ZoneCanvas } from './ZoneCanvas';
import { ClassMappingEditor } from './ClassMappingEditor';

const SECTION_LABELS: Record<string, string> = {
  sources: 'Sources',
  detectors: 'Detectors',
  trackers: 'Trackers',
  events_detectors: 'Events',
  objects_handler: 'Handler',
  database: 'Database',
  visualizer: 'Visualizer',
};

export function ConfigurePage() {
  const { name: routeName } = useParams();
  const { hasPermission } = useAuth();
  const { showError, showSuccess } = useToast();
  const [names, setNames] = useState<string[]>([]);
  const [name, setName] = useState(routeName ?? '');
  const [sections, setSections] = useState<string[]>([]);
  const [active, setActive] = useState('sources');
  const [sectionData, setSectionData] = useState<unknown>(null);
  const [fullJson, setFullJson] = useState('{}');
  const [sourceId, setSourceId] = useState(0);
  const [dirty, setDirty] = useState(false);
  const canEdit = hasPermission('config:edit');

  // Note: react-router useBlocker requires a data router; we use BrowserRouter,
  // so rely on beforeunload + explicit confirms for dirty navigation.
  useEffect(() => {
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (!dirty) return;
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  }, [dirty]);

  useEffect(() => {
    void configsList()
      .then((list) => {
        setNames(list);
        if (!name && list[0]) setName(list[0]);
      })
      .catch((e) => showError(e.message));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!name) return;
    void (async () => {
      try {
        const secs = await configListSections(name);
        setSections(secs.sections);
        if (secs.sections.length && !secs.sections.includes(active)) setActive(secs.sections[0]);
        const body = await configGet(name);
        setFullJson(JSON.stringify(body, null, 2));
        setDirty(false);
      } catch (e) {
        showError(e instanceof Error ? e.message : 'Ошибка');
      }
    })();
  }, [name]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!name || !active || active === 'json' || active === 'history' || active === 'roi' || active === 'zones' || active === 'classes') return;
    void configGetSection(name, active)
      .then((data) => {
        setSectionData(data);
        setDirty(false);
      })
      .catch((e) => showError(e instanceof ApiError ? e.message : 'Ошибка секции'));
  }, [name, active, showError]);

  const saveSection = async (data: unknown) => {
    if (!canEdit) return;
    try {
      await configPutSection(name, active, data);
      showSuccess('Секция сохранена');
      setSectionData(data);
      setDirty(false);
    } catch (e) {
      showError(e instanceof Error ? e.message : 'Ошибка сохранения');
    }
  };

  const switchTab = (s: string) => {
    if (dirty && !window.confirm('Есть несохранённые изменения. Сменить вкладку?')) return;
    setActive(s);
    setDirty(false);
  };

  const renderSectionForm = () => {
    const common = {
      data: sectionData,
      readOnly: !canEdit,
      onSave: async (data: unknown) => {
        await saveSection(data);
      },
    };
    if (active === 'sources') return <SourcesForm {...common} />;
    if (active === 'detectors') return <DetectorsForm {...common} />;
    if (active === 'trackers') return <TrackersForm {...common} />;
    if (active === 'events_detectors' || active === 'events') return <EventsForm {...common} />;
    if (active === 'objects_handler') return <HandlerForm {...common} />;
    if (active === 'database') return <DatabaseForm {...common} />;
    if (active === 'visualizer') return <VisualizerForm {...common} />;
    return <GenericSectionForm section={active} {...common} />;
  };

  return (
    <section className="panel active">
      <div className="card">
        <h2>Config Studio {dirty ? <span className="hint">· несохранённые изменения</span> : null}</h2>
        <p className="hint">Формы секций, ROI/Zone canvas, class mapping. JSON — advanced.</p>
        <div className="toolbar">
          <select
            value={name}
            onChange={(e) => {
              if (dirty && !window.confirm('Есть несохранённые изменения. Сменить конфиг?')) return;
              setName(e.target.value);
              setDirty(false);
            }}
          >
            {names.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
          <Button
            variant="outline"
            onClick={() =>
              void configValidate(name)
                .then((r) => {
                  if (r.ok) showSuccess('Конфиг валиден');
                  else showError(r.errors.join('; ') || 'Ошибки валидации');
                })
                .catch((e) => showError(e.message))
            }
          >
            Validate
          </Button>
        </div>
        <div className="journal-tabs">
          {[...sections, 'roi', 'zones', 'classes', 'json', 'history'].map((s) => (
            <button key={s} type="button" className={`journal-tab${active === s ? ' active' : ''}`} onClick={() => switchTab(s)}>
              {SECTION_LABELS[s] ?? s}
            </button>
          ))}
        </div>
        {active === 'json' ? (
          <JsonAdvancedTab
            value={fullJson}
            readOnly={!canEdit}
            onSave={async (text) => {
              await configUpdate(name, JSON.parse(text));
              setFullJson(text);
              setDirty(false);
              showSuccess('JSON сохранён');
            }}
            onChange={() => setDirty(true)}
          />
        ) : active === 'history' ? (
          <ConfigHistoryPanel configName={name} />
        ) : active === 'roi' ? (
          <RoiCanvas configName={name} sourceId={sourceId} onSourceIdChange={setSourceId} readOnly={!canEdit} />
        ) : active === 'zones' ? (
          <ZoneCanvas configName={name} sourceId={sourceId} onSourceIdChange={setSourceId} readOnly={!canEdit} />
        ) : active === 'classes' ? (
          <ClassMappingEditor configName={name} readOnly={!canEdit} />
        ) : (
          <div onInput={() => setDirty(true)} onChange={() => setDirty(true)}>
            {renderSectionForm()}
          </div>
        )}
      </div>
    </section>
  );
}
