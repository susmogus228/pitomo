"""Geocoder boundary checks without sending addresses to an external service."""
from datetime import timedelta
from urllib.error import HTTPError, URLError

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.geo import addresses
from app.main import create_test_app

KEY = 'test-provider-key-never-public'
RESULT = {'country_code': 'kz', 'formatted': 'Алматы, улица Абая, 10',
          'lat': 43.238, 'lon': 76.945, 'city': 'Алматы', 'street': 'Абая', 'housenumber': '10'}


def test_no_key_manual_mode_and_validation():
    with TestClient(create_test_app()) as client:
        assert client.get('/api/v1/geo/config').json() == {'enabled': False, 'country_code': 'kz'}
        assert client.get('/api/v1/geo/address-search?q=Алматы').status_code == 503
        assert client.get('/api/v1/geo/reverse?lat=43.238&lon=76.945').status_code == 503
        for params in ({'q': 'ab'}, {'q': '   '}, {'q': 'abcd', 'lang': 'en'},
                       {'q': 'abcd', 'limit': 6}, {'q': 'a' * 201}, {'q': 'abc\x01'}):
            assert client.get('/api/v1/geo/address-search', params=params).status_code == 422
        for params in ({'lat': 'nan', 'lon': 76}, {'lat': 91, 'lon': 76},
                       {'lat': 43, 'lon': 'inf'}):
            assert client.get('/api/v1/geo/reverse', params=params).status_code == 422


def test_provider_country_filter_mapping_cache_and_key_privacy(monkeypatch, caplog):
    calls = []

    def fake_fetch(endpoint, params):
        calls.append((endpoint, params))
        return {'results': [
            {**RESULT, 'country_code': 'ru'}, {**RESULT, 'lat': 'NaN'},
            {**RESULT, 'formatted': ''}, RESULT,
        ]}

    monkeypatch.setattr(addresses, '_fetch_json', fake_fetch)
    settings = Settings.for_testing(geoapify_api_key=KEY)
    assert KEY not in repr(settings)
    with TestClient(create_test_app(settings=settings)) as client:
        config = client.get('/api/v1/geo/config')
        assert config.json()['enabled'] and KEY not in config.text
        query = {'q': '  Алматы   Абая  ', 'lang': 'kk', 'limit': 3}
        first = client.get('/api/v1/geo/address-search', params=query)
        second = client.get('/api/v1/geo/address-search', params=query)
        assert first.status_code == second.status_code == 200
        assert first.json() == second.json()
        assert first.json()['items'][0]['country_code'] == 'kz'
        assert len(first.json()['items']) == 1 and len(calls) == 1
        assert calls[0] == ('autocomplete', {
            'text': 'Алматы Абая', 'lang': 'kk', 'limit': 3,
            'filter': 'countrycode:kz', 'format': 'json', 'apiKey': KEY,
        })
        assert first.headers['cache-control'] == 'no-store'
        assert KEY not in first.text
    audit = '\n'.join(record.getMessage() for record in caplog.records
                      if record.name == 'petshop.audit')
    assert KEY not in audit and 'Алматы' not in audit


def test_reverse_ignores_non_kazakhstan_and_far_coordinates(monkeypatch):
    calls = []

    def fake_fetch(endpoint, params):
        calls.append((endpoint, params))
        return {'results': [{**RESULT, 'country_code': 'uz'}]}

    monkeypatch.setattr(addresses, '_fetch_json', fake_fetch)
    with TestClient(create_test_app(settings=Settings.for_testing(geoapify_api_key=KEY))) as client:
        assert client.get('/api/v1/geo/reverse?lat=51&lon=71').json() == {'item': None}
        assert calls[0][0] == 'reverse'
        assert client.get('/api/v1/geo/reverse?lat=20&lon=10').json() == {'item': None}
        assert len(calls) == 1


def test_daily_limit_counts_failures_and_resets(monkeypatch):
    def fail(endpoint, params):
        raise URLError('sensitive-address-and-key')

    monkeypatch.setattr(addresses, '_fetch_json', fail)
    adapter = addresses.AddressClient(Settings.for_testing(geoapify_api_key=KEY, geoapify_daily_limit=1))
    with pytest.raises(HTTPException) as error:
        adapter.lookup('autocomplete', {'text': 'one'})
    assert error.value.status_code == 503 and 'sensitive' not in str(error.value.detail)
    with pytest.raises(HTTPException) as error:
        adapter.lookup('autocomplete', {'text': 'two'})
    assert error.value.status_code == 429
    adapter._day -= timedelta(days=1)
    monkeypatch.setattr(addresses, '_fetch_json', lambda endpoint, params: {'results': [RESULT]})
    assert adapter.lookup('autocomplete', {'text': 'three'})[0].label == RESULT['formatted']
    assert adapter._used == 1


def test_cached_calls_skip_rate_and_daily_budget(monkeypatch):
    monkeypatch.setattr(addresses, '_fetch_json', lambda endpoint, params: {'results': [RESULT]})
    adapter = addresses.AddressClient(Settings.for_testing(geoapify_api_key=KEY, geoapify_daily_limit=1))
    for _ in range(8):
        assert adapter.lookup('autocomplete', {'text': 'repeat'})
    assert adapter._used == 1


def test_global_rate_and_bounded_cache(monkeypatch):
    monkeypatch.setattr(addresses, '_fetch_json', lambda endpoint, params: {'results': [RESULT]})
    monkeypatch.setattr(addresses.time, 'monotonic', lambda: 10)
    adapter = addresses.AddressClient(Settings.for_testing(geoapify_api_key=KEY))
    for i in range(5):
        adapter.lookup('autocomplete', {'text': str(i)})
    with pytest.raises(HTTPException) as error:
        adapter.lookup('autocomplete', {'text': 'six'})
    assert error.value.status_code == 429 and error.value.headers['Retry-After'] == '1'
    monkeypatch.setattr(addresses.time, 'monotonic', lambda: 11)
    adapter.lookup('autocomplete', {'text': 'six'})
    monkeypatch.setattr(addresses, 'CACHE_SIZE', 2)
    adapter.lookup('autocomplete', {'text': 'seven'})
    assert len(adapter._cache) == 2


@pytest.mark.parametrize('failure', [
    HTTPError('https://provider.invalid/?apiKey=secret', 429, 'limit', {}, None),
    HTTPError('https://provider.invalid/?apiKey=secret', 403, 'key secret', {}, None),
    TimeoutError('secret'), ValueError('secret'),
])
def test_provider_failures_redacted(monkeypatch, failure):
    def fail(endpoint, params):
        raise failure

    monkeypatch.setattr(addresses, '_fetch_json', fail)
    with TestClient(create_test_app(settings=Settings.for_testing(geoapify_api_key=KEY))) as client:
        response = client.get('/api/v1/geo/address-search?q=Алматы')
        assert response.status_code == (429 if isinstance(failure, HTTPError) and failure.code == 429 else 503)
        assert 'secret' not in response.text and 'apiKey' not in response.text and KEY not in response.text


def test_config_bounds():
    with pytest.raises(ValueError):
        Settings.for_testing(geoapify_daily_limit=3001)
    with pytest.raises(ValueError):
        Settings.for_testing(geoapify_api_key='secret key')
