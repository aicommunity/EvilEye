import { EventsForm } from './EventsForm';

/** Alias for events_detectors studio tab. */
export function EventsDetectorsForm(props: {
  data: unknown;
  readOnly: boolean;
  onSave: (data: unknown) => Promise<void>;
  onChange?: (data: unknown) => void;
}) {
  return <EventsForm {...props} />;
}
