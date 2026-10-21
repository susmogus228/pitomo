import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router";
import { api, ApiError, json, messageOf } from "../api";
import { useStore } from "../StoreContext";
import { readPendingIntent, safeReturnTo } from "../lib";
import { Breadcrumbs, ErrorNotice, Icon, Loading } from "../components";
import "../auth.css";
import { ConsentFields } from "../Privacy";
import type { PrivacyConfig } from "../Privacy";
import { useResource } from "../useResource";
import { authFieldErrors, focusFirstError } from "../formValidation";
import type { FieldErrors } from "../formValidation";
import { mediaUrl, illustrationSources } from "../media";

export default function Auth({ register = false }: { register?: boolean }) {
  const { user, authLoading, login } = useStore();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const returnTo = safeReturnTo(params.get("returnTo"));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [consentSuggestedName, setConsentSuggestedName] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [registered, setRegistered] = useState(false);
  const [pendingIntent] = useState(() => readPendingIntent());
  const privacy = useResource<PrivacyConfig>(
    register ? "/privacy/config" : null,
  );
  const [serviceConsent, setServiceConsent] = useState(false);
  const [analyticsConsent, setAnalyticsConsent] = useState(false);
  useEffect(() => {
    setServiceConsent(false);
    setAnalyticsConsent(false);
  }, [privacy.data?.version]);
  if (authLoading) return <Loading />;
  if (user && !busy && !error) return <Navigate to={returnTo} replace />;
  if (user && error)
    return (
      <section className="auth-panel" style={{ marginBlock: 48 }}>
        <h2>Вход выполнен</h2>
        <ErrorNotice message={error} />
        <div className="button-row">
          <Link
            className="button"
            to={pendingIntent?.action === "favorite" ? "/favorites" : "/cart"}
          >
            Проверить{" "}
            {pendingIntent?.action === "favorite" ? "избранное" : "корзину"}
          </Link>
          <Link className="button outline" to={returnTo}>
            Продолжить
          </Link>
        </div>
      </section>
    );
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (busy) return;
    const form = new FormData(event.currentTarget);
    const email = String(form.get("email") || "").trim();
    const password = String(form.get("password") || "");
    const errors = authFieldErrors(
      {
        first_name: String(form.get("first_name") || ""),
        email,
        password,
        password_confirm: String(form.get("password_confirm") || ""),
        consent_name: String(form.get("consent_name") || ""),
        service_consent: serviceConsent,
      },
      register && !registered,
    );
    setFieldErrors(errors);
    setError("");
    if (Object.keys(errors).length) {
      focusFirstError(event.currentTarget, errors);
      return;
    }
    setBusy(true);
    setError("");
    try {
      if (register && !registered) {
        if (!privacy.data?.registration_allowed || !serviceConsent) {
          setError(
            "Откройте условия обработки данных и подтвердите согласие для аккаунта.",
          );
          return;
        }
        await api("/auth/register", {
          method: "POST",
          body: json({
            email,
            password,
            first_name: String(form.get("first_name")).trim(),
            last_name: String(form.get("last_name") || "").trim() || null,
            consent: {
              version: privacy.data.version,
              subject_name: String(form.get("consent_name") || "").trim(),
              service: serviceConsent,
              analytics: analyticsConsent,
            },
          }),
        });
        setRegistered(true);
      }
      const warning = await login(email, password);
      if (warning) setError(warning);
      else navigate(returnTo, { replace: true });
    } catch (e) {
      setError(messageOf(e));
      if (e instanceof ApiError && e.status === 409 && register && !registered)
        privacy.reload();
    } finally {
      setBusy(false);
    }
  };
  const switchLink = `${register ? "/login" : "/register"}?returnTo=${encodeURIComponent(returnTo)}`;
  return (
    <>
      <Breadcrumbs items={[{ label: register ? "Регистрация" : "Вход" }]} />
      <div
        className={`auth-layout auth-v2 ${register ? "auth-register" : "auth-login"}`}
      >
        <div className="auth-story">
          <div className="auth-cat-frame">
            <span className="auth-cat-marker" aria-hidden="true">
              {register ? "?" : "Это ты!"}
            </span>
            <img
              src={mediaUrl(`/media/${register ? "cat-register" : "cat-login"}-1280.webp`)}
              srcSet={illustrationSources(register ? "cat-register" : "cat-login")}
              sizes="(max-width: 800px) 90vw, 45vw"
              alt={
                register
                  ? "Кот осторожно знакомится и любопытно смотрит на нового человека"
                  : "Кот узнаёт хозяина и идёт навстречу с поднятым хвостом"
              }
              width={register ? 1024 : 1536}
              height={register ? 1536 : 1024}
            />
          </div>
          <p className="auth-cat-thought">
            {register ? (
              <>
                Кажется, у нас новый человек.
                <br />
                <strong>Будем знакомы?</strong>
              </>
            ) : (
              <>
                А я тебя помню.
                <br />
                <strong>Как хорошо, что ты вернулся.</strong>
              </>
            )}
          </p>
        </div>
        <section className="auth-panel" aria-labelledby="auth-title">
          <p className="auth-eyebrow">
            {register ? "Первое знакомство" : "Свои снова дома"}
          </p>
          <h1 id="auth-title">
            {register ? (
              <>
                Давай
                <br />
                знакомиться.
              </>
            ) : (
              "С возвращением!"
            )}
          </h1>
          <p className="auth-intro">
            {register
              ? "Пара слов о себе, и ты среди своих. Сохраняй любимое и собирай всё для питомца."
              : "Твои находки, любимые товары и заказы уже ждут в личном кабинете."}
          </p>
          {pendingIntent && (
            <p className="form-note">
              После входа{" "}
              {pendingIntent.action === "add_cart"
                ? "добавим выбранный товар в корзину"
                : "сохраним выбранный товар в избранном"}{" "}
              и вернём вас в магазин.
            </p>
          )}
          {registered && (
            <p className="success-text">Аккаунт создан. Осталось войти.</p>
          )}
          <form
            onSubmit={submit}
            noValidate
            onChange={(event) => {
              const name = (event.target as unknown as HTMLInputElement).name;
              if (name === "first_name" || name === "last_name") {
                const values = new FormData(event.currentTarget);
                setConsentSuggestedName(
                  [values.get("last_name"), values.get("first_name")]
                    .filter(Boolean)
                    .join(" ")
                    .trim(),
                );
              }
              if (fieldErrors[name])
                setFieldErrors((old) => {
                  const next = { ...old };
                  delete next[name];
                  return next;
                });
            }}
          >
            {register && (
              <div className="form-row">
                <label className="field">
                  <span>Имя</span>
                  <input
                    name="first_name"
                    autoComplete="given-name"
                    required
                    maxLength={100}
                    disabled={registered}
                    aria-invalid={Boolean(fieldErrors.first_name)}
                    aria-describedby={
                      fieldErrors.first_name
                        ? "auth-first-name-error"
                        : undefined
                    }
                  />
                  {fieldErrors.first_name && (
                    <small className="error-text" id="auth-first-name-error">
                      {fieldErrors.first_name}
                    </small>
                  )}
                </label>
                <label className="field">
                  <span>
                    Фамилия <small>необязательно</small>
                  </span>
                  <input
                    name="last_name"
                    autoComplete="family-name"
                    maxLength={100}
                    disabled={registered}
                  />
                </label>
              </div>
            )}
            <label className="field">
              <span>Электронная почта</span>
              <input
                type="email"
                name="email"
                autoComplete="email"
                required
                maxLength={254}
                placeholder="you@example.com"
                aria-invalid={Boolean(fieldErrors.email)}
                aria-describedby={
                  fieldErrors.email ? "auth-email-error" : undefined
                }
              />
              {fieldErrors.email && (
                <small className="error-text" id="auth-email-error">
                  {fieldErrors.email}
                </small>
              )}
            </label>
            <label className="field">
              <span>Пароль</span>
              <div className="password-input">
                <input
                  type={showPassword ? "text" : "password"}
                  name="password"
                  autoComplete={register ? "new-password" : "current-password"}
                  required
                  minLength={register ? 8 : 1}
                  maxLength={128}
                  aria-invalid={Boolean(fieldErrors.password)}
                  aria-describedby={
                    [
                      register ? "password-help" : "",
                      fieldErrors.password ? "auth-password-error" : "",
                    ]
                      .filter(Boolean)
                      .join(" ") || undefined
                  }
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((value) => !value)}
                  aria-label={
                    showPassword ? "Скрыть пароль" : "Показать пароль"
                  }
                >
                  {showPassword ? "Скрыть" : "Показать"}
                </button>
              </div>
              {register && (
                <small id="password-help">От 8 до 128 символов.</small>
              )}
              {fieldErrors.password && (
                <small className="error-text" id="auth-password-error">
                  {fieldErrors.password}
                </small>
              )}
            </label>
            {register && !registered && (
              <label className="field">
                <span>Повторите пароль</span>
                <input
                  type={showPassword ? "text" : "password"}
                  name="password_confirm"
                  autoComplete="new-password"
                  required
                  minLength={8}
                  maxLength={128}
                  aria-invalid={Boolean(fieldErrors.password_confirm)}
                  aria-describedby={
                    fieldErrors.password_confirm
                      ? "auth-password-confirm-error"
                      : undefined
                  }
                />
                {fieldErrors.password_confirm && (
                  <small
                    className="error-text"
                    id="auth-password-confirm-error"
                  >
                    {fieldErrors.password_confirm}
                  </small>
                )}
              </label>
            )}
            {register && !registered && (
              <>
                {privacy.loading && (
                  <Loading text="Загружаем условия обработки данных…" />
                )}
                <ErrorNotice message={privacy.error} retry={privacy.reload} />
                {privacy.data && (
                  <ConsentFields
                    config={privacy.data}
                    service={serviceConsent}
                    analytics={analyticsConsent}
                    onService={setServiceConsent}
                    onAnalytics={setAnalyticsConsent}
                    name={consentSuggestedName}
                    errors={fieldErrors}
                    disabled={busy || !privacy.data.registration_allowed}
                  />
                )}
                {privacy.data && !privacy.data.registration_allowed && (
                  <ErrorNotice message="Документы магазина ещё не готовы для регистрации." />
                )}
              </>
            )}
            <ErrorNotice message={error} />
            <button
              className="button full-width"
              disabled={
                busy ||
                (register && !registered && !privacy.data?.registration_allowed)
              }
            >
              {busy
                ? "Подождите…"
                : register && !registered
                  ? "Зарегистрироваться"
                  : "Войти"}
              <Icon name="arrow" size={20} />
            </button>
          </form>
          <p className="auth-switch">
            {register ? "Уже знакомы?" : "Пока нет аккаунта?"}{" "}
            <Link to={switchLink}>
              {register ? "Войти" : "Зарегистрироваться"} →
            </Link>
          </p>
          <p className="form-note">
            Это демонстрационный магазин. Не используйте пароль от других
            сервисов.
          </p>
        </section>
      </div>
    </>
  );
}
