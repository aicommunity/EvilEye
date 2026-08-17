export interface ConfigRun {
  id: number;
  name: string | null;
  config_path: string;
  pid: number | null;
  state: string;
  error: string | null;
  managed?: boolean;
  source?: string;
  alive?: boolean;
  frame_dir?: string | null;
}

export interface StateRun extends ConfigRun {
  started_at?: number | null;
  updated_at?: number | null;
  uptime_seconds?: number | null;
  latest_frame_available?: boolean;
  pipeline_class?: string | null;
  detector_count?: number;
  tracker_count?: number;
  event_detector_names?: string[];
  database_enabled?: boolean;
  storage_mode?: 'json' | 'database';
  config_name?: string | null;
  log_session_id?: string | null;
  log_files?: {
    main?: string | null;
    errors?: string | null;
    performance?: string | null;
  };
  log_match?: 'exact' | 'heuristic' | 'none';
  sources?: Array<{
    source_id: number | null;
    source_name: string;
    source_type?: string | null;
    address?: string | null;
  }>;
  runtime_snapshot?: Record<string, unknown> | null;
}

export interface StateCamera {
  run_id: number;
  run_name: string | null;
  run_state: string;
  pipeline_class?: string | null;
  source_id: number | null;
  source_name: string;
  source_type?: string | null;
  address?: string | null;
  preview_available: boolean;
  is_working?: boolean;
  last_frame_age_sec?: number | null;
  reconnecting?: boolean;
  alive: boolean;
}

export interface JournalGroupedRow {
  time?: string;
  time_lost?: string;
  event?: string;
  information?: string;
  source?: string;
  date_folder?: string;
  preview?: string;
  lost_preview?: string;
  has_found_preview?: boolean;
  has_lost_preview?: boolean;
  has_found_video?: boolean;
  has_lost_video?: boolean;
  has_stream_video?: boolean;
  found_video_path?: string | null;
  lost_video_path?: string | null;
  stream_video_path?: string | null;
  stream_offset_seconds?: number | null;
  bbox_found?: [number, number, number, number] | null;
  bbox_lost?: [number, number, number, number] | null;
  zone_coords?: [number, number][] | null;
  row_key?: string;
  [key: string]: unknown;
}

export interface JournalFiltersMeta {
  dates: string[];
  source_names: string[];
  event_types_events: string[];
  event_types_objects: string[];
}

export interface JournalPage<T> {
  available: boolean;
  items: T[];
  total: number;
  mode?: string;
  reason?: string;
  message?: string;
}

export interface AuthUser {
  username: string;
  role: string;
}

export interface AuthMeResponse {
  authenticated: boolean;
  auth_enabled: boolean;
  user: AuthUser | null;
  permissions: string[];
  must_change_password?: boolean;
}

export interface OverviewResponse {
  timestamp: number;
  server: {
    status: string;
    current_run_id: number | null;
    current_run_state: string;
    active_runs_total: number;
    cameras_total: number;
    web_previews_available: number;
    log_files: string[];
    journal_stats?: { available: boolean; events_total?: number; objects_total?: number };
  };
  current_run: StateRun | null;
  active_runs: StateRun[];
  cameras: StateCamera[];
  latest_logs: Array<{ name: string; updated_at: number; tail: string[] }>;
}

export interface StreamMetadataObject {
  object_id?: number | null;
  global_id?: number | null;
  track_id?: number | null;
  class_id?: number;
  class_name?: string | null;
  conf?: number | null;
  bbox?: [number, number, number, number];
  event_active?: boolean;
  attributes?: Array<{
    name: string;
    state: string;
    confidence?: number;
    frames_present?: number;
    total_time_ms?: number;
    found_ratio?: number;
  }>;
  trail?: [number, number][];
}

export interface StreamMetadata {
  source_id?: number | null;
  ts?: number;
  objects?: StreamMetadataObject[];
  zones?: Array<{ name?: string; kind?: 'poly' | 'rect'; points: [number, number][] }>;
  signalization?: boolean;
  event_labels?: string[];
  event_color?: [number, number, number];
  debug_rois?: [number, number, number, number][];
  overlay?: {
    source_name?: string;
    time_label?: string;
  };
}

/** Alias for overlays shared between live and archive playback. */
export type OverlayMetadata = StreamMetadata;

export interface PlaybackCamera {
  id: string;
  name: string;
  folder: string;
  source_id?: number | null;
  storage_folder?: string;
  parent_folder?: string | null;
  split?: boolean;
  src_coords?: [number, number, number, number] | null;
  segment_count?: number;
  available?: boolean;
}

export interface PlaybackSegment {
  path: string;
  start_ts: number;
  end_ts: number;
  duration_ms: number;
}

export interface PlaybackEventMarker {
  ts: number;
  type: string;
  camera?: string;
  row_key?: string;
}
