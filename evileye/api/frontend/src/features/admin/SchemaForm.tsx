import Form from '@rjsf/core';
import validator from '@rjsf/validator-ajv8';
import { buttonId, canExpand, descriptionId, getTemplate, getUiOptions, titleId, type ArrayFieldItemButtonsTemplateProps, type ArrayFieldTemplateProps, type FormContextType, type ObjectFieldTemplateProps, type RJSFSchema, type StrictRJSFSchema, type UiSchema } from '@rjsf/utils';
import { useI18n } from '../../i18n';

type JsonObject = Record<string, unknown>;

function prepareSchema(schema: RJSFSchema, excluded: Set<string>): RJSFSchema {
  if (!excluded.size || !schema.properties || typeof schema.properties !== 'object') return schema;
  const properties = Object.fromEntries(Object.entries(schema.properties).filter(([key]) => !excluded.has(key)));
  return { ...schema, properties, required: schema.required?.filter((key) => !excluded.has(key)) };
}

export function mergeUnknownFields(previous: unknown, next: unknown, schema: RJSFSchema): unknown {
  if (Array.isArray(previous) && Array.isArray(next)) {
    return next.map((item, index) => {
      const itemSchema = Array.isArray(schema.items) ? schema.items[index] as RJSFSchema | undefined
        : schema.items && typeof schema.items === 'object' ? schema.items as RJSFSchema : undefined;
      return itemSchema ? mergeUnknownFields(previous[index], item, itemSchema) : mergeUnspecifiedValue(previous[index], item);
    });
  }
  if (!previous || !next || typeof previous !== 'object' || typeof next !== 'object' || Array.isArray(previous) || Array.isArray(next)) return next;
  const properties = schema.properties && typeof schema.properties === 'object' ? schema.properties as Record<string, RJSFSchema> : {};
  const merged: JsonObject = { ...previous as JsonObject, ...next as JsonObject };
  for (const [key, value] of Object.entries(previous as JsonObject)) {
    const matchingPattern = schema.patternProperties ? Object.entries(schema.patternProperties).find(([pattern]) => {
      try { return new RegExp(pattern).test(key); } catch { return false; }
    })?.[1] as RJSFSchema | undefined : undefined;
    const fieldSchema = properties[key]
      || matchingPattern
      || (schema.additionalProperties && typeof schema.additionalProperties === 'object' ? schema.additionalProperties as RJSFSchema : undefined);
    const nextValue = (next as JsonObject)[key];
    if (isSensitiveField(key, fieldSchema) && (nextValue === '' || nextValue === null || nextValue === undefined)) {
      merged[key] = value;
    } else if (fieldSchema && nextValue && value && typeof nextValue === 'object' && typeof value === 'object') {
      merged[key] = mergeUnknownFields(value, nextValue, fieldSchema);
    } else if (!fieldSchema && nextValue && value && typeof nextValue === 'object' && typeof value === 'object') {
      merged[key] = mergeUnspecifiedValue(value, nextValue);
    }
  }
  return merged;
}

function mergeUnspecifiedValue(previous: unknown, next: unknown): unknown {
  if (Array.isArray(previous) && Array.isArray(next)) return next.map((item, index) => mergeUnspecifiedValue(previous[index], item));
  if (!previous || !next || typeof previous !== 'object' || typeof next !== 'object' || Array.isArray(previous) || Array.isArray(next)) return next;
  const merged = { ...previous, ...next } as JsonObject;
  for (const [key, value] of Object.entries(previous)) {
    const current = (next as JsonObject)[key];
    if (isSensitiveField(key) && (current === '' || current === null || current === undefined)) merged[key] = value;
    else if (current && value && typeof current === 'object' && typeof value === 'object') merged[key] = mergeUnspecifiedValue(value, current);
  }
  return merged;
}

function isSensitiveField(key: string, schema?: RJSFSchema): boolean {
  return Boolean(schema?.secret || schema?.writeOnly) || /password|secret|token|api_key|private_key/i.test(key);
}

function effectiveType(schema: RJSFSchema): unknown {
  return Array.isArray(schema.type) ? schema.type.find((type) => type !== 'null') : schema.type;
}

function schemaUiHints(schema: RJSFSchema, value: unknown, translate: (key: string, values?: Record<string, string | number>) => string, root = false): UiSchema {
  const properties = schema.properties && typeof schema.properties === 'object' ? schema.properties as Record<string, RJSFSchema> : {};
  const fields: Record<string, unknown> = {};
  for (const [key, field] of Object.entries(properties)) {
    const current = value && typeof value === 'object' && !Array.isArray(value) ? (value as JsonObject)[key] : undefined;
    const hasCurrent = Boolean(value && typeof value === 'object' && !Array.isArray(value) && Object.prototype.hasOwnProperty.call(value, key));
    const hints: Record<string, unknown> = {};
    if (isSensitiveField(key, field)) {
      hints['ui:widget'] = 'password';
      hints['ui:autocomplete'] = 'new-password';
      hints['ui:placeholder'] = hasCurrent ? translate('builder.secretHint') : translate('builder.notSet');
    } else if (effectiveType(field) === 'object' && field.properties) {
      Object.assign(hints, schemaUiHints(field, current, translate));
    } else if (effectiveType(field) === 'array' && field.items && typeof field.items === 'object' && 'properties' in field.items) {
      hints.items = schemaUiHints(field.items as RJSFSchema, undefined, translate);
    }
    if (!hasCurrent && Object.prototype.hasOwnProperty.call(field, 'default') && !isSensitiveField(key, field)) {
      const defaultValue = typeof field.default === 'string' ? field.default : JSON.stringify(field.default) ?? String(field.default);
      hints['ui:help'] = translate('builder.schemaDefaultShown', { value: defaultValue });
    } else if (!hasCurrent && effectiveType(field) !== 'object' && effectiveType(field) !== 'array' && !isSensitiveField(key, field)) {
      hints['ui:placeholder'] = translate('builder.notSet');
    }
    fields[key] = hints;
  }
  return { ...fields, ...(root ? { 'ui:submitButtonOptions': { norender: true } } : {}) } as UiSchema;
}

function schemaSecurityHints(schema: RJSFSchema): UiSchema {
  const fields: Record<string, unknown> = {};
  const properties = schema.properties && typeof schema.properties === 'object' ? schema.properties as Record<string, RJSFSchema> : {};
  for (const [key, field] of Object.entries(properties)) {
    if (isSensitiveField(key, field)) fields[key] = { 'ui:widget': 'password', 'ui:autocomplete': 'new-password' };
    else if (effectiveType(field) === 'object' && field.properties) fields[key] = schemaSecurityHints(field);
    else if (effectiveType(field) === 'array' && field.items && typeof field.items === 'object' && 'properties' in field.items) {
      fields[key] = { items: schemaSecurityHints(field.items as RJSFSchema) };
    }
  }
  return fields as UiSchema;
}

function mergeUiSchema(base: UiSchema, custom?: UiSchema): UiSchema {
  if (!custom) return base;
  const merged: Record<string, unknown> = { ...base, ...custom };
  for (const [key, value] of Object.entries(custom)) {
    const current = base[key];
    if (current && value && typeof current === 'object' && typeof value === 'object' && !Array.isArray(current) && !Array.isArray(value)) {
      merged[key] = mergeUiSchema(current as UiSchema, value as UiSchema);
    }
  }
  return merged as UiSchema;
}

function FriendlyArrayButtons<T = any, S extends StrictRJSFSchema = RJSFSchema, F extends FormContextType = any>(props: ArrayFieldItemButtonsTemplateProps<T, S, F>) {
  const { t } = useI18n();
  const { disabled, readonly, hasMoveUp, hasMoveDown, hasRemove, onMoveUpItem, onMoveDownItem, onRemoveItem } = props;
  return <div className="schema-array-actions">
    {hasMoveUp || hasMoveDown ? <>
      <button type="button" disabled={disabled || readonly || !hasMoveUp} onClick={onMoveUpItem} aria-label={t('builder.moveUp')} title={t('builder.moveUp')}>↑</button>
      <button type="button" disabled={disabled || readonly || !hasMoveDown} onClick={onMoveDownItem} aria-label={t('builder.moveDown')} title={t('builder.moveDown')}>↓</button>
    </> : null}
    {hasRemove ? <button type="button" className="is-danger" disabled={disabled || readonly} onClick={onRemoveItem}>{t('builder.remove')}</button> : null}
  </div>;
}

function FriendlyArrayTemplate<T = any, S extends StrictRJSFSchema = RJSFSchema, F extends FormContextType = any>(props: ArrayFieldTemplateProps<T, S, F>) {
  const { t } = useI18n();
  const { canAdd, disabled, fieldPathId, items, onAddClick, readonly, required, schema, title, uiSchema, registry } = props;
  const options = getUiOptions<T, S, F>(uiSchema);
  const Description = getTemplate<'ArrayFieldDescriptionTemplate', T, S, F>('ArrayFieldDescriptionTemplate', registry, options);
  const itemSchema = schema.items && !Array.isArray(schema.items) ? schema.items as RJSFSchema : undefined;
  const objectItems = Boolean(itemSchema?.properties || itemSchema?.additionalProperties);
  const values = Array.isArray(props.formData) ? props.formData as unknown[] : [];
  return <fieldset className="schema-array" id={fieldPathId.$id}>
    <legend>{options.title || title}{required ? <span className="required-mark"> *</span> : null}</legend>
    {options.description || schema.description ? <Description fieldPathId={fieldPathId} description={options.description || schema.description} schema={schema} uiSchema={uiSchema} registry={registry} /> : null}
    <div className="schema-array-list">{items.map((item, index) => {
      if (!objectItems) return <div className="schema-array-row" key={item.key}>{item}</div>;
      const row = values[index] && typeof values[index] === 'object' && !Array.isArray(values[index]) ? values[index] as JsonObject : {};
      const label = ['name', 'title', 'label', 'id', 'type'].map((key) => row[key]).find((value) => typeof value === 'string' || typeof value === 'number');
      const summary = label == null ? t('builder.arrayItem', { index: index + 1 }) : `${t('builder.arrayItem', { index: index + 1 })} · ${String(label)}`;
      return <details className="schema-array-object" key={item.key} open={index === items.length - 1}>
        <summary>{summary}</summary>
        {item}
      </details>;
    })}</div>
    {canAdd ? <button type="button" className="schema-array-add" onClick={onAddClick} disabled={disabled || readonly}>{t('builder.addArrayItem')}</button> : null}
  </fieldset>;
}

function FriendlyObjectTemplate<T = any, S extends StrictRJSFSchema = RJSFSchema, F extends FormContextType = any>(props: ObjectFieldTemplateProps<T, S, F>) {
  const { t } = useI18n();
  const { className, description, disabled, fieldPathId, formData, onAddProperty, optionalDataControl, properties, readonly, registry, required, schema, title, uiSchema } = props;
  const options = getUiOptions<T, S, F>(uiSchema);
  const Title = getTemplate<'TitleFieldTemplate', T, S, F>('TitleFieldTemplate', registry, options);
  const Description = getTemplate<'DescriptionFieldTemplate', T, S, F>('DescriptionFieldTemplate', registry, options);
  const showOptionalDataControlInTitle = !readonly && !disabled;
  return <fieldset className={className} id={fieldPathId.$id}>
    {title ? <Title id={titleId(fieldPathId)} title={options.title || title} required={required} schema={schema} uiSchema={uiSchema}
      registry={registry} optionalDataControl={showOptionalDataControlInTitle ? optionalDataControl : undefined} /> : null}
    {description ? <Description id={descriptionId(fieldPathId)} description={options.description || description} schema={schema} uiSchema={uiSchema} registry={registry} /> : null}
    {!showOptionalDataControlInTitle ? optionalDataControl : null}
    {properties.map((property) => property.content)}
    {canExpand<T, S, F>(schema, uiSchema, formData) ? <button type="button" id={buttonId(fieldPathId, 'add')} className="rjsf-object-property-expand"
      onClick={onAddProperty} disabled={disabled || readonly}>{t('builder.addDictionaryEntry')}</button> : null}
  </fieldset>;
}

export function SchemaForm({
  schema,
  value,
  onChange,
  uiSchema,
  excluded = new Set<string>(),
  idPrefix = 'module-config',
  emptyMessage = 'No schema fields are available for this module.',
}: {
  schema?: Record<string, unknown> | null;
  value: JsonObject;
  onChange: (next: JsonObject) => void;
  uiSchema?: Record<string, unknown> | null;
  excluded?: Set<string>;
  idPrefix?: string;
  emptyMessage?: string;
}) {
  const { t } = useI18n();
  if (!schema || !Object.keys((schema.properties || {}) as object).some((key) => !excluded.has(key))) {
    return <p className="hint">{emptyMessage}</p>;
  }
  const usableSchema = prepareSchema(schema as RJSFSchema, excluded);
  const defaultsAndHints = mergeUiSchema(schemaUiHints(usableSchema, value, t, true), uiSchema as UiSchema | undefined);
  const mergedUiSchema = mergeUiSchema(defaultsAndHints, schemaSecurityHints(usableSchema));
  return <div className="schema-form">
    <Form
      idPrefix={idPrefix}
      schema={usableSchema}
      uiSchema={mergedUiSchema}
      formData={value}
      validator={validator}
      noHtml5Validate
      liveValidate
      templates={{ ArrayFieldTemplate: FriendlyArrayTemplate, ArrayFieldItemButtonsTemplate: FriendlyArrayButtons, ObjectFieldTemplate: FriendlyObjectTemplate }}
      onChange={({ formData }) => onChange((mergeUnknownFields(value, formData || {}, usableSchema) || {}) as JsonObject)}
      onSubmit={(_data, event) => event.preventDefault()}
    />
  </div>;
}
