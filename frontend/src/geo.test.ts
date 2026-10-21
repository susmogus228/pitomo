import { afterEach, describe, expect, it, vi } from "vitest";
import { currentPosition, roundedPoint, validPoint } from "./geo";

afterEach(() => vi.unstubAllGlobals());

describe("explicit location request", () => {
  it("accepts boundary coordinates and rejects invalid map or checkout points", () => {
    expect(validPoint({ lat: -90, lon: 180 })).toBe(true);
    expect(validPoint({ lat: 90.01, lon: 0 })).toBe(false);
    expect(validPoint({ lat: 10, lon: Infinity })).toBe(false);
    expect(roundedPoint({ lat: 43.238901234, lon: 76.889712345 })).toEqual({ lat: 43.2389012, lon: 76.8897123 });
  });

  it("requests a bounded, low-accuracy browser position only when called", async () => {
    const getCurrentPosition = vi.fn((success: PositionCallback, _failure?: PositionErrorCallback, _options?: PositionOptions) => success({ coords: { latitude: 43.2389, longitude: 76.8897 } } as GeolocationPosition));
    vi.stubGlobal("navigator", { geolocation: { getCurrentPosition } });
    expect(getCurrentPosition).not.toHaveBeenCalled();
    await expect(currentPosition()).resolves.toEqual({ lat: 43.2389, lon: 76.8897 });
    expect(getCurrentPosition.mock.calls[0][2]).toEqual({ enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 });
  });

  it("provides manual map fallback when browser permission is denied", async () => {
    vi.stubGlobal("navigator", { geolocation: { getCurrentPosition: (_: PositionCallback, failure: PositionErrorCallback) => failure({ code: 1 } as GeolocationPositionError) } });
    await expect(currentPosition()).rejects.toThrow("Выберите точку на карте");
  });
});
