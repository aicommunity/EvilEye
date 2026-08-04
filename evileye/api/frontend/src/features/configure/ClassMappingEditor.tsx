import { useEffect, useState } from 'react';
import { editorsApi } from '../../api';
import { Button } from '../../components/ui';
import { useToast } from '../../components/ui/Toast';

export function ClassMappingEditor({ configName, readOnly }: { configName: string; readOnly: boolean }) {
  const { showError, showSuccess } = useToast();
  const [text, setText] = useState('{}');

  useEffect(() => {
    void editorsApi
      .getClassMapping(configName)
      .then((r) => setText(JSON.stringify(r.mapping ?? {}, null, 2)))
      .catch((e) => showError(e.message));
  }, [configName, showError]);

  return (
    <div>
      <p className="hint">Словарь class_id → имя</p>
      <textarea rows={12} value={text} readOnly={readOnly} onChange={(e) => setText(e.target.value)} />
      {!readOnly ? (
        <Button
          variant="primary"
          onClick={() =>
            void editorsApi
              .putClassMapping(configName, JSON.parse(text || '{}'))
              .then((r) => showSuccess(r.restart_required ? 'Сохранено (нужен restart)' : 'Сохранено'))
              .catch((e) => showError(e.message))
          }
        >
          Сохранить mapping
        </Button>
      ) : null}
    </div>
  );
}
