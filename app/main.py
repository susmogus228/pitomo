"""Separate runtime and isolated test factories."""
from __future__ import annotations

from dataclasses import replace
from contextlib import asynccontextmanager
import logging
import json
import re
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import IntegrityError, OperationalError

from app.auth.dependencies import AdminUser
from app.auth.rate_limit import AuthLimitMiddleware
from app.auth.exceptions import AuthenticationError, AuthorizationError
from app.auth.router import router as auth_router
from app.admin.exceptions import AdminSelfLockoutError
from app.admin.router import router as admin_router
from app.admin.exports import router as exports_router
from app.cart.exceptions import CartItemNotFoundError, InsufficientStockError, InvalidCartDataError
from app.cart.router import router as cart_router
from app.catalog.exceptions import (
    DuplicateSKUError,
    InvalidCatalogDataError,
    ProductNotFoundError,
    VariantNotFoundError,
)
from app.catalog.router import router as catalog_router
from app.catalog.media import router as product_media_router
from app.privacy.router import router as privacy_router
from app.core.config import Settings, TEST_DATABASE_URL, load_settings
from app.db.base import Base
from app.db.errors import unique_violation
from app.db.seed import seed_demo_catalog
from app.db.session import Database, backend_name
from app.orders.exceptions import EmptyCartError, InvalidOrderDataError, OrderCheckoutError, OrderNotFoundError
from app.orders.router import router as orders_router
from app.orders.repeat import router as repeat_orders_router
from app.saved_addresses.router import router as saved_addresses_router
from app.users.exceptions import EmailAlreadyExistsError, InvalidUserDataError, UserNotFoundError
from app.users.router import router as users_router
from app.favorites.router import router as favorites_router
from app.reviews.router import router as reviews_router
from app.reviews.extended import router as review_extended_router
from app.reviews.media import router as review_media_router
from app.reviews.moderation import router as review_moderation_router
from app.db.dependencies import SessionDependency
from app.db.models import ReviewORM, ReviewPhotoORM, ReviewReplyORM
from app.geo.router import router as vets_router
from app.geo.addresses import AddressClient, router as addresses_router


SCHEMA_REVISION = '0012_v014'
logger = logging.getLogger('petshop.audit')
logger.setLevel(logging.INFO)
if not logger.handlers:
    logger.addHandler(logging.StreamHandler())


def create_app(database_url: str | None = None, *, settings: Settings | None = None) -> FastAPI:
    """Build the runtime app; schema creation and seed are explicit CLI actions."""
    settings = settings or load_settings()
    if database_url is not None:
        settings = replace(settings, database_url=database_url)
    database = Database(settings.database_url, echo=settings.sql_echo)

    @asynccontextmanager
    async def lifespan(app):
        settings.validate()
        try:
            yield
        finally:
            database.dispose()

    app = FastAPI(
        title='Petshop API',
        version=settings.app_version,
        description=(
            'Учебный backend зоомагазина: каталог, пользователи, JWT-аутентификация, '
            'корзина и заказы. Начиная с v0.6 данные хранятся через SQLAlchemy; '
            'основная СУБД — PostgreSQL. В v0.7 добавлены роли customer/admin и Admin API.\n\n'
            '**Swagger workflow:** зарегистрируйтесь через `/api/v1/auth/register`, войдите через '
            '`/api/v1/auth/login`, скопируйте `access_token`, нажмите **Authorize** и вставьте токен.'
        ),
        docs_url='/docs' if settings.docs_enabled else None,
        redoc_url='/redoc' if settings.docs_enabled else None,
        openapi_url='/openapi.json' if settings.docs_enabled else None,
        swagger_ui_parameters={'persistAuthorization': False},
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.address_client = AddressClient(settings)
    app.state.database = database
    app.state.isolated_test_schema = False
    app.state.metrics = {'requests': 0, 'server_errors': 0, 'duration_seconds': 0.0}
    app.add_middleware(AuthLimitMiddleware, database=database, settings=settings)
    if settings.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                           allow_credentials=True, allow_methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
                           allow_headers=['Authorization', 'Content-Type', 'Idempotency-Key', 'X-CSRF-Token'])

    @app.middleware('http')
    async def observe(request, call_next):
        started = time.monotonic()
        request_id = uuid.uuid4().hex
        request.state.request_id = request_id
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers['X-Request-ID'] = request_id
            response.headers['X-Content-Type-Options'] = 'nosniff'
            response.headers['Cache-Control'] = ('private, no-store'
                                                 if request.url.path == '/api/v1/vets/nearby'
                                                 else 'no-store')
            return response
        finally:
            elapsed = time.monotonic() - started
            app.state.metrics['requests'] += 1
            app.state.metrics['server_errors'] += int(status >= 500)
            app.state.metrics['duration_seconds'] += elapsed
            route = request.scope.get('route')
            logger.info(json.dumps({
                'event': 'http_request', 'request_id': request_id, 'method': request.method,
                'route': getattr(route, 'path', 'unmatched'), 'status': status,
                'user_id': getattr(request.state, 'user_id', None), 'duration_ms': round(elapsed * 1000, 2),
            }))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        issues = [{'type': e['type'], 'loc': list(e['loc']),
                   'msg': 'Invalid value' if e['type'] == 'value_error' else e['msg']}
                  for e in exc.errors()]
        return JSONResponse(status_code=422, content={'detail': issues})

    @app.exception_handler(IntegrityError)
    async def integrity_error(request: Request, exc: IntegrityError):
        if unique_violation(exc, names={
            'ix_users_email', 'users_email_key', 'uq_product_variants_sku_normalized',
            'ix_product_variants_sku', 'product_variants_sku_key', 'uq_orders_user_idempotency_key',
            'uq_product_reviews_user_product',
            'uq_review_replies_one_official',
        }, sqlite_columns={
            'users.email', 'product_variants.sku', 'product_variants.sku_normalized',
            'orders.user_id, orders.idempotency_key',
            'product_reviews.user_id, product_reviews.product_id',
        }):
            return JSONResponse(status_code=409, content={'detail': 'Конфликт данных. Обновите данные и повторите запрос.'})
        logger.error(json.dumps({'event': 'unexpected_integrity_error',
                                 'request_id': getattr(request.state, 'request_id', None)}))
        return JSONResponse(status_code=500, content={'detail': 'Ошибка сохранения данных'})

    @app.exception_handler(OperationalError)
    async def storage_error(_: Request, exc: OperationalError):
        return JSONResponse(status_code=503, content={'detail': 'База данных временно недоступна'})

    @app.exception_handler(ProductNotFoundError)
    async def product_not_found(_: Request, exc: ProductNotFoundError):
        return JSONResponse(status_code=404, content={'detail': str(exc)})

    @app.exception_handler(VariantNotFoundError)
    async def variant_not_found(_: Request, exc: VariantNotFoundError):
        return JSONResponse(status_code=404, content={'detail': str(exc)})

    @app.exception_handler(DuplicateSKUError)
    async def duplicate_sku(_: Request, exc: DuplicateSKUError):
        return JSONResponse(status_code=409, content={'detail': str(exc)})

    @app.exception_handler(InvalidCatalogDataError)
    async def invalid_catalog_data(_: Request, exc: InvalidCatalogDataError):
        return JSONResponse(status_code=422, content={'detail': str(exc)})

    @app.exception_handler(UserNotFoundError)
    async def user_not_found(_: Request, exc: UserNotFoundError):
        return JSONResponse(status_code=404, content={'detail': str(exc)})

    @app.exception_handler(EmailAlreadyExistsError)
    async def duplicate_email(_: Request, exc: EmailAlreadyExistsError):
        return JSONResponse(status_code=409, content={'detail': str(exc)})

    @app.exception_handler(InvalidUserDataError)
    async def invalid_user_data(_: Request, exc: InvalidUserDataError):
        return JSONResponse(status_code=422, content={'detail': str(exc)})

    @app.exception_handler(AuthenticationError)
    async def authentication_error(_: Request, exc: AuthenticationError):
        return JSONResponse(
            status_code=401,
            content={'detail': str(exc)},
            headers={'WWW-Authenticate': 'Bearer'},
        )

    @app.exception_handler(AuthorizationError)
    async def authorization_error(_: Request, exc: AuthorizationError):
        return JSONResponse(status_code=403, content={'detail': str(exc)})

    @app.exception_handler(AdminSelfLockoutError)
    async def admin_self_lockout(_: Request, exc: AdminSelfLockoutError):
        return JSONResponse(status_code=409, content={'detail': str(exc)})

    @app.exception_handler(CartItemNotFoundError)
    async def cart_item_not_found(_: Request, exc: CartItemNotFoundError):
        return JSONResponse(status_code=404, content={'detail': str(exc)})

    @app.exception_handler(InsufficientStockError)
    async def insufficient_stock(_: Request, exc: InsufficientStockError):
        return JSONResponse(status_code=409, content={'detail': str(exc)})

    @app.exception_handler(InvalidCartDataError)
    async def invalid_cart_data(_: Request, exc: InvalidCartDataError):
        return JSONResponse(status_code=422, content={'detail': str(exc)})

    @app.exception_handler(OrderNotFoundError)
    async def order_not_found(_: Request, exc: OrderNotFoundError):
        return JSONResponse(status_code=404, content={'detail': str(exc)})

    @app.exception_handler(EmptyCartError)
    async def empty_cart(_: Request, exc: EmptyCartError):
        return JSONResponse(status_code=409, content={'detail': str(exc)})

    @app.exception_handler(OrderCheckoutError)
    async def order_checkout_error(_: Request, exc: OrderCheckoutError):
        return JSONResponse(status_code=409, content={'detail': str(exc)})

    @app.exception_handler(InvalidOrderDataError)
    async def invalid_order_data(_: Request, exc: InvalidOrderDataError):
        return JSONResponse(status_code=422, content={'detail': str(exc)})

    @app.get('/', tags=['Состояние'])
    def root():
        return {
            'name': settings.app_name,
            'version': settings.app_version,
            'status': 'running',
            'docs': '/docs' if settings.docs_enabled else None,
            'health': '/health',
            'ready': '/ready',
        }

    @app.get('/health', tags=['Состояние'])
    def health():
        # Liveness is independent of migrations or database availability.
        backend = backend_name(settings.database_url)
        storage = 'memory' if backend == 'sqlite' and ':memory:' in settings.database_url else backend
        return {'status': 'ok', 'storage': storage}

    @app.get('/api/v1/storefront/config', tags=['Справочники'])
    def storefront_config():
        return {'demo_payments_enabled': settings.demo_payments_enabled, 'currency': 'KZT'}

    @app.get('/ready', tags=['Состояние'], responses={503: {'description': 'Schema or storage is not ready'}})
    def ready():
        try:
            with database.engine.connect() as connection:
                inspector = inspect(connection)
                tables = set(inspector.get_table_names())
                if not set(Base.metadata.tables) <= tables:
                    raise ValueError('Missing tables')
                for table in Base.metadata.sorted_tables:
                    if not set(table.columns.keys()) <= {c['name'] for c in inspector.get_columns(table.name)}:
                        raise ValueError('Missing columns')
                if not app.state.isolated_test_schema:
                    revisions = set(connection.execute(text('SELECT version_num FROM alembic_version')).scalars())
                    if revisions != {SCHEMA_REVISION}:
                        raise ValueError('Outdated migration')
            return {'status': 'ready', 'revision': SCHEMA_REVISION}
        except Exception:
            return JSONResponse(status_code=503, content={'detail': 'Database schema is not ready'})

    @app.get('/metrics', tags=['Состояние'])
    def metrics(admin: AdminUser):
        """Process-local counters; aggregate across instances in the monitoring system."""
        return dict(app.state.metrics)

    @app.get('/media/reviews/{filename}', include_in_schema=False)
    def review_photo(filename: str, session: SessionDependency):
        # Both Vite and Nginx proxy here so hidden/deleted thread files are private.
        if re.fullmatch(r'[a-f0-9]{32}\.webp', filename) is None:
            raise HTTPException(status_code=404)
        visible = session.scalar(select(ReviewPhotoORM.id)
            .outerjoin(ReviewReplyORM, ReviewReplyORM.id == ReviewPhotoORM.reply_id)
            .join(ReviewORM, ReviewORM.id == func.coalesce(ReviewPhotoORM.review_id, ReviewReplyORM.review_id))
            .where(ReviewPhotoORM.filename == filename, ReviewPhotoORM.deleted_at.is_(None),
                   ReviewORM.deleted_at.is_(None), ReviewORM.hidden_at.is_(None),
                   (ReviewPhotoORM.reply_id.is_(None) | ReviewReplyORM.deleted_at.is_(None))).limit(1))
        if visible is None:
            raise HTTPException(status_code=404)
        target = Path(settings.review_upload_dir) / filename
        if not target.is_file():
            raise HTTPException(status_code=404)
        return FileResponse(target, media_type='image/webp', headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})

    @app.get('/media/products/{filename}', include_in_schema=False)
    def product_photo(filename: str):
        if re.fullmatch(r'[a-f0-9]{32}\.webp', filename) is None:
            raise HTTPException(status_code=404)
        target = Path(settings.review_upload_dir) / 'products' / filename
        if not target.is_file():
            raise HTTPException(status_code=404)
        return FileResponse(target, media_type='image/webp', headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})

    app.include_router(product_media_router)
    app.include_router(privacy_router)
    app.include_router(catalog_router)
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(exports_router)
    app.include_router(users_router)
    app.include_router(cart_router)
    app.include_router(orders_router)
    app.include_router(repeat_orders_router)
    app.include_router(saved_addresses_router)
    app.include_router(favorites_router)
    app.include_router(reviews_router)
    app.include_router(review_extended_router)
    app.include_router(review_media_router)
    app.include_router(review_moderation_router)
    app.include_router(vets_router)
    app.include_router(addresses_router)
    return app


def create_test_app(database_url: str | None = None, *, settings: Settings | None = None) -> FastAPI:
    """Seed only a newly allocated in-memory test database, never an explicit URL."""
    settings = settings or Settings.for_testing()
    application = create_app(database_url or TEST_DATABASE_URL, settings=settings)
    if database_url is None:
        application.state.database.create_schema()
        with application.state.database.session_factory() as session:
            seed_demo_catalog(session)
            session.commit()
        application.state.isolated_test_schema = True
    return application


app = create_app()
