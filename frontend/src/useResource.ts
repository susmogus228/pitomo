import { useEffect, useState } from "react";
import { api, messageOf } from "./api";
import { beginResourceRequest, resourceView } from "./resourceState";
import type { ResourceState } from "./resourceState";

export function useResource<T>(path: string | null, options: { keepPreviousData?: boolean; scope?: string | number } = {}) {
  const keepPreviousData = options.keepPreviousData === true;
  const scope = options.scope;
  const [state, setState] = useState<ResourceState<T>>({ path, scope, dataPath: null, data: null, error: "", pending: Boolean(path) });
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    if (!path) {
      setState({ path: null, scope, dataPath: null, data: null, error: "", pending: false });
      return;
    }
    const controller = new AbortController();
    setState((previous) => beginResourceRequest(previous, path, keepPreviousData, scope));
    api<T>(path, { signal: controller.signal })
      .then((data) => {
        if (!controller.signal.aborted)
          setState({ path, scope, dataPath: path, data, error: "", pending: false });
      })
      .catch((error) => {
        if (!controller.signal.aborted)
          setState((previous) => ({ ...previous, error: messageOf(error), pending: false }));
      });
    return () => controller.abort();
  }, [path, revision, keepPreviousData, scope]);
  return {
    ...resourceView(state, path, keepPreviousData, scope),
    reload: () => setRevision((value) => value + 1),
    setData: (data: T) => setState({ path, scope, dataPath: path, data, error: "", pending: false }),
  };
}
