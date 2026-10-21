"""Product gallery transactions, pixel validation and admin access boundaries."""
from io import BytesIO
import json
from unittest.mock import patch

from fastapi.testclient import TestClient
from fastapi import HTTPException, UploadFile
from PIL import Image
import pytest
from sqlalchemy import func, select
from starlette.datastructures import Headers

from app.catalog import media
from app.core.config import Settings
from app.db.models import ProductORM, ProductPhotoORM, UserORM
from app.main import create_test_app
from tests.helpers import admin_headers
from tests import test_postgresql as pg_support

pg_empty = pg_support.pg_empty


def image_bytes(format='PNG', size=(40, 40)):
    with Image.new('RGB', size, (120, 90, 210)) as image:
        output = BytesIO()
        if format == 'JPEG':
            exif = Image.Exif()
            exif[270] = 'private camera note'
            image.save(output, format=format, exif=exif)
        else:
            image.save(output, format=format)
    return output.getvalue()


def payload(sku='PHOTO-NEW'):
    return {'name': 'Товар с фото', 'pet_type': 'cat', 'brand': 'Питомо',
            'category': 'food', 'composition': 'Мясо и рис',
            'variants': [{'sku': sku, 'label': '500 г', 'price': '1000', 'stock': 3}]}


@pytest.fixture
def client(tmp_path):
    app = create_test_app(settings=Settings.for_testing(review_upload_dir=str(tmp_path / 'uploads')))
    with TestClient(app) as client:
        yield client


def photo_folder(client):
    from pathlib import Path
    return Path(client.app.state.settings.review_upload_dir) / 'products'


def upload(client, admin, product=2):
    return client.post(f'/api/v1/products/{product}/photos', headers=admin,
                       files={'file': ('../camera.jpg', image_bytes('JPEG'), 'image/jpeg')})


def test_gallery_cover_list_update_and_file_deletion(client):
    admin = admin_headers(client)
    first = upload(client, admin)
    assert first.status_code == 201, first.text
    first = first.json()
    assert first['image_url'] == first['images'][0]['url']
    second = upload(client, admin).json()
    assert len(second['images']) == 2 and second['image_url'] == first['image_url']
    photo = second['images'][1]
    cover = client.patch(f"/api/v1/products/2/photos/{photo['id']}/cover", headers=admin)
    assert cover.status_code == 200 and cover.json()['image_url'] == photo['url']
    detail = client.get('/api/v1/products/2').json()
    listed = next(row for row in client.get('/api/v1/products').json()['items'] if row['id'] == 2)
    assert listed['images'] == detail['images'] == second['images']
    updated = client.patch('/api/v1/products/2', json={'name': 'Новое имя'}, headers=admin).json()
    assert updated['images'] == detail['images'] and updated['image_url'] == photo['url']
    for row in detail['images']:
        stored = client.get(row['url'])
        assert stored.status_code == 200 and stored.headers['content-type'] == 'image/webp'
        with Image.open(BytesIO(stored.content)) as image:
            assert image.format == 'WEBP' and not image.getexif() and 'exif' not in image.info
    deleted = client.delete(f"/api/v1/products/2/photos/{photo['id']}", headers=admin)
    assert deleted.status_code == 200 and deleted.json()['image_url'] == first['image_url']
    assert client.get(photo['url']).status_code == 404
    first_photo = first['images'][0]
    final = client.delete(f"/api/v1/products/2/photos/{first_photo['id']}", headers=admin)
    assert final.json()['images'] == [] and final.json()['image_url'] is None
    assert not list(photo_folder(client).glob('*'))


def test_uploaded_product_png_preserves_transparent_pixels(client):
    buffer = BytesIO()
    Image.new('RGBA', (40, 40), (180, 80, 30, 0)).save(buffer, format='PNG')
    response = client.post('/api/v1/products/2/photos', headers=admin_headers(client),
        files={'file': ('transparent.png', buffer.getvalue(), 'image/png')})
    assert response.status_code == 201
    stored = client.get(response.json()['images'][0]['url'])
    with Image.open(BytesIO(stored.content)) as image:
        assert image.mode == 'RGBA'
        assert image.getchannel('A').getextrema() == (0, 0)


def test_invalid_multipart_payload_does_not_echo_input(client):
    data = {**payload(), 'unexpected': 'private-value-in-unexpected-field'}
    result = client.post('/api/v1/products/with-photos', headers=admin_headers(client),
        data={'data': json.dumps(data)}, files={'files': ('valid.png', image_bytes(), 'image/png')})
    assert result.status_code == 422
    assert 'private-value-in-unexpected-field' not in result.text


def test_with_photos_creates_product_and_images_together(client):
    admin = admin_headers(client)
    created = client.post('/api/v1/products/with-photos', headers=admin,
                          data={'data': json.dumps(payload())}, files=[
                              ('files', ('one.png', image_bytes(), 'image/png')),
                              ('files', ('two.jpg', image_bytes('JPEG'), 'image/jpeg'))])
    assert created.status_code == 201, created.text
    body = created.json()
    assert len(body['images']) == 2 and body['image_url'] == body['images'][0]['url']
    assert client.get(f"/api/v1/products/{body['id']}").json()['images'] == body['images']
    plain = client.post('/api/v1/products', headers=admin, json=payload('PHOTO-PLAIN'))
    assert plain.status_code == 201 and plain.json()['images'] == []


@pytest.mark.parametrize('format,mime', [('PNG', 'image/png'), ('JPEG', 'image/jpeg'), ('WEBP', 'image/webp')])
def test_supported_formats_reencode_to_webp(client, format, mime):
    admin = admin_headers(client)
    response = client.post('/api/v1/products/2/photos', headers=admin,
                           files={'file': ('any-name', image_bytes(format), mime)})
    assert response.status_code == 201, response.text
    assert response.json()['images'][0]['url'].endswith('.webp')


@pytest.mark.parametrize('bytes,mime,expected', [
    (b'not an image', 'image/png', 422),
    (b'<svg></svg>', 'image/svg+xml', 422),
    (b'x' * (5 * 1024 * 1024 + 1), 'image/png', 413),
], ids=['fake-png', 'svg', 'over-5mib'])
def test_bad_files_do_not_leave_rows_or_files(client, bytes, mime, expected):
    admin = admin_headers(client)
    response = client.post('/api/v1/products/2/photos', headers=admin,
                           files={'file': ('bad', bytes, mime)})
    assert response.status_code == expected, response.text
    assert client.get('/api/v1/products/2').json()['images'] == []
    assert not list(photo_folder(client).glob('*'))


def test_pixel_limit(client):
    admin = admin_headers(client)
    response = client.post('/api/v1/products/2/photos', headers=admin,
                           files={'file': ('large.png', image_bytes(size=(4001, 3000)), 'image/png')})
    assert response.status_code == 422
    assert not list(photo_folder(client).glob('*'))


def test_atomic_create_invalid_photo_duplicate_sku_and_bad_data(client):
    admin = admin_headers(client)
    with client.app.state.database.session_factory() as session:
        before = session.scalar(select(func.count(ProductORM.id)))
    invalid = client.post('/api/v1/products/with-photos', headers=admin,
                          data={'data': json.dumps(payload())}, files=[
                              ('files', ('good.png', image_bytes(), 'image/png')),
                              ('files', ('bad.png', b'not png', 'image/png'))])
    assert invalid.status_code == 422
    duplicate_sku = client.get('/api/v1/products/2').json()['variants'][0]['sku']
    duplicate = client.post('/api/v1/products/with-photos', headers=admin,
                            data={'data': json.dumps(payload(duplicate_sku))},
                            files={'files': ('good.png', image_bytes(), 'image/png')})
    assert duplicate.status_code == 409
    assert client.post('/api/v1/products/with-photos', headers=admin,
                       data={'data': '{not-json'}).status_code == 422
    with client.app.state.database.session_factory() as session:
        assert session.scalar(select(func.count(ProductORM.id))) == before
        assert session.scalar(select(func.count(ProductPhotoORM.id))) == 0
    assert not list(photo_folder(client).glob('*'))


def test_disk_failure_rolls_back_product_and_earlier_files(client):
    admin = admin_headers(client)
    original = media.os.replace
    calls = 0

    def fail_second(source, target):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError('disk full')
        return original(source, target)

    with patch.object(media.os, 'replace', fail_second):
        response = client.post('/api/v1/products/with-photos', headers=admin,
                               data={'data': json.dumps(payload())}, files=[
                                   ('files', ('one.png', image_bytes(), 'image/png')),
                                   ('files', ('two.png', image_bytes(), 'image/png'))])
    assert response.status_code == 503, response.text
    assert client.get('/api/v1/products', params={'q': 'Товар с фото'}).json()['total'] == 0
    assert not list(photo_folder(client).glob('*'))


def test_limit_and_wrong_parent(client):
    admin = admin_headers(client)
    for _ in range(5):
        assert upload(client, admin).status_code == 201
    assert upload(client, admin).status_code == 409
    six = [('files', ('one.png', image_bytes(), 'image/png'))] * 6
    assert client.post('/api/v1/products/with-photos', headers=admin,
                       data={'data': json.dumps(payload())}, files=six).status_code == 422
    photo = client.get('/api/v1/products/2').json()['images'][0]
    for method, url in [('delete', f"/api/v1/products/3/photos/{photo['id']}"),
                        ('patch', f"/api/v1/products/3/photos/{photo['id']}/cover")]:
        assert getattr(client, method)(url, headers=admin).status_code == 404
    assert upload(client, admin, 999999).status_code == 404


def test_legacy_image_and_delete_product_cleanup(client):
    admin = admin_headers(client)
    with client.app.state.database.session_factory.begin() as session:
        session.get(ProductORM, 2).image_url = '/media/products/v2/cat-food.webp'
    legacy = client.patch('/api/v1/products/2', json={'name': 'Старый товар'}, headers=admin).json()
    assert legacy['image_url'] == '/media/products/v2/cat-food.webp' and legacy['images'] == []
    photo = upload(client, admin).json()['images'][0]
    assert client.delete('/api/v1/products/2', headers=admin).status_code == 204
    assert client.get(photo['url']).status_code == 404
    assert not list(photo_folder(client).glob('*'))


def test_admin_and_cookie_csrf_required(client):
    assert upload(client, {}).status_code == 401
    assert client.post('/api/v1/products/with-photos', data={'data': json.dumps(payload())}).status_code == 401
    other = admin_headers(client, 'photo-customer@example.com')
    with client.app.state.database.session_factory.begin() as session:
        row = session.scalar(select(UserORM).where(UserORM.email == 'photo-customer@example.com'))
        row.role = 'customer'
    assert upload(client, other).status_code == 403
    admin_headers(client)
    credentials = {'email': 'test-admin@example.com', 'password': 'StrongAdmin123'}
    login = client.post('/api/v1/auth/browser/login', json=credentials, headers={'Origin': 'http://testserver'})
    assert login.status_code == 200, login.text
    assert upload(client, {'Origin': 'http://testserver'}).status_code == 403
    csrf = {'Origin': 'http://testserver', 'X-CSRF-Token': client.cookies['pitomo_csrf']}
    assert upload(client, csrf).status_code == 201
    assert client.get('/media/products/not-a-uuid.webp').status_code == 404


@pytest.mark.postgresql
def test_parallel_uploads_preserve_five_photo_limit(pg_empty, tmp_path):
    """Use the existing dedicated-test-database guard and disposable PG schema."""
    pg_empty.create_schema()
    from app.catalog.models import Food, ProductVariant
    from app.catalog.repository import SQLAlchemyProductRepository
    with pg_empty.session_factory.begin() as session:
        SQLAlchemyProductRepository(session).add(Food(1, 'Фото', 'cat', 'Питомо',
            [ProductVariant(1, 'PHOTO-PG', '500 г', '1000', 3)], 'Мясо'))
        product = media._product(session, 1)
        session.info['settings'] = Settings.for_testing(review_upload_dir=str(tmp_path))
        for _ in range(4):
            media._save(session, product, image_bytes('WEBP'))

    def add_one():
        with pg_empty.session_factory.begin() as session:
            session.info['settings'] = Settings.for_testing(review_upload_dir=str(tmp_path))
            from app.catalog.service import CatalogService
            file = UploadFile(file=BytesIO(image_bytes()), filename='one.png',
                              headers=Headers({'content-type': 'image/png'}))
            try:
                media.upload_photo(1, file, None, session,
                                   CatalogService(SQLAlchemyProductRepository(session)))
            except HTTPException as exc:
                return exc.status_code
            return 201
    assert sorted(pg_support.parallel(add_one, add_one)) == [201, 409]
    with pg_empty.session_factory() as session:
        assert session.scalar(select(func.count(ProductPhotoORM.id))) == 5
