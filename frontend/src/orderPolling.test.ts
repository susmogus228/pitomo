import { describe, expect, it, vi } from "vitest";
import { OrderResourceClient } from "./orderPolling";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

describe("order polling and commands", () => {
  it("retains the last order during background loading, failure and recovery", async () => {
    const pending = deferred<{ version: number }>();
    const get = vi.fn().mockResolvedValueOnce({ version: 0 }).mockImplementationOnce(() => pending.promise).mockResolvedValueOnce({ version: 1 });
    const client = new OrderResourceClient(get, vi.fn());
    await client.refresh();
    const refresh = client.refresh();
    expect(client.state.data).toEqual({ version: 0 });
    expect(client.state.loading).toBe(false);
    pending.reject(new Error("Connection failed"));
    await refresh;
    expect(client.state.data).toEqual({ version: 0 });
    expect(client.state.error).toBe("");
    expect(client.state.refreshError).toBe("Connection failed");
    await client.refresh();
    expect(client.state.data).toEqual({ version: 1 });
    expect(client.state.refreshError).toBe("");
  });
  it("prevents a late poll from overwriting a successful mutation", async () => {
    const pending = deferred<{ version: number }>();
    const get = vi.fn().mockResolvedValueOnce({ version: 0 }).mockImplementationOnce(() => pending.promise);
    const client = new OrderResourceClient(get, vi.fn());
    await client.refresh();
    const refresh = client.refresh();
    const readSignal = get.mock.calls[1][0] as AbortSignal;
    await client.mutate(async () => ({ version: 1 }));
    expect(readSignal.aborted).toBe(true);
    pending.resolve({ version: 0 });
    await refresh;
    expect(client.state.data).toEqual({ version: 1 });
  });
  it("serializes mutations and prevents polling during a command", async () => {
    const pending = deferred<{ version: number }>();
    const get = vi.fn().mockResolvedValue({ version: 0 });
    const client = new OrderResourceClient(get, vi.fn());
    await client.refresh();
    const action = vi.fn(() => pending.promise);
    const mutation = client.mutate(action);
    await client.refresh();
    await client.mutate(action);
    expect(get).toHaveBeenCalledTimes(1);
    expect(action).toHaveBeenCalledTimes(1);
    pending.resolve({ version: 1 });
    await mutation;
    expect(client.state.mutating).toBe(false);
  });
  it("can recover after a rejected command without losing the order", async () => {
    const client = new OrderResourceClient(async () => ({ version: 0 }), vi.fn());
    await client.refresh();
    await expect(client.mutate(async () => { throw new Error("Version conflict"); })).rejects.toThrow("Version conflict");
    expect(client.state.mutating).toBe(false);
    expect(client.state.data).toEqual({ version: 0 });
    await client.mutate(async () => ({ version: 1 }));
    expect(client.state.data).toEqual({ version: 1 });
  });
  it("aborts and suppresses notifications when a page is disposed", async () => {
    const pending = deferred<{ version: number }>();
    const get = vi.fn((_signal: AbortSignal) => pending.promise);
    const notify = vi.fn();
    const client = new OrderResourceClient(get, notify);
    const refresh = client.refresh();
    client.dispose();
    notify.mockClear();
    pending.resolve({ version: 0 });
    await refresh;
    expect(get.mock.calls[0][0].aborted).toBe(true);
    expect(notify).not.toHaveBeenCalled();
  });
});
