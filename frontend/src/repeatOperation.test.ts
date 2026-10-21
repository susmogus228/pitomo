import { describe, expect, it } from "vitest";
import {
  clearRepeatOperation,
  readRepeatOperation,
  REPEAT_OPERATION_TTL,
  saveRepeatOperation,
} from "./repeatOperation";

describe("uncertain repeat operation", () => {
  const receipt = {
    owner_id: 37,
    order_id: 82,
    fingerprint: "a".repeat(64),
    operation_key: "same-operation-key",
  };
  it("retains the exact confirmed payload for a retry across component remounts", () => {
    const values = new Map<string, string>();
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => {
        values.set(key, value);
      },
      removeItem: (key: string) => {
        values.delete(key);
      },
    };
    expect(saveRepeatOperation(receipt, storage, 10)).toBe(true);
    expect(readRepeatOperation(37, 82, storage, 11)).toEqual(receipt);
    expect(readRepeatOperation(38, 82, storage, 11)).toBeNull();
    expect(readRepeatOperation(37, 83, storage, 11)).toBeNull();
    expect(
      readRepeatOperation(37, 82, storage, REPEAT_OPERATION_TTL + 11),
    ).toBeNull();
  });
  it("uses memory when session storage denies writes and tombstones after success", () => {
    const storage = {
      getItem: () => null,
      setItem: () => {
        throw Error("quota");
      },
      removeItem: () => {
        throw Error("quota");
      },
    };
    expect(saveRepeatOperation(receipt, storage, 10)).toBe(false);
    expect(readRepeatOperation(37, 82, storage, 11)).toEqual(receipt);
    clearRepeatOperation(37, 82, storage);
    expect(readRepeatOperation(37, 82, storage, 12)).toBeNull();
  });
});
