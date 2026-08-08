import { GenericSectionForm } from './GenericSectionForm';

export function McTrackersForm(props: {
  data: unknown;
  readOnly: boolean;
  onSave: (data: unknown) => Promise<void>;
  onChange?: (data: unknown) => void;
}) {
  return <GenericSectionForm section="mc_trackers" {...props} />;
}
