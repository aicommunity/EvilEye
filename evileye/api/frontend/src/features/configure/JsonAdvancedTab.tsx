import { useState } from 'react';
import { Button } from '../../components/ui';
import { useToast } from '../../components/ui/Toast';

export function JsonAdvancedTab({
  value,
  readOnly,
  onSave,
}: {
  value: string;
  readOnly: boolean;
  onSave: (text: string) => Promise<void>;
}) {
  const [text, setText] = useState(value);
  const { showError } = useToast();
  return (
    <div>
      <textarea rows={20} value={text} readOnly={readOnly} onChange={(e) => setText(e.target.value)} />
      {!readOnly ? (
        <Button
          variant="primary"
          onClick={() =>
            void onSave(text).catch((e) => showError(e instanceof Error ? e.message : 'Ошибка'))
          }
        >
          Сохранить JSON
        </Button>
      ) : null}
    </div>
  );
}
