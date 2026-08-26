import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Button } from '../../components/ui';
import { useI18n } from '../../i18n';

type Props = {
  selected: string[];
  catalog: string[];
  disabled?: boolean;
  saving?: boolean;
  /** Called on every selection change; parent should persist immediately. */
  onChange: (next: string[]) => void;
};

function summaryLabel(selected: string[], noneLabel: string): string {
  if (!selected.length) return noneLabel;
  if (selected.length <= 2) return selected.join(', ');
  return `${selected.slice(0, 2).join(', ')} +${selected.length - 2}`;
}

/**
 * Compact multi-select: trigger + portal dropdown checklist from catalog.
 * Changes autosave via onChange — no Save button.
 */
export function CameraAclEditor({ selected, catalog, disabled, saving, onChange }: Props) {
  const { t } = useI18n();
  const rootRef = useRef<HTMLDivElement | null>(null);
  const dropRef = useRef<HTMLDivElement | null>(null);
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState('');
  const [draft, setDraft] = useState('');
  const [showOther, setShowOther] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number; width: number }>({
    top: 0,
    left: 0,
    width: 260,
  });

  const catalogNames = useMemo(() => {
    const set = new Set<string>();
    for (const n of catalog) {
      const v = String(n || '').trim();
      if (v) set.add(v);
    }
    return Array.from(set).sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' }));
  }, [catalog]);

  const options = useMemo(() => {
    const set = new Set(catalogNames);
    for (const n of selected) {
      const v = String(n || '').trim();
      if (v) set.add(v);
    }
    return Array.from(set).sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' }));
  }, [catalogNames, selected]);

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return options;
    return options.filter((n) => n.toLowerCase().includes(q));
  }, [options, filter]);

  const catalogEmpty = catalogNames.length === 0;
  const allowManual = catalogEmpty || showOther;

  const updatePos = () => {
    if (!rootRef.current) return;
    const r = rootRef.current.getBoundingClientRect();
    const width = Math.min(Math.max(r.width, 260), Math.min(320, window.innerWidth - 16));
    let left = r.left;
    if (left + width > window.innerWidth - 8) left = Math.max(8, window.innerWidth - width - 8);
    const dropH = dropRef.current?.offsetHeight ?? 280;
    let top = r.bottom + 4;
    if (top + dropH > window.innerHeight - 8) {
      top = Math.max(8, r.top - dropH - 4);
    }
    setPos({ top, left, width });
  };

  useLayoutEffect(() => {
    if (!open) return;
    updatePos();
  }, [open, filtered.length, allowManual]);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      const target = e.target as Node;
      if (rootRef.current?.contains(target)) return;
      if (dropRef.current?.contains(target)) return;
      setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    const onReposition = () => updatePos();
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    window.addEventListener('resize', onReposition);
    window.addEventListener('scroll', onReposition, true);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
      window.removeEventListener('resize', onReposition);
      window.removeEventListener('scroll', onReposition, true);
    };
  }, [open]);

  const toggle = (name: string) => {
    if (disabled) return;
    if (selected.includes(name)) onChange(selected.filter((n) => n !== name));
    else onChange([...selected, name]);
  };

  const selectFiltered = () => {
    if (disabled || !filtered.length) return;
    const next = new Set(selected);
    for (const n of filtered) next.add(n);
    onChange(Array.from(next));
  };

  const clearFiltered = () => {
    if (disabled || !filtered.length) return;
    const drop = new Set(filtered);
    onChange(selected.filter((n) => !drop.has(n)));
  };

  const addDraft = () => {
    const name = draft.trim();
    if (!name || disabled) return;
    if (!selected.includes(name)) onChange([...selected, name]);
    setDraft('');
  };

  const dropdown = open
    ? createPortal(
        <div
          className="camera-acl-dropdown"
          ref={dropRef}
          role="listbox"
          aria-multiselectable="true"
          style={{ top: pos.top, left: pos.left, width: pos.width }}
        >
          <input
            className="search-input camera-acl-filter"
            type="search"
            value={filter}
            disabled={disabled}
            placeholder={t('users.camerasPick')}
            onChange={(e) => setFilter(e.target.value)}
            autoFocus
          />
          <div className="camera-acl-dropdown-actions">
            <Button type="button" size="sm" variant="outline" disabled={disabled || !filtered.length} onClick={selectFiltered}>
              {t('users.camerasSelectAll')}
            </Button>
            <Button type="button" size="sm" variant="outline" disabled={disabled || !filtered.length} onClick={clearFiltered}>
              {t('users.camerasClear')}
            </Button>
          </div>
          {!filtered.length ? (
            <p className="hint camera-acl-empty">
              {catalogEmpty ? t('users.camerasEmptyAdd') : t('users.camerasNoMatch')}
            </p>
          ) : (
            <div className="camera-acl-checklist">
              {filtered.map((name) => (
                <label key={name} className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={selected.includes(name)}
                    disabled={disabled}
                    onChange={() => toggle(name)}
                  />
                  <span>{name}</span>
                </label>
              ))}
            </div>
          )}
          {!catalogEmpty && !showOther ? (
            <button
              type="button"
              className="camera-acl-other-link"
              disabled={disabled}
              onClick={() => setShowOther(true)}
            >
              {t('users.camerasOther')}
            </button>
          ) : null}
          {allowManual ? (
            <div className="camera-acl-add-row">
              <input
                className="search-input"
                type="text"
                value={draft}
                disabled={disabled}
                placeholder={t('users.camerasAddPlaceholder')}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    addDraft();
                  }
                }}
              />
              <Button type="button" size="sm" variant="outline" disabled={disabled || !draft.trim()} onClick={addDraft}>
                {t('users.camerasAdd')}
              </Button>
            </div>
          ) : null}
        </div>,
        document.body,
      )
    : null;

  return (
    <div className={`camera-acl-editor${saving ? ' is-saving' : ''}`} ref={rootRef}>
      <Button
        type="button"
        size="sm"
        variant="outline"
        className="camera-acl-trigger"
        disabled={disabled}
        onClick={() => setOpen((v) => !v)}
        title={selected.join(', ') || t('users.camerasPick')}
        aria-expanded={open}
        aria-haspopup="listbox"
      >
        {summaryLabel(selected, t('users.camerasNone'))}
      </Button>
      {dropdown}
    </div>
  );
}
