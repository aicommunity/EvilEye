import type { ReactNode } from 'react';

export function FormGrid({ children }: { children: ReactNode }) {
  return <div className="config-form-grid">{children}</div>;
}

export function FormField({
  label,
  children,
  hint,
  fullWidth,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
  fullWidth?: boolean;
}) {
  return (
    <>
      <label className={fullWidth ? 'full-width' : undefined}>{label}</label>
      <div className={fullWidth ? 'full-width' : undefined}>
        {children}
        {hint ? <p className="hint" style={{ margin: '0.25rem 0 0' }}>{hint}</p> : null}
      </div>
    </>
  );
}

export function FormActions({ children }: { children: ReactNode }) {
  return <div className="toolbar config-form-actions">{children}</div>;
}
