"""Review trust, report ownership, moderation and public projection regressions."""
from io import BytesIO
import csv

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from app.core.config import Settings
from app.main import create_test_app
from tests.helpers import admin_headers
from tests.test_v090_features import customer
from tests.test_v010_features import _received_review


@pytest.fixture
def client(tmp_path):
    with TestClient(create_test_app(settings=Settings.for_testing(
            review_upload_dir=str(tmp_path/'uploads')))) as value:
        yield value


def photo(client, path, headers):
    image = BytesIO()
    Image.new('RGB', (10, 10), 'blue').save(image, 'PNG')
    response = client.post(path+'/photos', headers=headers,
                           files={'file':('review.png', image.getvalue(), 'image/png')})
    assert response.status_code == 201, response.text
    return response.json()['url']


def test_purchase_and_edit_badges_are_server_derived(client):
    owner = customer(client)
    review, purchase = _received_review(client, owner)
    path = f"/api/v1/products/2/reviews/{review['id']}"
    assert review['verified_purchase'] is True
    assert review['is_edited'] is False
    assert client.patch(path, headers=owner, json={'verified_purchase':True}).status_code == 422
    unchanged = client.patch(path, headers=owner, json={'body':review['body']}).json()
    assert unchanged['is_edited'] is False
    changed = client.patch(path, headers=owner, json={'rating':4}).json()
    assert changed['is_edited'] is True and changed['edited_at']
    assert changed['verified_purchase'] is True
    assert 'order_id' not in changed
    mine = client.get('/api/v1/products/2/reviews/mine', headers=owner)
    assert mine.status_code == 200 and mine.json()['id'] == review['id']
    assert client.get('/api/v1/products/2/reviews/mine').status_code == 401
    assert client.get('/api/v1/orders/'+str(purchase['id']), headers=owner).json()['received_at']


def test_distribution_sort_and_photo_filter(client):
    first = customer(client)
    second = customer(client, 'second-review@example.test')
    high, _ = _received_review(client, first)
    low, _ = _received_review(client, second)
    path = f"/api/v1/products/2/reviews/{low['id']}"
    assert client.patch(path, headers=second, json={'rating':2}).status_code == 200
    photo(client, path, second)
    page = client.get('/api/v1/products/2/reviews?sort=rating_asc&limit=1').json()
    assert page['total'] == 2 and page['items'][0]['id'] == low['id']
    assert page['rating_distribution'] == {'1':0,'2':1,'3':0,'4':0,'5':1}
    assert page['average_rating'] == 3.5
    filtered = client.get('/api/v1/products/2/reviews?with_photos=true&rating=2').json()
    assert filtered['total'] == 1 and filtered['items'][0]['id'] == low['id']
    assert filtered['summary_total'] == 2
    assert filtered['rating_distribution'] == page['rating_distribution']
    assert client.get('/api/v1/products/2/reviews?sort=rating_desc').json()['items'][0]['id'] == high['id']
    assert client.get('/api/v1/products/2/reviews?sort=unknown').status_code == 422
    assert client.get('/api/v1/products/2/reviews?rating=6').status_code == 422


def test_report_does_not_hide_and_reports_are_private(client):
    owner = customer(client)
    reporter = customer(client, 'reporter@example.test')
    admin = admin_headers(client)
    review, _ = _received_review(client, owner)
    path = f"/api/v1/products/2/reviews/{review['id']}/reports"
    data = {'reason':'spam','details':'Пожалуйста, проверьте содержание.'}
    assert client.post(path, json=data).status_code == 401
    assert client.post(path, headers=owner, json=data).status_code == 422
    sent = client.post(path, headers=reporter, json=data)
    assert sent.status_code == 201, sent.text
    duplicate = client.post(path, headers=reporter, json=data)
    assert duplicate.status_code == 200 and duplicate.json()['id'] == sent.json()['id']
    assert client.get('/api/v1/products/2/reviews').json()['total'] == 1
    assert client.get('/api/v1/admin/review-reports', headers=reporter).status_code == 403
    queue = client.get('/api/v1/admin/review-reports', headers=admin).json()
    assert queue['total'] == 1 and queue['items'][0]['review_id'] == review['id']
    assert 'email' not in str(queue)


def test_hide_restore_protects_rating_media_and_creates_journal(client):
    owner = customer(client)
    reporter = customer(client, 'moderation-reporter@example.test')
    admin = admin_headers(client)
    review, purchase = _received_review(client, owner)
    path = f"/api/v1/products/2/reviews/{review['id']}"
    media = photo(client, path, owner)
    assert client.get(media).status_code == 200
    assert client.post(path+'/reports', headers=reporter, json={'reason':'abuse'}).status_code == 201
    moderation = f"/api/v1/admin/reviews/{review['id']}/moderation"
    assert client.post(moderation, headers=reporter, json={'action':'hide','reason':'Проверено'}).status_code == 403
    assert client.post(moderation, headers=admin, json={'action':'hide','reason':''}).status_code == 422
    hidden = client.post(moderation, headers=admin, json={'action':'hide','reason':'Нарушение правил отзывов'})
    assert hidden.status_code == 200, hidden.text
    assert client.get('/api/v1/products/2/reviews').json()['total'] == 0
    product = client.get('/api/v1/products/2').json()
    assert product['rating_count'] == 0 and product['rating_average'] is None
    assert client.get(media).status_code == 404
    mine = client.get('/api/v1/products/2/reviews/mine', headers=owner).json()
    assert mine['is_hidden'] is True
    assert client.patch(path, headers=owner, json={'body':'Попытка обойти модерацию'}).status_code in (404,409)
    assert client.delete(path, headers=owner).status_code in (404,409)
    assert client.post('/api/v1/products/2/reviews', headers=owner,
                       json={'order_id':purchase['id'],'rating':5,'body':'Попытка создать отзыв заново'}).status_code == 409
    queue = client.get('/api/v1/admin/review-reports', headers=admin).json()
    assert queue['total'] == 0
    assert client.post(moderation, headers=admin, json={'action':'restore','reason':'Повторная проверка'}).status_code == 200
    assert client.get('/api/v1/products/2/reviews').json()['total'] == 1
    assert client.get(media).status_code == 200
    events = client.get(moderation, headers=admin).json()['items']
    assert [event['action'] for event in events] == ['restore','hide']
    assert client.get(moderation, headers=owner).status_code == 403


def test_dismiss_report_keeps_review_and_closes_queue(client):
    owner = customer(client)
    reporter = customer(client, 'dismiss-reporter@example.test')
    admin = admin_headers(client)
    review, _ = _received_review(client, owner)
    path = f"/api/v1/products/2/reviews/{review['id']}"
    assert client.post(path+'/reports', headers=reporter, json={'reason':'other'}).status_code == 201
    moderation = f"/api/v1/admin/reviews/{review['id']}/moderation"
    assert client.post(moderation, headers=admin, json={'action':'dismiss_reports','reason':'Нарушений нет'}).status_code == 200
    assert client.get('/api/v1/admin/review-reports', headers=admin).json()['total'] == 0
    assert client.get('/api/v1/products/2/reviews').json()['total'] == 1


def test_admin_visibility_export_matches_queue(client):
    owner = customer(client)
    other = customer(client, 'export-review@example.test')
    admin = admin_headers(client)
    hidden, _ = _received_review(client, owner)
    public, _ = _received_review(client, other)
    assert client.post(f"/api/v1/admin/reviews/{hidden['id']}/moderation", headers=admin,
                       json={'action':'hide','reason':'Модерация'}).status_code == 200
    for visibility, expected in [('hidden', hidden['id']), ('visible', public['id'])]:
        page = client.get('/api/v1/admin/reviews?visibility='+visibility, headers=admin).json()
        assert [item['id'] for item in page['items']] == [expected]
        export = client.get('/api/v1/admin/exports/reviews?format=csv&visibility='+visibility, headers=admin)
        assert export.status_code == 200, export.text
        rows = list(csv.DictReader(export.content.decode('utf-8-sig').splitlines()))
        assert [int(row['id']) for row in rows] == [expected]
        assert 'hidden_at' in rows[0] and 'edited_at' in rows[0]
