import { useEffect, useState } from 'react';
import { Button } from '../../components/ui';
import { useToast } from '../../components/ui/Toast';
import { useI18n } from '../../i18n';

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
  const { t } = useI18n();
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
            void onSave(text).catch((e) => showError(e instanceof Error ? e.message : t('common.error')))
          }
        >
          {t('configure.saveJson')}
        </Button>
      ) : null}
    </div>
  );
}
