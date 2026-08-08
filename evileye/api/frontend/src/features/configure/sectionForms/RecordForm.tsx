import { ObjectSectionForm } from './ObjectSectionForm';

const FIELDS = [
  { key: 'enabled', label: 'enabled', kind: 'bool' as const },
  { key: 'continuous_recording_enabled', label: 'continuous', kind: 'bool' as const },
  { key: 'event_recording_enabled', label: 'event recording', kind: 'bool' as const },
  { key: 'event_pre_seconds', label: 'pre seconds', kind: 'number' as const },
  { key: 'event_post_seconds', label: 'post seconds', kind: 'number' as const },
  { key: 'event_buffer_fps', label: 'buffer fps', kind: 'number' as const },
  { key: 'container', label: 'container', kind: 'text' as const },
  { key: 'segment_length_sec', label: 'segment length (sec)', kind: 'number' as const },
  { key: 'retention_days', label: 'retention days', kind: 'number' as const },
  { key: 'min_free_space_pct', label: 'min free space %', kind: 'number' as const },
  { key: 'filename_tmpl', label: 'filename template', kind: 'text' as const },
  { key: 'out_dir', label: 'out dir', kind: 'text' as const },
  { key: 'enabled_sources', label: 'enabled_sources (JSON)', kind: 'json' as const },
];

export function RecordForm(props: {
  data: unknown;
  readOnly: boolean;
  onSave: (data: unknown) => Promise<void>;
  onChange?: (data: unknown) => void;
}) {
  return <ObjectSectionForm title="Record" fields={FIELDS} {...props} />;
}
