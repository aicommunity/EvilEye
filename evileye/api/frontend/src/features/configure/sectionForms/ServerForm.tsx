import { ObjectSectionForm } from './ObjectSectionForm';

const FIELDS = [
  { key: 'enabled', label: 'enabled', kind: 'bool' as const },
  { key: 'host', label: 'host', kind: 'text' as const },
  { key: 'port', label: 'port', kind: 'number' as const },
  { key: 'execution_mode', label: 'execution_mode', kind: 'text' as const },
  { key: 'log_level', label: 'log_level', kind: 'text' as const },
  { key: 'preview_encoder', label: 'preview_encoder', kind: 'text' as const },
  { key: 'preview_encode_workers', label: 'encode workers', kind: 'number' as const },
];

export function ServerForm(props: {
  data: unknown;
  readOnly: boolean;
  onSave: (data: unknown) => Promise<void>;
  onChange?: (data: unknown) => void;
}) {
  return <ObjectSectionForm title="Server" fields={FIELDS} {...props} />;
}
