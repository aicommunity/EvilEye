import { Button } from '../../../components/ui';

export function DetectorsForm({
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
      <p className="hint">Детекторы: model, classes, source_ids, roi, conf…</p>
      <textarea rows={16} defaultValue={text} key={text} readOnly={readOnly} id="detectors-form-json" />
      {!readOnly ? (
        <Button
          variant="primary"
          onClick={() => {
            const el = document.getElementById('detectors-form-json') as HTMLTextAreaElement;
            void onSave(JSON.parse(el.value || '[]'));
          }}
        >
          Сохранить detectors
        </Button>
      ) : null}
    </div>
  );
}
