export type JsonSchema = Record<string, any>;

function effectiveType(schema: JsonSchema): unknown {
  return Array.isArray(schema.type)
    ? schema.type.find((item: unknown) => item !== 'null')
    : schema.type;
}

export function schemaDefaults(schema?: JsonSchema | null): Record<string, any> {
  const result: Record<string, any> = {};
  const properties = schema?.properties && typeof schema.properties === 'object' && !Array.isArray(schema.properties)
    ? schema.properties as Record<string, JsonSchema>
    : {};
  for (const [key, field] of Object.entries(properties)) {
    if (!field || typeof field !== 'object' || Array.isArray(field)) continue;
    if (Object.prototype.hasOwnProperty.call(field, 'default')) result[key] = field.default;
    else if (effectiveType(field) === 'object') result[key] = schemaDefaults(field);
    else if (effectiveType(field) === 'array') result[key] = [];
  }
  return result;
}

export function schemaFieldValue(value: Record<string, any>, key: string, field: JsonSchema): unknown {
  if (Object.prototype.hasOwnProperty.call(value, key)) return value[key];
  if (Object.prototype.hasOwnProperty.call(field, 'default')) return field.default;
  const type = effectiveType(field);
  if (type === 'object') return schemaDefaults(field);
  if (type === 'array') return [];
  return undefined;
}
