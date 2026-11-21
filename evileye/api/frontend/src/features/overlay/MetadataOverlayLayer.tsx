import type { StreamMetadata } from '../../api';
import { OverlayCanvas, type OverlayDensity, type OverlayLayoutBox, type OverlayRenderMode } from './OverlayCanvas';

export function MetadataOverlayLayer({
  meta,
  layoutBox,
  density = 'full',
  visible = true,
  renderMode = 'live',
}: {
  meta: StreamMetadata | null;
  layoutBox?: OverlayLayoutBox;
  density?: OverlayDensity;
  visible?: boolean;
  renderMode?: OverlayRenderMode;
}) {
  if (!visible || !meta) return null;
  return <OverlayCanvas meta={meta} layoutBox={layoutBox} density={density} renderMode={renderMode} />;
}

export type { OverlayLayoutBox, OverlayDensity };
