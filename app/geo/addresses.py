"""Server-side Kazakhstan geocoding with bounded requests and an ephemeral cache."""
from __future__ import annotations

import json
import math
import time
from collections import OrderedDict, deque
from datetime import datetime, timezone
from threading import Lock
from typing import Annotated, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request as URLRequest, build_opener

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app.core.config import Settings

router = APIRouter(prefix='/api/v1/geo', tags=['Адреса'])
PROVIDER_BASE = 'https://api.geoapify.com/v1/geocode/'
CACHE_TTL = 300
CACHE_SIZE = 256
MAX_RESPONSE_BYTES = 1_000_000


class AddressSuggestion(BaseModel):
    label: str
    lat: float
    lon: float
    country_code: Literal['kz'] = 'kz'
    city: str | None = None
    street: str | None = None
    housenumber: str | None = None
    postcode: str | None = None


class AddressSearchResponse(BaseModel):
    items: list[AddressSuggestion]


class ReverseResponse(BaseModel):
    item: AddressSuggestion | None


class GeoConfigResponse(BaseModel):
    enabled: bool
    country_code: Literal['kz'] = 'kz'


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward the provider key to another location.
        return None


def _fetch_json(endpoint: str, params: dict) -> dict:
    request = URLRequest(PROVIDER_BASE + endpoint + '?' + urlencode(params),
                         headers={'Accept': 'application/json', 'User-Agent': 'Pitomo/address-search'})
    with build_opener(_NoRedirect()).open(request, timeout=8) as response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError('Provider response exceeds the limit')
    payload = json.loads(raw)
    if not isinstance(payload, dict) or not isinstance(payload.get('results'), list):
        raise ValueError('Invalid provider response')
    return payload


def _text(value: object, limit: int = 200) -> str | None:
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        return None
    return str(value).strip()[:limit] or None


def _suggestions(payload: dict, limit: int) -> list[AddressSuggestion]:
    results = payload.get('results')
    if not isinstance(results, list):
        raise ValueError('Invalid provider response')
    items = []
    for row in results[:20]:
        if not isinstance(row, dict) or str(row.get('country_code', '')).lower() != 'kz':
            continue
        try:
            lat, lon = float(row['lat']), float(row['lon'])
        except (KeyError, ValueError, TypeError, OverflowError):
            continue
        label = _text(row.get('formatted'), 400)
        if not label or not math.isfinite(lat) or not math.isfinite(lon):
            continue
        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            continue
        items.append(AddressSuggestion(label=label, lat=lat, lon=lon,
            city=_text(row.get('city')), street=_text(row.get('street')),
            housenumber=_text(row.get('housenumber')), postcode=_text(row.get('postcode'))))
        if len(items) >= limit:
            break
    return items


class AddressClient:
    """One client per API process. Failed requests also consume the local budget."""

    def __init__(self, settings: Settings):
        self._key = settings.geoapify_api_key
        self._daily_limit = settings.geoapify_daily_limit
        self._cache: OrderedDict[tuple, tuple[float, list[AddressSuggestion]]] = OrderedDict()
        self._recent: deque[float] = deque()
        self._lock = Lock()
        self._day = datetime.now(timezone.utc).date()
        self._used = 0

    @property
    def enabled(self) -> bool:
        return bool(self._key)

    def lookup(self, endpoint: str, params: dict) -> list[AddressSuggestion]:
        if not self.enabled:
            raise HTTPException(503, 'Подсказки адресов пока недоступны. Введите адрес вручную.')
        cache_key = (endpoint, *sorted(params.items()))
        # Serialize provider calls, including duplicate in-flight requests.
        with self._lock:
            now = time.monotonic()
            cached = self._cache.get(cache_key)
            if cached and now - cached[0] < CACHE_TTL:
                self._cache.move_to_end(cache_key)
                return cached[1]
            self._cache.pop(cache_key, None)
            day = datetime.now(timezone.utc).date()
            if day != self._day:
                self._day, self._used = day, 0
            while self._recent and now - self._recent[0] >= 1:
                self._recent.popleft()
            if len(self._recent) >= 5:
                raise HTTPException(429, 'Подождите немного перед следующим поиском.',
                                    headers={'Retry-After': '1'})
            if self._used >= self._daily_limit:
                raise HTTPException(429, 'Сегодня подсказки недоступны. Введите адрес вручную.')
            self._used += 1
            self._recent.append(now)
            try:
                payload = _fetch_json(endpoint, {**params, 'apiKey': self._key, 'format': 'json'})
                items = _suggestions(payload, int(params.get('limit', 1)))
            except HTTPError as exc:
                # Do not expose URLs, keys or provider response bodies.
                if exc.code == 429:
                    raise HTTPException(429, 'Подсказки временно недоступны. Введите адрес вручную.',
                                        headers={'Retry-After': '60'}) from None
                raise HTTPException(503, 'Сервис адресов временно недоступен. Введите адрес вручную.') from None
            except (URLError, TimeoutError, OSError, ValueError, TypeError):
                raise HTTPException(503, 'Сервис адресов временно недоступен. Введите адрес вручную.') from None
            self._cache[cache_key] = (time.monotonic(), items)
            while len(self._cache) > CACHE_SIZE:
                self._cache.popitem(last=False)
            return items


@router.get('/config', response_model=GeoConfigResponse)
def geo_config(request: Request):
    return GeoConfigResponse(enabled=request.app.state.address_client.enabled)


@router.get('/address-search', response_model=AddressSearchResponse)
def address_search(request: Request,
    q: Annotated[str, Query(min_length=3, max_length=200)],
    lang: Literal['ru', 'kk'] = 'ru',
    limit: Annotated[int, Query(ge=1, le=5)] = 5,
):
    query = ' '.join(q.split())
    if len(query) < 3 or any(ord(char) < 32 for char in q):
        raise HTTPException(422, 'Введите хотя бы три символа адреса.')
    items = request.app.state.address_client.lookup('autocomplete', {
        'text': query, 'lang': lang, 'filter': 'countrycode:kz', 'limit': limit,
    })
    return AddressSearchResponse(items=items)


@router.get('/reverse', response_model=ReverseResponse)
def reverse_address(request: Request,
    lat: Annotated[float, Query(ge=-90, le=90, allow_inf_nan=False)],
    lon: Annotated[float, Query(ge=-180, le=180, allow_inf_nan=False)],
    lang: Literal['ru', 'kk'] = 'ru',
):
    # Broad geographic envelope; provider country code is the final country check.
    if not 40 <= lat <= 56 or not 46 <= lon <= 88:
        return ReverseResponse(item=None)
    items = request.app.state.address_client.lookup('reverse', {
        'lat': round(lat, 6), 'lon': round(lon, 6), 'lang': lang, 'limit': 1,
    })
    return ReverseResponse(item=items[0] if items else None)
