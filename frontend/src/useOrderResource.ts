import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import { isOrderTerminal } from "./delivery";
import { initialOrderResourceState, OrderResourceClient } from "./orderPolling";
import type { OrderResourceState } from "./orderPolling";
import type { Order } from "./types";

export function useOrderResource<T extends Order>(path: string | null, scope?: string | number) {
  const client = useRef<OrderResourceClient<T> | null>(null);
  const [state, setState] = useState<{ path: string | null; scope?: string | number; value: OrderResourceState<T> }>(
    () => ({ path, scope, value: initialOrderResourceState<T>() }),
  );
  useEffect(() => {
    if (!path) {
      setState({ path, scope, value: { ...initialOrderResourceState<T>(), loading: false } });
      return;
    }
    const resource = new OrderResourceClient<T>(
      (signal) => api<T>(path, { signal }),
      (value) => setState({ path, scope, value }),
    );
    client.current = resource;
    void resource.refresh();
    const refreshVisible = () => {
      if (document.visibilityState === "visible" && (!resource.state.data || !isOrderTerminal(resource.state.data)))
        void resource.refresh();
    };
    const interval = window.setInterval(refreshVisible, 10_000);
    document.addEventListener("visibilitychange", refreshVisible);
    return () => {
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", refreshVisible);
      resource.dispose();
      if (client.current === resource) client.current = null;
    };
  }, [path, scope]);
  const reload = useCallback(() => { void client.current?.refresh(); }, []);
  const mutate = useCallback(async (action: (signal: AbortSignal) => Promise<T>) => {
    await client.current?.mutate(action);
  }, []);
  return { ...(state.path === path && state.scope === scope ? state.value : initialOrderResourceState<T>()), reload, mutate };
}
