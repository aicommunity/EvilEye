import type { StreamMetadata } from '../../api';

/** Combine config-static layers with time-varying event/object layers. */
export function mergePlaybackMetadata(
  staticMeta: StreamMetadata | null,
  dynamicMeta: StreamMetadata | null,
): StreamMetadata | null {
  if (!staticMeta && !dynamicMeta) return null;
  const base = staticMeta ?? {};
  const live = dynamicMeta ?? {};
  return {
    source_id: live.source_id ?? base.source_id,
    ts: live.ts ?? base.ts,
    // Static config layers always win — dynamic payload must not clobber them on scrub.
    zones: base.zones?.length ? base.zones : live.zones ?? [],
    debug_rois: base.debug_rois?.length ? base.debug_rois : live.debug_rois ?? [],
    objects: live.objects ?? [],
    signalization: live.signalization ?? false,
    event_labels: live.event_labels ?? [],
    event_color: live.event_color ?? base.event_color,
    overlay: {
      ...base.overlay,
      ...live.overlay,
      source_name: live.overlay?.source_name ?? base.overlay?.source_name,
      time_label: live.overlay?.time_label ?? base.overlay?.time_label,
    },
  };
}
