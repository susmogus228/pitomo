"""HTTP routes for the catalog module."""
from decimal import Decimal
from .types import PetType, ProductKind
from typing import Annotated, Literal

from fastapi import Path, APIRouter, Depends, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import AdminUser
from app.core.schemas import ErrorResponse
from app.db.dependencies import get_db_session
from app.db.dependencies import SessionDependency
from app.db.models import ProductPhotoORM, ReviewORM

from .schemas import (
    ProductCreate,
    ProductKindResponse,
    ProductPage,
    ProductResponse,
    ProductUpdate,
    VariantCreate,
    VariantResponse,
    VariantUpdate,
)
from .repository import SQLAlchemyProductRepository
from .service import CatalogService

router = APIRouter()


def get_catalog_service(
    session: Annotated[Session, Depends(get_db_session, scope="function")],
) -> CatalogService:
    return CatalogService(SQLAlchemyProductRepository(session))


ServiceDependency = Annotated[CatalogService, Depends(get_catalog_service)]


def _rating_map(session: Session, product_ids: list[int]) -> dict[int, tuple[int, float]]:
    if not product_ids:
        return {}
    rows = session.execute(select(ReviewORM.product_id, func.count(ReviewORM.id), func.avg(ReviewORM.rating))
                           .where(ReviewORM.product_id.in_(product_ids), ReviewORM.deleted_at.is_(None), ReviewORM.hidden_at.is_(None))
                           .group_by(ReviewORM.product_id)).all()
    return {product_id: (count, round(float(average), 2)) for product_id, count, average in rows}


def _with_ratings(items: list[dict], session: Session) -> list[dict]:
    product_ids = [item['id'] for item in items]
    ratings = _rating_map(session, product_ids)
    photos: dict[int, list[dict]] = {}
    if product_ids:
        rows = session.scalars(select(ProductPhotoORM).where(
            ProductPhotoORM.product_id.in_(product_ids)).order_by(
                ProductPhotoORM.created_at, ProductPhotoORM.id))
        for photo in rows:
            photos.setdefault(photo.product_id, []).append({
                'id': photo.id, 'url': f'/media/products/{photo.filename}',
            })
    for item in items:
        count, average = ratings.get(item['id'], (0, None))
        item['rating_count'] = count
        item['rating_average'] = average
        item['images'] = photos.get(item['id'], [])
    return items


@router.get(
    '/api/v1/products',
    response_model=ProductPage,
    tags=['Каталог'],
    summary='Список товаров',
)
def products(
    service: ServiceDependency,
    session: SessionDependency,
    q: Annotated[str | None, Query(max_length=100)] = None,
    pet_type: PetType | None = None,
    category: Literal['food', 'accessory'] | None = None,
    product_kind: ProductKind | None = None,
    brand: str | None = None,
    min_price: Annotated[Decimal | None, Query(ge=0, max_digits=12, decimal_places=2)] = None,
    max_price: Annotated[Decimal | None, Query(ge=0, max_digits=12, decimal_places=2)] = None,
    in_stock: bool | None = None,
    hits_only: bool = False,
    sort: Literal['id', 'name', 'price_asc', 'price_desc'] = 'id',
    page: Annotated[int, Query(ge=1, le=2147483647)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    result = service.list_products(
        q=q,
        pet_type=pet_type,
        category=category,
        product_kind=product_kind,
        brand=brand,
        min_price=min_price,
        max_price=max_price,
        in_stock=in_stock,
        hits_only=hits_only,
        sort=sort,
        page=page,
        page_size=page_size,
    )
    _with_ratings(result['items'], session)
    return result


@router.post(
    '/api/v1/products',
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    tags=['Каталог'],
    summary='Создать товар',
    responses={
        401: {'model': ErrorResponse, 'description': 'Bearer-токен отсутствует или недействителен'},
        403: {'model': ErrorResponse, 'description': 'Требуются права администратора'},
        409: {'model': ErrorResponse, 'description': 'SKU уже используется'},
    },
)
def create_product(data: ProductCreate, service: ServiceDependency, admin_user: AdminUser,
                   session: SessionDependency):
    return _with_ratings([service.create_product(data).to_dict()], session)[0]


@router.get(
    '/api/v1/products/{product_id}',
    response_model=ProductResponse,
    tags=['Каталог'],
    summary='Получить товар',
    responses={404: {'model': ErrorResponse, 'description': 'Товар не найден'}},
)
def product_detail(product_id: Annotated[int, Path(gt=0, le=2147483647)], service: ServiceDependency,
                   session: SessionDependency):
    return _with_ratings([service.get_product(product_id).to_dict()], session)[0]


@router.patch(
    '/api/v1/products/{product_id}',
    response_model=ProductResponse,
    tags=['Каталог'],
    summary='Изменить товар',
    responses={
        401: {'model': ErrorResponse, 'description': 'Bearer-токен отсутствует или недействителен'},
        403: {'model': ErrorResponse, 'description': 'Требуются права администратора'},
        404: {'model': ErrorResponse, 'description': 'Товар не найден'},
    },
)
def update_product(product_id: Annotated[int, Path(gt=0, le=2147483647)], data: ProductUpdate, service: ServiceDependency, admin_user: AdminUser,
                   session: SessionDependency):
    return _with_ratings([service.update_product(product_id, data).to_dict()], session)[0]


@router.delete(
    '/api/v1/products/{product_id}',
    status_code=status.HTTP_204_NO_CONTENT,
    tags=['Каталог'],
    summary='Удалить товар',
    responses={
        401: {'model': ErrorResponse, 'description': 'Bearer-токен отсутствует или недействителен'},
        403: {'model': ErrorResponse, 'description': 'Требуются права администратора'},
        404: {'model': ErrorResponse, 'description': 'Товар не найден'},
    },
)
def delete_product(product_id: Annotated[int, Path(gt=0, le=2147483647)], service: ServiceDependency, admin_user: AdminUser,
                   session: SessionDependency):
    from pathlib import Path as FilePath

    service.repository.lock_product(product_id)
    photo_paths = [FilePath(session.info['settings'].review_upload_dir) / 'products' / row.filename
                   for row in session.scalars(select(ProductPhotoORM).where(
                       ProductPhotoORM.product_id == product_id))]
    service.delete_product(product_id)
    session.info.setdefault('deleted_uploads', []).extend(photo_paths)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    '/api/v1/products/{product_id}/variants',
    response_model=VariantResponse,
    status_code=status.HTTP_201_CREATED,
    tags=['Варианты товара'],
    summary='Добавить вариант товара',
    responses={
        401: {'model': ErrorResponse, 'description': 'Bearer-токен отсутствует или недействителен'},
        403: {'model': ErrorResponse, 'description': 'Требуются права администратора'},
        404: {'model': ErrorResponse, 'description': 'Товар не найден'},
        409: {'model': ErrorResponse, 'description': 'SKU уже используется'},
    },
)
def add_variant(product_id: Annotated[int, Path(gt=0, le=2147483647)], data: VariantCreate, service: ServiceDependency, admin_user: AdminUser):
    return service.add_variant(product_id, data).to_dict()


@router.patch(
    '/api/v1/products/{product_id}/variants/{variant_id}',
    response_model=VariantResponse,
    tags=['Варианты товара'],
    summary='Изменить вариант товара',
    responses={
        401: {'model': ErrorResponse, 'description': 'Bearer-токен отсутствует или недействителен'},
        403: {'model': ErrorResponse, 'description': 'Требуются права администратора'},
        404: {'model': ErrorResponse, 'description': 'Товар или вариант не найден'},
        409: {'model': ErrorResponse, 'description': 'SKU уже используется'},
    },
)
def update_variant(
    product_id: Annotated[int, Path(gt=0, le=2147483647)],
    variant_id: Annotated[int, Path(gt=0, le=2147483647)],
    data: VariantUpdate,
    service: ServiceDependency,
    admin_user: AdminUser,
):
    return service.update_variant(product_id, variant_id, data).to_dict()


@router.delete(
    '/api/v1/products/{product_id}/variants/{variant_id}',
    status_code=status.HTTP_204_NO_CONTENT,
    tags=['Варианты товара'],
    summary='Удалить вариант товара',
    responses={
        401: {'model': ErrorResponse, 'description': 'Bearer-токен отсутствует или недействителен'},
        403: {'model': ErrorResponse, 'description': 'Требуются права администратора'},
        404: {'model': ErrorResponse, 'description': 'Товар или вариант не найден'},
    },
)
def delete_variant(product_id: Annotated[int, Path(gt=0, le=2147483647)], variant_id: Annotated[int, Path(gt=0, le=2147483647)], service: ServiceDependency, admin_user: AdminUser):
    service.delete_variant(product_id, variant_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get('/api/v1/categories', tags=['Справочники'], summary='Список категорий')
def categories(service: ServiceDependency):
    return service.categories()


@router.get('/api/v1/product-kinds', response_model=list[ProductKindResponse],
            tags=['Справочники'], summary='Разделы и число товаров для выбранного питомца')
def product_kinds(service: ServiceDependency, pet_type: PetType | None = None):
    return service.product_kinds(pet_type=pet_type)


@router.get(
    '/api/v1/brands',
    response_model=list[str],
    tags=['Справочники'],
    summary='Список брендов',
)
def brands(service: ServiceDependency):
    return service.brands()
