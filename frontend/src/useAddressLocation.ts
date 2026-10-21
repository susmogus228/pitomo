import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import {
  editAddress,
  kazakhstanAddresses,
  LatestAddressRequest,
  suggestionLocation,
} from "./address";
import type { AddressLocation, AddressSuggestion, GeoConfig } from "./address";
import { currentPosition, roundedPoint } from "./geo";
import type { GeoPoint } from "./geo";
import { messageOf } from "./api";
import { useResource } from "./useResource";

export function useAddressLocation(initial?: AddressLocation) {
  const [location, setLocation] = useState<AddressLocation>(
    initial || { address: "", point: null },
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const reverse = useRef(new LatestAddressRequest());
  const geoConfig = useResource<GeoConfig>("/geo/config");
  useEffect(() => () => reverse.current.cancel(), []);
  const restoreLocation = useCallback((next: AddressLocation) => {
    reverse.current.cancel();
    setBusy(false);
    setError("");
    setNote("");
    setLocation(next);
  }, []);
  const changeAddress = (value: string) => {
    reverse.current.cancel();
    setBusy(false);
    setError("");
    setNote("");
    setLocation(editAddress(value));
  };
  const selectSuggestion = (item: AddressSuggestion) => {
    reverse.current.cancel();
    setBusy(false);
    setError("");
    setNote("Адрес найден. Можно уточнить точку на карте.");
    setLocation(suggestionLocation(item));
  };
  const selectPoint = async (point: GeoPoint) => {
    const next = roundedPoint(point);
    const request = reverse.current.start();
    setLocation((old) => ({ ...old, point: next }));
    setError("");
    if (!geoConfig.data?.enabled) {
      setBusy(false);
      setNote(
        "Точка выбрана вручную. Проверьте, что она соответствует введённому адресу.",
      );
      return;
    }
    setBusy(true);
    setNote("");
    try {
      const data = await api<{ item: AddressSuggestion | null }>(
        `/geo/reverse?${new URLSearchParams({ lat: String(next.lat), lon: String(next.lon), lang: "ru" })}`,
        { signal: request.signal },
      );
      if (!request.current()) return;
      const item = data.item && kazakhstanAddresses([data.item])[0];
      if (item) {
        setLocation({ address: item.label, point: next });
        setNote("Адрес обновлён по выбранной точке. Проверьте номер дома.");
      } else
        setNote(
          "Адрес точки не найден. Проверьте введённый адрес или выберите другую точку.",
        );
    } catch {
      if (request.current())
        setNote(
          "Точка выбрана вручную. Поиск адреса недоступен: проверьте введённый адрес.",
        );
    } finally {
      if (request.current()) setBusy(false);
    }
  };
  const locate = async () => {
    const request = reverse.current.start();
    setBusy(true);
    setError("");
    setNote("");
    try {
      const point = await currentPosition();
      if (request.current()) await selectPoint(point);
    } catch (problem) {
      if (request.current()) {
        setError(messageOf(problem));
        setBusy(false);
      }
    }
  };
  return {
    ...location,
    geoConfig,
    busy,
    error,
    note,
    changeAddress,
    selectSuggestion,
    selectPoint,
    locate,
    restoreLocation,
  };
}
