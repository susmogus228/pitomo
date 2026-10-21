"""Role, ownership, media, rating and stock audit regression checks."""
from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from app.core.config import Settings
from app.main import create_test_app
from app.db.models import ProductVariantORM, ReviewPhotoORM
from tests.helpers import admin_headers
from tests.test_v090_features import customer, order


def _received_review(client, owner):
    purchase = order(client, owner, payment='cod', quantity=1)
    assert client.post(f"/api/v1/orders/{purchase['id']}/confirm-receipt", headers=owner).status_code == 200
    response = client.post('/api/v1/products/2/reviews', headers=owner,
        json={'order_id': purchase['id'], 'rating': 5, 'body': 'Корм хороший, доставка удобная.'})
    assert response.status_code == 201, response.text
    return response.json(), purchase


def test_review_edit_reply_pin_delete_rating_and_admin_guard(tmp_path):
    settings = Settings.for_testing(review_upload_dir=str(tmp_path / 'reviews'))
    with TestClient(create_test_app(settings=settings)) as client:
        owner = customer(client)
        other = customer(client, 'v010-other@example.com')
        admin = admin_headers(client)
        review, purchase = _received_review(client, owner)
        path = f"/api/v1/products/2/reviews/{review['id']}"
        assert client.get('/api/v1/products/2').json()['rating_average'] == 5.0
        assert client.get('/api/v1/products/2').json()['rating_count'] == 1
        assert client.get('/api/v1/products', params={'page_size': 5}).json()['items'][1]['rating_count'] == 1
        assert client.patch(path, json={'body': 'Это чужой отзыв.'}, headers=other).status_code == 403
        assert client.delete(path, headers=other).status_code == 403
        assert client.patch(path, json={'body': None}, headers=owner).status_code == 422
        assert client.patch(path, json={'rating': 4}, headers=owner).json()['rating'] == 4
        assert client.get('/api/v1/products/2').json()['rating_average'] == 4.0
        assert client.post(f'{path}/replies', json={'body': 'Официальный ответ', 'official': True},
                           headers=other).status_code == 403
        reply = client.post(f'{path}/replies', json={'body': 'А у вас как?', 'parent_reply_id': None},
                            headers=other)
        assert reply.status_code == 201, reply.text
        reply_id = reply.json()['id']
        assert client.patch(f'{path}/replies/{reply_id}', json={'body': 'Чужая правка'},
                            headers=owner).status_code == 403
        nested = client.post(f'{path}/replies', json={'body': 'Ответ', 'parent_reply_id': reply_id},
                             headers=owner)
        assert nested.status_code == 201
        assert client.post(f'{path}/replies', json={'body': 'Слишком глубоко',
            'parent_reply_id': nested.json()['id']}, headers=owner).status_code == 422
        second_review, _ = _received_review_for_other_product(client, owner)
        assert client.post(f'{path}/replies', json={'body': 'Не тот отзыв',
            'parent_reply_id': second_review['reply_id']}, headers=owner).status_code == 404
        official = client.post(f'{path}/replies', json={'body': 'Спасибо за отзыв!', 'official': True},
                               headers=admin)
        assert official.status_code == 201 and official.json()['is_pinned']
        assert client.post(f'{path}/replies', json={'body': 'Ещё один', 'official': True},
                           headers=admin).status_code == 409
        followup = client.post(f'{path}/replies', json={'body': 'Подскажем подробнее',
            'parent_reply_id': reply_id, 'official': True}, headers=admin)
        assert followup.status_code == 201
        assert followup.json()['is_official'] and not followup.json()['is_pinned']
        page = client.get('/api/v1/products/2/reviews').json()
        assert page['items'][0]['replies'][0]['id'] == official.json()['id']
        assert client.get('/api/v1/admin/dashboard').status_code == 401
        assert client.get('/api/v1/admin/dashboard', headers=owner).status_code == 403
        assert client.get('/api/v1/admin/reviews', headers=owner).status_code == 403
        assert any(item['id'] == review['id'] and item['has_official_reply']
                   for item in client.get('/api/v1/admin/reviews', headers=admin).json()['items'])
        assert client.delete(f'{path}/replies/{reply_id}', headers=other).status_code == 204
        assert any(reply['id'] == reply_id and reply['is_deleted']
                   for reply in client.get('/api/v1/products/2/reviews').json()['items'][0]['replies'])
        assert client.delete(path, headers=owner).status_code == 204
        assert client.get('/api/v1/products/2').json()['rating_count'] == 0
        assert client.get('/api/v1/products/2/reviews').json()['total'] == 0
        recreated = client.post('/api/v1/products/2/reviews', headers=owner,
            json={'order_id': purchase['id'], 'rating': 5, 'body': 'Обновлённый отзыв после удаления.'})
        assert recreated.status_code == 201, recreated.text
        assert client.get('/api/v1/products/2').json()['rating_count'] == 1


def _received_review_for_other_product(client, owner):
    purchase = order(client, owner, payment='cod', quantity=1, variant_id=30)
    assert client.post(f"/api/v1/orders/{purchase['id']}/confirm-receipt", headers=owner).status_code == 200
    response = client.post('/api/v1/products/3/reviews', headers=owner,
        json={'order_id': purchase['id'], 'rating': 5, 'body': 'Ещё один хороший товар.'})
    assert response.status_code == 201, response.text
    review = response.json()
    reply = client.post(f"/api/v1/products/3/reviews/{review['id']}/replies",
                        headers=owner, json={'body': 'Вторая ветка'})
    assert reply.status_code == 201
    return {'id': review['id'], 'reply_id': reply.json()['id']}, purchase


def test_photo_validation_ownership_and_storage(tmp_path):
    upload_dir = tmp_path / 'review-media'
    settings = Settings.for_testing(review_upload_dir=str(upload_dir))
    with TestClient(create_test_app(settings=settings)) as client:
        owner = customer(client)
        other = customer(client, 'v010-photo-other@example.com')
        review, _ = _received_review(client, owner)
        path = f"/api/v1/products/2/reviews/{review['id']}/photos"
        img = Image.new('RGB', (40, 40), (255, 0, 0))
        image_bytes = BytesIO()
        img.save(image_bytes, format='PNG')
        payload = image_bytes.getvalue()
        assert client.post(path, files={'file': ('x.png', payload, 'image/png')}, headers=other).status_code == 403
        assert client.post(path, files={'file': ('x.png', b'not png', 'image/png')}, headers=owner).status_code == 422
        assert client.post(path, files={'file': ('x.png', b'x' * (5 * 1024 * 1024 + 1), 'image/png')}, headers=owner).status_code == 413
        uploaded = [client.post(path, files={'file': ('x.png', payload, 'image/png')}, headers=owner)
                    for _ in range(3)]
        assert all(result.status_code == 201 for result in uploaded), [result.text for result in uploaded]
        assert all(result.json()['url'].startswith('/media/reviews/') for result in uploaded)
        for item in uploaded:
            filename = item.json()['url'].split('/')[-1]
            with Image.open(upload_dir / filename) as stored:
                assert stored.format == 'WEBP'
        assert client.post(path, files={'file': ('x.png', payload, 'image/png')}, headers=owner).status_code == 409
        first = uploaded[0].json()
        served = client.get(first['url'])
        assert served.status_code == 200 and served.headers['content-type'] == 'image/webp'
        assert client.get('/media/reviews/not-a-photo.webp').status_code == 404
        assert client.delete(f"{path}/{first['id']}", headers=other).status_code == 403
        assert client.delete(f"{path}/{first['id']}", headers=owner).status_code == 204
        assert client.get(first['url']).status_code == 404
        assert not (upload_dir / first['url'].split('/')[-1]).exists()
        with client.app.state.database.session_factory() as session:
            assert session.scalar(select(ReviewPhotoORM.deleted_at).where(
                ReviewPhotoORM.id == first['id'])) is not None


def test_replenishment_is_admin_only_atomic_and_audited():
    with TestClient(create_test_app()) as client:
        customer_headers = customer(client)
        admin = admin_headers(client)
        path = '/api/v1/admin/variants/20/replenishments'
        body = {'quantity': 7, 'reason': 'Тестовое поступление'}
        assert client.post(path, json=body).status_code == 401
        assert client.post(path, json=body, headers=customer_headers).status_code == 403
        assert client.post(path, json={'quantity': 0, 'reason': 'Тест'}, headers=admin).status_code == 422
        assert client.post('/api/v1/admin/variants/999999/replenishments', json=body,
                           headers=admin).status_code == 404
        with client.app.state.database.session_factory() as session:
            before = session.get(ProductVariantORM, 20).stock
        first = client.post(path, json=body, headers=admin)
        second = client.post(path, json=body, headers=admin)
        assert first.status_code == second.status_code == 201, (first.text, second.text)
        assert first.json()['stock_before'] == before
        assert first.json()['product_name'] and first.json()['variant_label'] and first.json()['sku']
        assert second.json()['stock_before'] == before + 7
        assert client.get('/api/v1/products/2').json()['variants'][0]['stock'] == before + 14
        history = client.get('/api/v1/admin/replenishments', headers=admin).json()
        assert history['total'] == 2 and history['items'][0]['reason'] == body['reason']
        assert client.get('/api/v1/admin/replenishments', headers=customer_headers).status_code == 403
