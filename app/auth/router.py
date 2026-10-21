"""HTTP routes for registration and login."""
from fastapi import APIRouter, status, Request, Response

from app.core.schemas import ErrorResponse
from app.users.schemas import UserResponse

from app.db.dependencies import SessionDependency
from app.privacy.documents import require_current_document
from app.privacy.router import record_consent
from .dependencies import AuthServiceDependency
from .browser import require_browser_origin, start_session, end_session, browser_user
from .schemas import TokenResponse, UserLogin, UserRegister

router = APIRouter(prefix='/api/v1/auth', tags=['Аутентификация'])


@router.post(
    '/register',
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary='Регистрация пользователя',
    responses={
        409: {'model': ErrorResponse, 'description': 'Пользователь с таким email уже существует'},
        422: {'model': ErrorResponse, 'description': 'Некорректные регистрационные данные'},
        429: {'model': ErrorResponse, 'description': 'Превышен лимит попыток'},
    },
)
def register(data: UserRegister, service: AuthServiceDependency, session: SessionDependency):
    config = require_current_document(service.settings, data.consent.version)
    user = service.register(data)
    record_consent(session, user.id, data.consent, config, 'registration')
    return user.to_dict()


@router.post(
    '/login',
    response_model=TokenResponse,
    summary='Вход и получение JWT',
    description=(
        'Возвращает JWT access token. В Swagger скопируйте `access_token`, нажмите '
        '**Authorize** вверху страницы и вставьте токен в поле Bearer authorization.'
    ),
    responses={
        401: {'model': ErrorResponse, 'description': 'Неверный email или пароль'},
        422: {'model': ErrorResponse, 'description': 'Некорректное тело запроса'},
        429: {'model': ErrorResponse, 'description': 'Превышен лимит попыток'},
    },
)
def login(data: UserLogin, service: AuthServiceDependency):
    return service.login(data)


@router.post('/browser/login', response_model=UserResponse, summary='Войти через браузерную сессию')
def browser_login(data: UserLogin, request: Request, response: Response,
                  session: SessionDependency, service: AuthServiceDependency):
    require_browser_origin(request, service.settings)
    credentials = service.login(data)
    user = service.user_from_token(credentials['access_token'])
    start_session(request, response, session, service.settings, user.id)
    return user.to_dict()


@router.get('/session', response_model=UserResponse, summary='Текущая браузерная сессия')
def get_session(request: Request, session: SessionDependency):
    user = browser_user(request, session, session.info['settings'])
    request.state.user_id = user.id
    return user.to_dict()


@router.post('/logout', status_code=204, summary='Завершить браузерную сессию')
def logout(request: Request, session: SessionDependency):
    settings = session.info['settings']
    browser_user(request, session, settings)
    response = Response(status_code=204)
    end_session(request, response, session, settings)
    return response
