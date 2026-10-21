export interface GeoPoint {
  lat: number;
  lon: number;
}

export const DEFAULT_MAP_CENTER: GeoPoint = { lat: 48.0196, lon: 66.9237 };

export function validPoint(point: GeoPoint): boolean {
  return Number.isFinite(point.lat) && Number.isFinite(point.lon) &&
    point.lat >= -90 && point.lat <= 90 && point.lon >= -180 && point.lon <= 180;
}

export function roundedPoint(point: GeoPoint): GeoPoint {
  return { lat: Number(point.lat.toFixed(7)), lon: Number(point.lon.toFixed(7)) };
}

export function currentPosition(): Promise<GeoPoint> {
  if (!navigator.geolocation) {
    return Promise.reject(new Error("Ваш браузер не поддерживает геолокацию. Выберите точку на карте."));
  }
  return new Promise((resolve, reject) => {
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => resolve({ lat: coords.latitude, lon: coords.longitude }),
      (error) => reject(new Error(error.code === 1
        ? "Доступ к геолокации отклонён. Выберите точку на карте."
        : "Не удалось определить местоположение. Выберите точку на карте.")),
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 },
    );
  });
}
