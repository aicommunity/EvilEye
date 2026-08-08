import { ObjectSectionForm } from './ObjectSectionForm';

const FIELDS = [
  { key: 'enabled', label: 'enabled', kind: 'bool' as const },
  { key: 'check_interval_sec', label: 'check interval (sec)', kind: 'number' as const },
  { key: 'retention_days', label: 'retention days', kind: 'number' as const },
  { key: 'max_size_gb', label: 'max size GB', kind: 'number' as const },
  { key: 'min_free_space_pct', label: 'min free space %', kind: 'number' as const },
  { key: 'path', label: 'path', kind: 'text' as const },
];

export function StorageMonitorForm(props: {
  data: unknown;
  readOnly: boolean;
  onSave: (data: unknown) => Promise<void>;
  onChange?: (data: unknown) => void;
}) {
  return <ObjectSectionForm title="Storage monitor" fields={FIELDS} {...props} />;
}
