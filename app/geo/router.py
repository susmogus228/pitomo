"""Bounded OpenStreetMap veterinary search around an explicit user location."""
from __future__ import annotations

import json
import math
import time
from threading import Lock
from typing import Annotated
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix='/api/v1/vets', tags=['Ветклиники'])
OVERPASS_URL = 'https://overpass-api.de/api/interpreter'
TTL_SECONDS = 900
_cache: dict[tuple[float, float, int], tuple[float, dict]] = {}
_cache_lock = Lock()
_recent_fetches: list[float] = []


class VetResponse(BaseModel):
    id: str
    name: str
    lat: float
    lon: float
    distance_m: int
    address: str | None = None
    phone: str | None = None
    website: str | None = None
    emergency: bool | None = None
    opening_hours: str | None = None
    osm_url: str


class NearbyVetsResponse(BaseModel):
    items: list[VetResponse]
    source: str = 'OpenStreetMap'
    attribution: str = '© OpenStreetMap contributors'


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    earth_radius = 6371000
    a = (math.sin(math.radians(lat2 - lat1) / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return round(2 * earth_radius * math.asin(min(1, math.sqrt(a))))


def _optional(value: object, limit: int = 200) -> str | None:
    text = str(value).strip()[:limit] if value is not None else ''
    return text or None


def _fetch(lat: float, lon: float, radius_m: int) -> dict:
    query = (f'[out:json][timeout:10];nwr["amenity"="veterinary"]'
             f'(around:{radius_m},{lat:.7f},{lon:.7f});out center 100;')
    request = Request(OVERPASS_URL, data=query.encode('utf-8'),
                      headers={'Content-Type': 'text/plain; charset=utf-8',
                               'User-Agent': 'Pitomo/0.9 veterinary-search'}, method='POST')
    with urlopen(request, timeout=10) as response:
        raw = response.read(1_000_001)
    if len(raw) > 1_000_000:
        raise ValueError('Overpass response too large')
    payload = json.loads(raw)
    if not isinstance(payload, dict) or not isinstance(payload.get('elements'), list):
        raise ValueError('Invalid Overpass response')
    return payload


def _map_elements(payload: dict, lat: float, lon: float, radius_m: int) -> list[dict]:
    result = []
    for element in payload['elements'][:100]:
        if not isinstance(element, dict) or element.get('type') not in {'node', 'way', 'relation'}:
            continue
        point = element if element['type'] == 'node' else element.get('center') or {}
        try:
            item_lat, item_lon = float(point['lat']), float(point['lon'])
            if not math.isfinite(item_lat) or not math.isfinite(item_lon):
                continue
            distance = _distance_m(lat, lon, item_lat, item_lon)
            osm_id = int(element['id'])
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if distance > radius_m or not (-90 <= item_lat <= 90 and -180 <= item_lon <= 180):
            continue
        tags = element.get('tags') or {}
        if not isinstance(tags, dict):
            tags = {}
        name = _optional(tags.get('name'), 160) or 'Ветеринарная клиника'
        address = _optional(', '.join(str(tags[key]).strip() for key in (
            'addr:street', 'addr:housenumber', 'addr:city') if tags.get(key)), 300)
        website = _optional(tags.get('website') or tags.get('contact:website'), 500)
        if website and (urlsplit(website).scheme not in {'http', 'https'} or not urlsplit(website).netloc):
            website = None
        result.append({'id': f"{element['type']}:{osm_id}", 'name': name,
                       'lat': item_lat, 'lon': item_lon, 'distance_m': distance,
                       'address': address, 'phone': _optional(tags.get('phone') or tags.get('contact:phone'), 50),
                       'website': website, 'emergency': (
                           True if tags.get('emergency') == 'yes' else
                           False if tags.get('emergency') == 'no' else None),
                       'opening_hours': _optional(tags.get('opening_hours'), 200),
                       'osm_url': f"https://www.openstreetmap.org/{element['type']}/{osm_id}"})
    result.sort(key=lambda item: (item['distance_m'], item['id']))
    return result


@router.get('/nearby', response_model=NearbyVetsResponse, summary='Найти ближайшие ветклиники')
def nearby_vets(lat: Annotated[float, Query(ge=-90, le=90, allow_inf_nan=False)],
                lon: Annotated[float, Query(ge=-180, le=180, allow_inf_nan=False)],
                radius_m: Annotated[int, Query(ge=500, le=20000)] = 5000):
    key = (round(lat, 4), round(lon, 4), radius_m)
    now = time.monotonic()
    with _cache_lock:
        cached = _cache.get(key)
        if cached and cached[0] > now:
            payload = cached[1]
        else:
            payload = None
    if payload is None:
        with _cache_lock:
            _recent_fetches[:] = [stamp for stamp in _recent_fetches if now - stamp < 10]
            if len(_recent_fetches) >= 8:
                raise HTTPException(status_code=429, detail='Слишком много запросов к поиску ветклиник',
                                    headers={'Retry-After': '10'})
            _recent_fetches.append(now)
        try:
            # Coordinates rounded to 4 decimals may differ by ~8 m across a
            # cache key. Fetch a small margin, then filter at the exact point.
            payload = _fetch(lat, lon, radius_m + 20)
        except Exception as exc:
            raise HTTPException(status_code=503, detail='Поиск ветклиник временно недоступен') from exc
        with _cache_lock:
            if len(_cache) >= 128:
                _cache.pop(next(iter(_cache)))
            _cache[key] = (time.monotonic() + TTL_SECONDS, payload)
    return {'items': _map_elements(payload, lat, lon, radius_m),
            'source': 'OpenStreetMap', 'attribution': '© OpenStreetMap contributors'}
