import { useEffect, useState } from 'react';
import { Button } from '../../components/ui';
import { useToast } from '../../components/ui/Toast';

export function JsonAdvancedTab({
  value,
  readOnly,
  onSave,
  onChange,
}: {
  value: string;
  readOnly: boolean;
  onSave: (text: string) => Promise<void>;
  onChange?: (text: string) => void;
}) {
  const [text, setText] = useState(value);
  const { showError } = useToast();
  useEffect(() => setText(value), [value]);
  return (
    <div className="config-studio-json">
      <textarea
        value={text}
        readOnly={readOnly}
        onChange={(e) => {
          setText(e.target.value);
          onChange?.(e.target.value);
        }}
      />
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
