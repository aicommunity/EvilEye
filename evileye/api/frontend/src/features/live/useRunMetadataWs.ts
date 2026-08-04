import { useEffect, useRef, useState } from 'react';
import { streamMetadataWsUrl, type StreamMetadata } from '../../api';

export function useRunMetadataWs(rid: number | null, sourceId: number | null | undefined) {
  const [meta, setMeta] = useState<StreamMetadata | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    setMeta(null);
    if (rid == null) return;
    const url = streamMetadataWsUrl(rid, sourceId ?? null);
    let ws: WebSocket;
    try {
      ws = new WebSocket(url);
    } catch {
      return;
    }
    wsRef.current = ws;
    ws.onmessage = (ev) => {
      try {
        setMeta(JSON.parse(String(ev.data)) as StreamMetadata);
      } catch {
        /* ignore */
      }
    };
    ws.onerror = () => {
      /* server may not support WS yet */
    };
    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [rid, sourceId]);

  return meta;
}
