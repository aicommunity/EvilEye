/** Display/parse helpers for Configure number inputs. */

export const INT_STEP = '1';
export const DECIMAL_STEP = '0.001';

export function formatInt(n: number | null | undefined): string {
  if (n == null) return '';
  const x = Number(n);
  if (!Number.isFinite(x)) return '';
  return String(Math.round(x));
}

/** Up to `maxFrac` digits after the decimal; strips trailing zeros. */
export function formatDecimal(n: number | null | undefined, maxFrac = 3): string {
  if (n == null) return '';
  const x = Number(n);
  if (!Number.isFinite(x)) return '';
  const factor = 10 ** maxFrac;
  const rounded = Math.round(x * factor) / factor;
  // Avoid scientific notation / long tails from binary floats.
  let s = rounded.toFixed(maxFrac);
  if (s.includes('.')) {
    s = s.replace(/\.?0+$/, '');
  }
  return s;
}

/** Integer if nearly whole, else up to 3 decimal places. */
export function formatSmartNumber(n: number | null | undefined, maxFrac = 3): string {
  if (n == null) return '';
  const x = Number(n);
  if (!Number.isFinite(x)) return '';
  if (Math.abs(x - Math.round(x)) < 1e-9) return formatInt(x);
  return formatDecimal(x, maxFrac);
}

export function parseIntInput(raw: string): number | undefined {
  const t = raw.trim();
  if (t === '') return undefined;
  const x = Number(t);
  if (!Number.isFinite(x)) return undefined;
  return Math.round(x);
}

export function parseDecimalInput(raw: string, maxFrac = 3): number | undefined {
  const t = raw.trim();
  if (t === '') return undefined;
  const x = Number(t);
  if (!Number.isFinite(x)) return undefined;
  const factor = 10 ** maxFrac;
  return Math.round(x * factor) / factor;
}

export function parseSmartNumberInput(raw: string, maxFrac = 3): number | undefined {
  const t = raw.trim();
  if (t === '') return undefined;
  const x = Number(t);
  if (!Number.isFinite(x)) return undefined;
  if (Math.abs(x - Math.round(x)) < 1e-9) return Math.round(x);
  return parseDecimalInput(raw, maxFrac);
}
