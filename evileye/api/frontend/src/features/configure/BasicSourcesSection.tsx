import type { BasicSource } from '../../api/setup';
import { Button } from '../../components/ui';
import { useI18n } from '../../i18n';
import { FormField, FormGrid } from './formLayout';

const SOURCE_TYPES = ['IpCamera', 'VideoFile', 'Device'] as const;

export function BasicSourcesSection({
  sources,
  canEdit,
  cameraTitle,
  onUpdateSource,
  onAdd,
  onRemove,
  onAdvanced,
}: {
  sources: BasicSource[];
  canEdit: boolean;
  cameraTitle: (src: BasicSource, index: number) => string;
  onUpdateSource: (index: number, patch: Partial<BasicSource>) => void;
  onAdd: () => void;
  onRemove: (index: number) => void;
  onAdvanced: (index: number) => void;
}) {
  const { t } = useI18n();

  return (
    <>
      <p className="hint">{t('setup.sourcesHint')}</p>
      <div className="basic-sources-list">
        {sources.map((src, i) => (
          <div key={`${src.id}-${i}`} className="basic-source-card">
            <div className="basic-source-card__title">{cameraTitle(src, i)}</div>
            <FormGrid>
              <FormField label={t('setup.sourceName')}>
                <input
                  disabled={!canEdit}
                  value={src.name}
                  onChange={(e) => onUpdateSource(i, { name: e.target.value })}
                />
              </FormField>
              <FormField label={t('setup.sourceType')}>
                <select
                  disabled={!canEdit}
                  value={src.type}
                  onChange={(e) => onUpdateSource(i, { type: e.target.value })}
                >
                  {SOURCE_TYPES.map((tp) => (
                    <option key={tp} value={tp}>
                      {tp}
                    </option>
                  ))}
                </select>
              </FormField>
              <FormField label={t('setup.sourceAddress')}>
                <input
                  disabled={!canEdit}
                  value={String(src.address ?? '')}
                  onChange={(e) => onUpdateSource(i, { address: e.target.value })}
                />
              </FormField>
              <FormField label={t('setup.sourceUser')}>
                <input
                  disabled={!canEdit}
                  value={src.username ?? ''}
                  onChange={(e) => onUpdateSource(i, { username: e.target.value })}
                />
              </FormField>
              <FormField label={t('setup.sourcePassword')}>
                <input
                  type="password"
                  disabled={!canEdit}
                  placeholder={src.password_set ? '••••••••' : ''}
                  value={src.password ?? ''}
                  onChange={(e) => onUpdateSource(i, { password: e.target.value })}
                  autoComplete="new-password"
                />
              </FormField>
              <FormField label={t('setup.sourceRecord')}>
                <input
                  type="checkbox"
                  disabled={!canEdit}
                  checked={Boolean(src.record)}
                  onChange={(e) => onUpdateSource(i, { record: e.target.checked })}
                />
              </FormField>
            </FormGrid>
            {canEdit ? (
              <div className="basic-source-card__actions">
                <Button size="sm" variant="outline" onClick={() => void onAdvanced(i)}>
                  {t('setup.sourceAdvanced')}
                </Button>
                <Button size="sm" variant="danger" onClick={() => onRemove(i)}>
                  {t('setup.removeSource')}
                </Button>
              </div>
            ) : null}
          </div>
        ))}
      </div>
      {canEdit ? (
        <div className="basic-add-source-bar">
          <Button size="sm" variant="success" onClick={onAdd}>
            {t('setup.addSource')}
          </Button>
        </div>
      ) : null}
    </>
  );
}
