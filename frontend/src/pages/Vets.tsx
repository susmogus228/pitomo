import { useState } from "react";
import { Breadcrumbs, ErrorNotice, Loading, PageTitle } from "../components";
import { DEFAULT_MAP_CENTER } from "../geo";
import { MapView } from "../MapView";
import { AddressSearch } from "../AddressSearch";
import { useAddressLocation } from "../useAddressLocation";
import type { NearbyVets } from "../types";
import { useResource } from "../useResource";

function safeWebsite(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
  } catch { return null; }
}

export default function Vets() {
  const address = useAddressLocation();
  const point = address.point;
  const [radius, setRadius] = useState(5000);
  const vets = useResource<NearbyVets>(point ? `/vets/nearby?lat=${point.lat}&lon=${point.lon}&radius_m=${radius}` : null);
  return <>
    <Breadcrumbs items={[{ label: "Ветклиники рядом" }]} />
    <PageTitle eyebrow="Помощь поблизости" subtitle="Найдите ветеринарные клиники возле выбранной точки.">Ветклиники рядом</PageTitle>
    <div className="vets-intro"><p>Введите адрес в Казахстане, выберите точку на карте или определите местоположение. Браузер запросит доступ только после нажатия кнопки. Расстояние указано по прямой, часы работы уточняйте в клинике.</p>
      <button type="button" className="button" disabled={address.busy} onClick={() => void address.locate()}>{address.busy ? "Определяем…" : "Найти рядом со мной"}</button></div>
    <ErrorNotice message={address.error} />
    <div className="vets-layout">
      <section className="vets-map-panel" aria-label="Карта ветклиник">
        <AddressSearch value={address.address} onChange={address.changeAddress} onSelect={address.selectSuggestion} enabled={address.geoConfig.data?.enabled === true} configLoading={address.geoConfig.loading} label="Найти клиники рядом с адресом" />
        <MapView label="Карта ветклиник и выбора местоположения" center={point || DEFAULT_MAP_CENTER} selected={point} clinics={vets.data?.items || []} onSelect={(next) => void address.selectPoint(next)} zoom={point ? 12 : 5} />
        {address.note && <p className="form-note delivery-point-note" role="status">{address.note}</p>}
        <p className="form-note">Данные карты и клиник: © OpenStreetMap contributors. Сведения могут быть неполными.</p>
      </section>
      <section className="vets-results" aria-labelledby="vets-results-title">
        <div className="vets-results-head"><h2 id="vets-results-title">Клиники рядом</h2>
          <label className="field"><span>Радиус поиска</span><select value={radius} onChange={(event) => setRadius(Number(event.target.value))}>
            <option value={3000}>3 км</option><option value={5000}>5 км</option><option value={10000}>10 км</option><option value={20000}>20 км</option>
          </select></label>
        </div>
        {!point ? <p className="form-note">Выберите точку, чтобы начать поиск.</p> : vets.loading ? <Loading text="Ищем клиники…" /> : vets.error ? <ErrorNotice message={vets.error} retry={vets.reload} /> : vets.data?.items.length ?
          <ol className="vets-list">{vets.data.items.map((clinic) => <li key={clinic.id}>
            <div className="vet-title"><h3>{clinic.name}</h3><strong>{clinic.distance_m < 1000 ? `${Math.round(clinic.distance_m)} м` : `${(clinic.distance_m / 1000).toFixed(1)} км`}</strong></div>
            {clinic.address && <p>{clinic.address}</p>}
            {clinic.emergency && <p className="vet-emergency">Экстренная помощь — уточните перед визитом</p>}
            <div className="vet-links">
              {clinic.phone && <a href={`tel:${clinic.phone.replace(/[^+\d]/g, "")}`}>Позвонить</a>}
              {safeWebsite(clinic.website) && <a href={safeWebsite(clinic.website)!} target="_blank" rel="noopener noreferrer">Сайт ↗</a>}
              <a href={`https://www.openstreetmap.org/?mlat=${clinic.lat}&mlon=${clinic.lon}#map=17/${clinic.lat}/${clinic.lon}`} target="_blank" rel="noopener noreferrer">Открыть на карте ↗</a>
            </div>
          </li>)}</ol>
          : <p className="form-note">В выбранном радиусе клиник не найдено. Увеличьте радиус или выберите другую точку.</p>}
      </section>
    </div>
  </>;
}
