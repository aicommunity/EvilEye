export type ConfigCameraOption = {
  source_id: number;
  source_name: string;
};

/** Parse pipeline.sources into logical cameras (matches backend load_config_summary). */
export function listCamerasFromConfig(config: unknown): ConfigCameraOption[] {
  if (!config || typeof config !== 'object') return [];
  const root = config as Record<string, unknown>;
  const pipeline = root.pipeline;
  const pipe = pipeline && typeof pipeline === 'object' ? (pipeline as Record<string, unknown>) : root;
  const sources = pipe.sources;
  if (!Array.isArray(sources)) return [];

  const out: ConfigCameraOption[] = [];
  for (const source of sources) {
    if (!source || typeof source !== 'object') continue;
    const src = source as Record<string, unknown>;
    const sourceIds = src.source_ids;
    const sourceNames = src.source_names;
    if (!Array.isArray(sourceIds) || !Array.isArray(sourceNames)) continue;
    for (let idx = 0; idx < sourceIds.length; idx += 1) {
      const rawId = sourceIds[idx];
      const sid = typeof rawId === 'number' ? rawId : Number(rawId);
      if (!Number.isFinite(sid)) continue;
      const name = String(sourceNames[idx] ?? `Source ${sid}`);
      out.push({ source_id: sid, source_name: name });
    }
  }
  return out;
}
