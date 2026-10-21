import { useEffect, useId, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { VetClinic } from "./types";
import type { GeoPoint } from "./geo";

interface Props {
  center: GeoPoint;
  selected?: GeoPoint | null;
  clinics?: VetClinic[];
  onSelect?: (point: GeoPoint) => void;
  disabled?: boolean;
  zoom?: number;
  label: string;
}

export function MapView({
  center,
  selected,
  clinics = [],
  onSelect,
  disabled = false,
  zoom = 12,
  label,
}: Props) {
  const element = useRef<HTMLDivElement>(null);
  const id = useId();
  const map = useRef<L.Map | null>(null);
  const pin = useRef<L.CircleMarker | null>(null);
  const clinicLayer = useRef<L.LayerGroup | null>(null);
  const selectRef = useRef(onSelect);
  selectRef.current = disabled ? undefined : onSelect;

  useEffect(() => {
    if (!element.current) return;
    const instance = L.map(element.current, { scrollWheelZoom: false }).setView(
      [center.lat, center.lon],
      zoom,
    );
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>',
      maxZoom: 19,
    }).addTo(instance);
    instance.on("click", (event: L.LeafletMouseEvent) => {
      selectRef.current?.({ lat: event.latlng.lat, lon: event.latlng.lng });
    });
    clinicLayer.current = L.layerGroup().addTo(instance);
    map.current = instance;
    const timer = window.setTimeout(() => instance.invalidateSize(), 100);
    return () => {
      window.clearTimeout(timer);
      map.current = null;
      pin.current = null;
      clinicLayer.current = null;
      instance.remove();
    };
  }, []);

  useEffect(() => {
    map.current?.setView([center.lat, center.lon], zoom);
  }, [center.lat, center.lon, zoom]);

  useEffect(() => {
    if (!map.current) return;
    pin.current?.remove();
    pin.current = selected
      ? L.circleMarker([selected.lat, selected.lon], {
          radius: 10,
          color: "#fff",
          weight: 3,
          fillColor: "#3457eb",
          fillOpacity: 1,
        })
          .addTo(map.current)
          .bindTooltip("Выбранная точка")
      : null;
  }, [selected?.lat, selected?.lon]);

  useEffect(() => {
    const layer = clinicLayer.current;
    if (!layer) return;
    layer.clearLayers();
    for (const clinic of clinics) {
      if (!Number.isFinite(clinic.lat) || !Number.isFinite(clinic.lon))
        continue;
      const content = document.createElement("span");
      content.textContent = clinic.name;
      L.circleMarker([clinic.lat, clinic.lon], {
        radius: 8,
        color: "#1d332a",
        weight: 2,
        fillColor: "#fff",
        fillOpacity: 1,
      })
        .bindPopup(content)
        .addTo(layer);
    }
  }, [clinics]);

  return (
    <div>
      {onSelect && (
        <p className="form-note" id={`${id}-help`}>
          Для выбора с клавиатуры перейдите на карту, переместите её стрелками и
          нажмите «Выбрать центр карты». Масштаб меняется клавишами + и −.
        </p>
      )}
      <div
        className="map-view"
        ref={element}
        role="region"
        aria-label={label}
        aria-describedby={onSelect ? `${id}-help` : undefined}
      />
      {onSelect && (
        <button
          type="button"
          className="button outline"
          disabled={disabled}
          style={{ marginTop: 12 }}
          onClick={() => {
            const current = map.current?.getCenter();
            if (current)
              selectRef.current?.({ lat: current.lat, lon: current.lng });
          }}
        >
          Выбрать центр карты
        </button>
      )}
    </div>
  );
}
