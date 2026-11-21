import type { ReactNode } from 'react';
import type { BasicSetupSectionId } from './useBasicSetupSections';

export type BasicSetupSectionProps = {
  id: BasicSetupSectionId;
  title: string;
  summary: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  disabled?: boolean;
  disabledHint?: string;
  children: ReactNode;
};

export function BasicSetupSection({
  title,
  summary,
  open,
  onOpenChange,
  disabled,
  disabledHint,
  children,
}: BasicSetupSectionProps) {
  const meta = disabled && disabledHint ? disabledHint : summary;

  return (
    <details
      className={`basic-setup-section${disabled ? ' basic-setup-section--disabled' : ''}`}
      open={open}
      onToggle={(e) => onOpenChange((e.target as HTMLDetailsElement).open)}
    >
      <summary className="basic-setup-section__summary">
        <span className="basic-setup-section__chevron" aria-hidden />
        <span className="basic-setup-section__title">{title}</span>
        <span className="basic-setup-section__meta">{meta}</span>
      </summary>
      <div className="basic-setup-section__body">
        {disabled && disabledHint ? (
          <p className="hint basic-setup-section__disabled-hint">{disabledHint}</p>
        ) : null}
        <fieldset disabled={disabled} className="basic-setup-section__fieldset">
          {children}
        </fieldset>
      </div>
    </details>
  );
}
