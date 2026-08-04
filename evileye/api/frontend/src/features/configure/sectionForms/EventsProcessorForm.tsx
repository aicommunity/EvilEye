import { GenericSectionForm } from './GenericSectionForm';

export function EventsProcessorForm(props: {
  data: unknown;
  readOnly: boolean;
  onSave: (data: unknown) => Promise<void>;
  onChange?: (data: unknown) => void;
}) {
  return <GenericSectionForm section="events_processor" {...props} />;
}
