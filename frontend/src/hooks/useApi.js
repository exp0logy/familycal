// ─────────────────────────────────────────────────────────────────────────────
// useApi — generic data-fetching hook with loading / error / refetch state.
//
// Usage:
//   const { data, loading, error, refetch } = useApi(() => ApiClient.getAgenda(7));
// ─────────────────────────────────────────────────────────────────────────────

import { useState, useEffect, useCallback, useRef } from 'react';

/**
 * @template T
 * @param {() => Promise<T>} fetcher  Stable function reference preferred
 * @param {T|null}           [initial] Initial value while loading
 * @returns {{ data: T|null, loading: boolean, error: string|null, refetch: () => void }}
 */
const useApi = (fetcher, initial = null) => {
  const [data, setData]       = useState(initial);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);
  const fetcherRef = useRef(fetcher);
  useEffect(() => { fetcherRef.current = fetcher; }, [fetcher]);

  const run = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetcherRef.current();
      setData(result);
    } catch (e) {
      setError(e?.detail ?? e?.message ?? 'Unknown error');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { run(); }, [run]);

  return { data, loading, error, refetch: run };
};

export default useApi;
