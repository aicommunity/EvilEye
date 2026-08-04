import { Button } from '../../../components/ui';

export function SourcesForm({
  data,
  readOnly,
  onSave,
}: {
  data: unknown;
  readOnly: boolean;
  onSave: (data: unknown) => Promise<void>;
}) {
  const text = JSON.stringify(data ?? [], null, 2);
  return (
    <div>
      <p className="hint">Список источников (JSON array / object по схеме конфига).</p>
      <textarea
        rows={16}
        defaultValue={text}
        key={text}
        readOnly={readOnly}
        id="sources-form-json"
      />
      {!readOnly ? (
        <Button
          variant="primary"
          onClick={() => {
            const el = document.getElementById('sources-form-json') as HTMLTextAreaElement;
            void onSave(JSON.parse(el.value || '[]'));
          }}
        >
          Сохранить sources
        </Button>
      ) : null}
    </div>
  );
}
