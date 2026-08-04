import { Button } from '../../../components/ui';

export function GenericSectionForm({
  section,
  data,
  readOnly,
  onSave,
}: {
  section: string;
  data: unknown;
  readOnly: boolean;
  onSave: (data: unknown) => Promise<void>;
}) {
  const text = JSON.stringify(data ?? {}, null, 2);
  const id = `section-${section}`;
  return (
    <div>
      <p className="hint">Секция «{section}»</p>
      <textarea rows={16} defaultValue={text} key={text} readOnly={readOnly} id={id} />
      {!readOnly ? (
        <Button
          variant="primary"
          onClick={() => {
            const el = document.getElementById(id) as HTMLTextAreaElement;
            void onSave(JSON.parse(el.value || '{}'));
          }}
        >
          Сохранить
        </Button>
      ) : null}
    </div>
  );
}
