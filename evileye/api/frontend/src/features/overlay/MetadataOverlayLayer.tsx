import type { StreamMetadata } from '../../api';
import { OverlayCanvas, type OverlayDensity, type OverlayLayoutBox } from './OverlayCanvas';

export function MetadataOverlayLayer({
  meta,
  layoutBox,
  density = 'full',
  visible = true,
}: {
  meta: StreamMetadata | null;
  layoutBox?: OverlayLayoutBox;
  density?: OverlayDensity;
  visible?: boolean;
}) {
  if (!visible || !meta) return null;
  return <OverlayCanvas meta={meta} layoutBox={layoutBox} density={density} />;
}

export type { OverlayLayoutBox, OverlayDensity };
