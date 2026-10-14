import type { ReactNode } from 'react';

/** Shared title, context and action layout for configuration and admin screens. */
export function PageHeader({ title, description, actions, className = '' }: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return <header className={`page-header ${className}`.trim()}>
    <div className="page-header-copy">
      <h2>{title}</h2>
      {description ? <p className="hint">{description}</p> : null}
    </div>
    {actions ? <div className="page-actions">{actions}</div> : null}
  </header>;
}
