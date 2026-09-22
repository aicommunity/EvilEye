import { useCallback, useEffect, useState } from 'react';

export type BasicSetupSectionId = 'system' | 'sources' | 'analytics' | 'alarm';

const STORAGE_PREFIX = 'evileye.basicSetup.sections.v1';

type SectionState = Partial<Record<BasicSetupSectionId, boolean>>;

function storageKey(configName: string): string {
  return `${STORAGE_PREFIX}:${configName}`;
}

function loadSections(configName: string): SectionState {
  try {
    const raw = localStorage.getItem(storageKey(configName));
    if (!raw) return {};
    const parsed = JSON.parse(raw) as SectionState;
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

function saveSections(configName: string, state: SectionState): void {
  try {
    localStorage.setItem(storageKey(configName), JSON.stringify(state));
  } catch {
    /* ignore quota errors */
  }
}

export function useBasicSetupSections(
  configName: string,
  defaults: Record<BasicSetupSectionId, boolean>,
): {
  isOpen: (id: BasicSetupSectionId) => boolean;
  setOpen: (id: BasicSetupSectionId, open: boolean) => void;
} {
  const [state, setState] = useState<SectionState>(() => loadSections(configName));

  useEffect(() => {
    setState(loadSections(configName));
  }, [configName]);

  const isOpen = useCallback(
    (id: BasicSetupSectionId) => {
      if (id in state) return Boolean(state[id]);
      return defaults[id] ?? false;
    },
    [state, defaults],
  );

  const setOpen = useCallback(
    (id: BasicSetupSectionId, open: boolean) => {
      setState((prev) => {
        const next = { ...prev, [id]: open };
        saveSections(configName, next);
        return next;
      });
    },
    [configName],
  );

  return { isOpen, setOpen };
}
