import { describe, expect, it } from 'vitest';
import { schemaDefaults, schemaFieldValue } from './schemaDefaults';

describe('schema defaults for builder forms', () => {
  it('recursively exposes nested object defaults, including nullable objects', () => {
    const schema = {
      type: 'object',
      properties: {
        default_schedule: {
          type: ['object', 'null'],
          properties: {
            enabled: { type: 'boolean', default: false },
            weekdays: { type: 'array', default: [0, 1, 2, 3, 4, 5, 6] },
            periods: { type: 'array', items: { type: 'array' } },
          },
        },
      },
    };

    expect(schemaDefaults(schema)).toEqual({
      default_schedule: { enabled: false, weekdays: [0, 1, 2, 3, 4, 5, 6], periods: [] },
    });
    expect(schemaFieldValue({}, 'default_schedule', schema.properties.default_schedule)).toEqual(
      schemaDefaults(schema).default_schedule,
    );
  });

  it('keeps explicitly configured values and defaults falsy values', () => {
    const field = { type: 'boolean', default: false };
    expect(schemaFieldValue({}, 'enabled', field)).toBe(false);
    expect(schemaFieldValue({ enabled: true }, 'enabled', field)).toBe(true);
    expect(schemaFieldValue({}, 'threshold', { type: 'integer', default: 0 })).toBe(0);
    expect(schemaFieldValue({}, 'unset', { type: 'number' })).toBeUndefined();
  });
});
