import { ObjectSectionForm } from './ObjectSectionForm';

const FIELDS = [
  { key: 'fps', label: 'fps', kind: 'number' as const },
  { key: 'gui_enabled', label: 'gui_enabled', kind: 'bool' as const },
  { key: 'show_main_gui', label: 'show_main_gui', kind: 'bool' as const },
  { key: 'show_journal', label: 'show_journal', kind: 'bool' as const },
  { key: 'autoclose', label: 'autoclose', kind: 'bool' as const },
  { key: 'enable_close_from_gui', label: 'enable_close_from_gui', kind: 'bool' as const },
  { key: 'use_database', label: 'use_database', kind: 'bool' as const },
  { key: 'auto_restart', label: 'auto_restart', kind: 'bool' as const },
  { key: 'show_memory_usage', label: 'show_memory_usage', kind: 'bool' as const },
  { key: 'memory_periodic_check_sec', label: 'memory check (sec)', kind: 'number' as const },
  { key: 'max_memory_usage_mb', label: 'max memory MB', kind: 'number' as const },
  { key: 'obj_handler_empty_heartbeat_every', label: 'empty heartbeat', kind: 'number' as const },
  { key: 'class_mapping', label: 'class_mapping path', kind: 'text' as const },
  { key: 'scheduled_restart', label: 'scheduled_restart (JSON)', kind: 'json' as const },
];

export function ControllerForm(props: {
  data: unknown;
  readOnly: boolean;
  onSave: (data: unknown) => Promise<void>;
  onChange?: (data: unknown) => void;
}) {
  return <ObjectSectionForm title="Controller" fields={FIELDS} {...props} />;
}
