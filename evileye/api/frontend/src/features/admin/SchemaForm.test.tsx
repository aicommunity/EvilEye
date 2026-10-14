import { render, screen } from '@testing-library/react';
import { I18nProvider } from '../../i18n';
import { describe, expect, it } from 'vitest';
import type { RJSFSchema } from '@rjsf/utils';
import { mergeUnknownFields, SchemaForm } from './SchemaForm';

const schema: RJSFSchema = {
  type: 'object',
  properties: {
    threshold: { type: 'number', title: 'Threshold', default: 0.5 },
    options: {
      type: 'object', title: 'Options', properties: {
        enabled: { type: 'boolean', title: 'Enabled', default: true },
        mode: { type: 'string', title: 'Mode', enum: ['fast', 'accurate'] },
      },
    },
    credentials: { type: 'object', properties: { api_token: { type: 'string', title: 'API token', writeOnly: true } } },
    unconfigured: { type: 'string', title: 'Not configured' },
    labels: { type: 'array', title: 'Labels', items: { type: 'string' } },
    cameras: {
      type: 'array', title: 'Camera rules', items: {
        type: 'object', properties: {
          source: { type: 'string', title: 'Source' },
          active: { type: 'boolean', title: 'Active' },
          token: { type: 'string', writeOnly: true },
        },
      },
    },
  },
};

describe('SchemaForm', () => {
  it('renders nested fields and collections as editable controls', () => {
    render(<I18nProvider><SchemaForm schema={schema} value={{ options: { mode: 'fast' }, labels: ['person'], cameras: [{ source: 'north', active: true }] }} onChange={() => undefined} /></I18nProvider>);
    expect((screen.getByLabelText('Threshold') as HTMLInputElement).value).toBe('0.5');
    expect(screen.getByText('Используется значение по умолчанию из схемы: 0.5. Измените поле, чтобы переопределить его.')).toBeTruthy();
    expect((screen.getByLabelText('Not configured') as HTMLInputElement).placeholder).toBe('Не задано в конфигурации');
    expect((screen.getByLabelText('Mode') as HTMLSelectElement).selectedOptions[0].textContent).toBe('fast');
    expect(screen.getByLabelText('Enabled')).toBeTruthy();
    expect(screen.getByDisplayValue('person')).toBeTruthy();
    expect(screen.getByText('Camera rules')).toBeTruthy();
    expect(screen.getByText(/Элемент 1/)).toBeTruthy();
  });

  it('keeps unknown values at the root and inside schema objects', () => {
    const updated = mergeUnknownFields(
      { threshold: 0.5, vendor_option: 'keep', options: { mode: 'fast', vendor_mode: 'custom' } },
      { threshold: 0.8, options: { mode: 'accurate' } },
      schema,
    ) as Record<string, unknown>;
    expect(updated).toMatchObject({ threshold: 0.8, vendor_option: 'keep', options: { mode: 'accurate', vendor_mode: 'custom' } });
  });

  it('does not expose or clear saved secret values on an empty edit', () => {
    render(<I18nProvider><SchemaForm schema={schema} value={{ credentials: { api_token: 'secret-value' } }} onChange={() => undefined} /></I18nProvider>);
    expect((screen.getByLabelText('API token') as HTMLInputElement).type).toBe('password');
    const updated = mergeUnknownFields({ credentials: { api_token: 'secret-value' } }, { credentials: { api_token: '' } }, schema);
    expect(updated).toMatchObject({ credentials: { api_token: 'secret-value' } });
  });

  it('preserves unknown values and secrets inside arrays of configured objects', () => {
    const updated = mergeUnknownFields(
      { cameras: [{ source: 'north', active: true, vendor_option: 'keep', token: 'saved' }] },
      { cameras: [{ source: 'south', active: false, token: '' }] },
      schema,
    );
    expect(updated).toMatchObject({ cameras: [{ source: 'south', active: false, vendor_option: 'keep', token: 'saved' }] });
  });
});
