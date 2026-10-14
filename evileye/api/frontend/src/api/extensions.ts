import { API_BASE, ApiError, request } from './client';

export type ExtensionModule = {
  id: string;
  plugin_id: string;
  module_id: string;
  kind: string;
  display_name: string;
  description: string;
  stages: string[];
  execution_modes: string[];
  default_execution_mode?: string | null;
  capabilities: string[];
  config_schema?: Record<string, unknown> | null;
};

export type ExtensionPipeline = {
  id: string;
  config_id: string;
  plugin_id: string;
  pipeline_id: string;
  display_name: string;
  description: string;
  config_schema?: Record<string, unknown> | null;
  has_topology: boolean;
};

export type ExtensionCatalog = {
  modules: ExtensionModule[];
  pipelines: ExtensionPipeline[];
  default_event_detectors: string[];
  templates: Array<{ id: string; description: string; module_id: string }>;
};

export type PipelinePreview = {
  valid: boolean;
  errors: string[];
  warnings: string[];
  topology: {
    pipeline_id: string;
    title: string;
    description: string;
    nodes: Array<{ node_id: string; label: string; kind: string; stage: string; module_id?: string | null }>;
    edges: Array<{ source: string; target: string; label: string }>;
  };
};

export type PluginOperation = {
  id: string;
  status: string;
  name: string;
  plugin_id: string;
  template: string;
  directory: string;
  archive: string;
  message: string;
  created_at?: number;
  updated_at?: number;
  missing_dependencies?: string[];
};

export const extensionsApi = {
  catalog(): Promise<ExtensionCatalog> {
    return request('/admin/extensions/catalog');
  },
  preview(config: Record<string, unknown>): Promise<PipelinePreview> {
    return request('/admin/extensions/preview', { method: 'POST', body: JSON.stringify({ config }) });
  },
  saveConfig(name: string, config: Record<string, unknown>, createOnly: boolean): Promise<{ name: string; status: string; backup: string | null }> {
    return request('/admin/extensions/configs', {
      method: 'POST',
      body: JSON.stringify({ name, config, create_only: createOnly }),
    });
  },
  createPlugin(name: string, template: string): Promise<PluginOperation> {
    return request('/admin/extensions/plugins', { method: 'POST', body: JSON.stringify({ name, template }) });
  },
  operation(operationId: string): Promise<PluginOperation> {
    return request(`/admin/extensions/operations/${encodeURIComponent(operationId)}`);
  },
  operations(): Promise<PluginOperation[]> {
    return request('/admin/extensions/operations');
  },
  async downloadArchive(operationId: string, fileName: string): Promise<void> {
    const response = await fetch(`${API_BASE}/admin/extensions/operations/${encodeURIComponent(operationId)}/archive`, {
      credentials: 'same-origin',
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({ detail: response.statusText }));
      const detail = (body as { detail?: unknown }).detail;
      throw new ApiError(response.status, typeof detail === 'string' ? detail : response.statusText);
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = fileName;
    anchor.click();
    URL.revokeObjectURL(url);
  },
};
