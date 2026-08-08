import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { useI18n } from '../../i18n';

export function Button({
  variant = 'outline',
  size = 'md',
  className = '',
  type = 'button',
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'outline' | 'danger' | 'success';
  size?: 'sm' | 'md';
  children: ReactNode;
}) {
  const sizeClass = size === 'sm' ? 'btn-sm' : '';
  return (
    <button type={type} className={`btn btn-${variant} ${sizeClass} ${className}`.trim()} {...rest}>
      {children}
    </button>
  );
}

export function Badge({ state, children }: { state?: string; children: ReactNode }) {
  const cls =
    state === 'running'
      ? 'badge-running'
      : state === 'error'
        ? 'badge-error'
        : state === 'starting'
          ? 'badge-pending'
          : 'badge-stopped';
  return <span className={`badge ${cls}`}>{children}</span>;
}

export function MetricCard({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="metric-card">
      <span className="metric-label">{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export function Modal({
  open,
  title,
  onClose,
  children,
  footer,
  wide,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
}) {
  const { t } = useI18n();
  if (!open) return null;
  return (
    <div className="modal open" role="dialog" aria-modal="true">
      <div className="modal-backdrop" onClick={onClose} />
      <div className={`modal-content ${wide ? 'modal-content-wide' : ''}`}>
        <div className="modal-header">
          <h2>{title}</h2>
          <Button variant="outline" onClick={onClose} aria-label={t('common.close')}>
            &times;
          </Button>
        </div>
        <div className="modal-body">{children}</div>
        {footer ? <div className="modal-footer">{footer}</div> : null}
      </div>
    </div>
  );
}
