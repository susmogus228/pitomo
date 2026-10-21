import { messageOf } from "./api";

export interface OrderResourceState<T> {
  data: T | null;
  error: string;
  refreshError: string;
  loading: boolean;
  refreshing: boolean;
  mutating: boolean;
}
export const initialOrderResourceState = <T>(): OrderResourceState<T> => ({
  data: null, error: "", refreshError: "", loading: true, refreshing: false, mutating: false,
});

// One owner serializes reads and mutations so a slow poll cannot undo a command.
export class OrderResourceClient<T> {
  state = initialOrderResourceState<T>();
  private generation = 0;
  private read: AbortController | null = null;
  private mutation: AbortController | null = null;
  private disposed = false;
  constructor(
    private get: (signal: AbortSignal) => Promise<T>,
    private notify: (state: OrderResourceState<T>) => void,
  ) {}
  private update(patch: Partial<OrderResourceState<T>>) {
    if (this.disposed) return;
    this.state = { ...this.state, ...patch };
    this.notify(this.state);
  }
  async refresh() {
    if (this.disposed || this.state.mutating || this.read) return;
    const token = ++this.generation;
    const controller = new AbortController();
    this.read = controller;
    this.update({ refreshing: true, loading: this.state.data === null });
    try {
      const data = await this.get(controller.signal);
      if (!controller.signal.aborted && token === this.generation)
        this.update({ data, error: "", refreshError: "" });
    } catch (error) {
      if (!controller.signal.aborted && token === this.generation)
        this.update(this.state.data ? { refreshError: messageOf(error) } : { error: messageOf(error) });
    } finally {
      if (token === this.generation) {
        this.read = null;
        this.update({ loading: false, refreshing: false });
      }
    }
  }
  async mutate(action: (signal: AbortSignal) => Promise<T>): Promise<void> {
    if (this.disposed || this.state.mutating) return;
    ++this.generation;
    this.read?.abort();
    this.read = null;
    const controller = new AbortController();
    this.mutation = controller;
    this.update({ mutating: true, refreshing: false });
    try {
      const data = await action(controller.signal);
      if (!controller.signal.aborted)
        this.update({ data, error: "", refreshError: "", loading: false });
    } finally {
      this.mutation = null;
      this.update({ mutating: false });
    }
  }
  dispose() {
    this.disposed = true;
    ++this.generation;
    this.read?.abort();
    this.mutation?.abort();
  }
}
