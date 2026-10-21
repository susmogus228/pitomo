export interface ResourceState<T> {
  path: string | null;
  dataPath: string | null;
  data: T | null;
  error: string;
  pending: boolean;
  scope?: string | number;
}

export function beginResourceRequest<T>(previous: ResourceState<T>, path: string, keepPreviousData = false, scope?: string | number): ResourceState<T> {
  const preserve = previous.scope === scope && (previous.dataPath === path || keepPreviousData);
  return { path, scope, dataPath: preserve ? previous.dataPath : null, data: preserve ? previous.data : null, error: "", pending: true };
}

export function resourceView<T>(state: ResourceState<T>, path: string | null, keepPreviousData = false, scope?: string | number) {
  const sameScope = state.scope === scope;
  const matches = state.path === path && sameScope;
  const data = path && sameScope && (state.dataPath === path || keepPreviousData) ? state.data : null;
  const pending = Boolean(path) && (!matches || state.pending);
  return { data, dataPath: data !== null ? state.dataPath : null, error: matches && path ? state.error : "", loading: pending && data === null, refreshing: pending && data !== null };
}
