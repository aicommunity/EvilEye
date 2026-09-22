import type { BasicAlarmCamera, BasicSetup, BasicSource, AlarmSchedule } from '../../api/setup';

export type PipelineCameraRef = {
  source_id: number;
  source_name: string;
};

/** Logical cameras for alarm schedule (split outputs), merged with saved alarm_cameras state. */
export function deriveAlarmCameras(
  sources: BasicSource[],
  alarmSchedule?: AlarmSchedule | null,
  existing?: BasicAlarmCamera[] | null,
  pipelineCameras?: PipelineCameraRef[] | null,
): BasicAlarmCamera[] {
  const byId = new Map((existing ?? []).map((c) => [c.id, c]));
  const entries: PipelineCameraRef[] = [];

  if (pipelineCameras?.length) {
    entries.push(...pipelineCameras);
  } else {
    for (const src of sources) {
      const ids = src.logical_ids?.length ? src.logical_ids : [src.id];
      const names = [src.name || `Cam${ids[0] + 1}`, ...(src.extra_names ?? [])];
      for (let i = 0; i < ids.length; i++) {
        entries.push({
          source_id: ids[i],
          source_name: names[i] ?? `Cam${ids[i] + 1}`,
        });
      }
    }
  }

  return entries.map(({ source_id, source_name }) => {
    const prev = byId.get(source_id);
    return (
      prev ?? {
        id: source_id,
        name: source_name,
        alarm_enabled: alarmSchedule?.enabled ?? false,
      }
    );
  });
}

export function withDerivedAlarmCameras(
  basic: BasicSetup,
  pipelineCameras?: PipelineCameraRef[] | null,
): BasicSetup {
  const alarm_cameras = deriveAlarmCameras(
    basic.sources,
    basic.alarm_schedule,
    basic.alarm_cameras,
    pipelineCameras,
  );
  return { ...basic, alarm_cameras };
}
