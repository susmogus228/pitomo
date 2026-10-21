import { useEffect, useId, useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router";
import { api, ApiError, json, messageOf } from "./api";
import { Breadcrumbs, ErrorNotice, Loading, PageTitle } from "./components";
import { useResource } from "./useResource";
import { useStore } from "./StoreContext";
import "./privacy.css";
import type { FieldErrors } from "./formValidation";

export interface PrivacyConfig {
  version: string;
  draft: boolean;
  notice: string;
  registration_allowed: boolean;
  analytics_collection_active: boolean;
  operator: { name: string; identifier: string; email: string };
  sections: { title: string; text: string }[];
  service: { title: string; text: string };
  analytics: { title: string; text: string };
}
interface Receipt {
  decision: "accepted" | "declined" | "withdrawn";
  version: string;
  subject_name: string;
  created_at: string;
  source: string;
}
interface ConsentStatus {
  version: string;
  service: Receipt | null;
  analytics: Receipt | null;
  analytics_allowed: boolean;
}

export function ConsentFields({
  config,
  service,
  analytics,
  onService,
  onAnalytics,
  name = "",
  disabled = false,
  errors = {},
}: {
  config: PrivacyConfig;
  service: boolean;
  analytics: boolean;
  onService: (value: boolean) => void;
  onAnalytics: (value: boolean) => void;
  name?: string;
  disabled?: boolean;
  errors?: FieldErrors;
}) {
  const id = useId();
  const [subjectName, setSubjectName] = useState(name);
  const [nameEdited, setNameEdited] = useState(false);
  useEffect(() => {
    if (!nameEdited) setSubjectName(name);
  }, [name, nameEdited]);
  return (
    <fieldset className="consent-fields" disabled={disabled}>
      <legend>Ваши данные и согласия</legend>
      {config.draft && (
        <p className="privacy-draft" role="note">
          Тестовый проект. Документы содержат заглушки владельца. Для проверки
          используйте вымышленные данные.
        </p>
      )}
      <label className="field">
        <span>Фамилия, имя и отчество для согласия</span>
        <input
          name="consent_name"
          autoComplete="name"
          required
          minLength={3}
          maxLength={310}
          pattern="\s*\S+(?:\s+\S+)+\s*"
          title="Укажите фамилию и имя, отчество — при наличии"
          value={subjectName}
          onChange={(event) => {
            setSubjectName(event.target.value);
            setNameEdited(true);
          }}
          aria-invalid={Boolean(errors.consent_name)}
          aria-describedby={`${id}-name-help${errors.consent_name ? ` ${id}-name-error` : ""}`}
        />
        <small id={`${id}-name-help`}>
          Укажите полное имя как в документе, отчество — при наличии. ИИН
          покупателя не нужен.
        </small>
        {errors.consent_name && (
          <small className="error-text" id={`${id}-name-error`}>
            {errors.consent_name}
          </small>
        )}
      </label>
      <label className="consent-choice">
        <input
          type="checkbox"
          name="service_consent"
          required
          checked={service}
          onChange={(event) => onService(event.target.checked)}
          aria-invalid={Boolean(errors.service_consent)}
          aria-describedby={
            errors.service_consent ? `${id}-service-error` : undefined
          }
        />
        <span>
          Согласен(на) на обработку персональных данных для аккаунта и
          выполнения заказов.
        </span>
      </label>
      {errors.service_consent && (
        <p className="error-text" id={`${id}-service-error`}>
          {errors.service_consent}
        </p>
      )}
      <p className="consent-links">
        <Link to="/consent#service" target="_blank" rel="noopener">
          Прочитать согласие
        </Link>{" "}
        ·{" "}
        <Link to="/privacy" target="_blank" rel="noopener">
          Обработка данных
        </Link>
      </p>
      <label className="consent-choice">
        <input
          type="checkbox"
          name="analytics_consent"
          checked={analytics}
          onChange={(event) => onAnalytics(event.target.checked)}
        />
        <span>
          Разрешаю аналитику моих действий и персональные рекомендации.{" "}
          <small>
            Необязательно. Можно отключить в профиле; отказ не мешает покупкам.
          </small>
        </span>
      </label>
      <p className="consent-links">
        <Link to="/consent#analytics" target="_blank" rel="noopener">
          Цели и данные для аналитики
        </Link>
      </p>
      <p className="form-note">
        Сейчас сохраняем ваш выбор. Аналитика поведения и система рекомендаций
        ещё не подключены.
      </p>
    </fieldset>
  );
}

export function ConsentSettings() {
  const { user } = useStore();
  const config = useResource<PrivacyConfig>("/privacy/config");
  const status = useResource<ConsentStatus>("/users/me/consents", { scope: user?.id });
  const [service, setService] = useState(false);
  const [analytics, setAnalytics] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  useEffect(() => {
    setService(
      status.data?.service?.decision === "accepted" &&
        status.data.service.version === status.data.version,
    );
    setAnalytics(Boolean(status.data?.analytics_allowed));
  }, [status.data]);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (busy || !config.data || !config.data.registration_allowed) return;
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      await api("/users/me/consents", {
        method: "POST",
        body: json({
          version: config.data.version,
          subject_name: String(form.get("consent_name") || "").trim(),
          service,
          analytics,
        }),
      });
      setSuccess("Ваш выбор сохранён.");
      status.reload();
    } catch (e) {
      setError(messageOf(e));
      if (e instanceof ApiError && e.status === 409) {
        config.reload();
        status.reload();
      }
    } finally {
      setBusy(false);
    }
  };
  if (config.loading || status.loading)
    return <Loading text="Загружаем настройки данных…" />;
  if (config.error || status.error)
    return (
      <ErrorNotice
        message={config.error || status.error}
        retry={() => {
          config.reload();
          status.reload();
        }}
      />
    );
  if (!config.data || !status.data) return null;
  return (
    <section
      className="privacy-settings"
      aria-labelledby="privacy-settings-title"
    >
      <h2 id="privacy-settings-title">Данные и рекомендации</h2>
      {!status.data.service && (
        <p>
          Для этого аккаунта нет записанного согласия. Подтвердите актуальные
          условия, если хотите их принять.
        </p>
      )}
      {status.data.service &&
        status.data.service.version !== status.data.version && (
          <p>
            Условия обработки данных изменились. Откройте новую версию перед
            подтверждением.
          </p>
        )}
      <form onSubmit={submit}>
        <ConsentFields
          key={status.data.service?.subject_name || "empty"}
          config={config.data}
          service={service}
          analytics={analytics}
          onService={setService}
          onAnalytics={setAnalytics}
          name={
            status.data.service?.subject_name ||
            [user?.last_name, user?.first_name].filter(Boolean).join(" ")
          }
          disabled={busy || !config.data.registration_allowed}
        />
        {!config.data.registration_allowed && (
          <ErrorNotice message="Владелец ещё не подготовил документы для реального запуска." />
        )}
        <button
          className="button"
          disabled={busy || !config.data.registration_allowed}
        >
          {busy ? "Сохраняем…" : "Сохранить согласия"}
        </button>
      </form>
      {status.data.analytics?.decision === "accepted" && (
        <button
          className="text-button privacy-withdraw"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            setError("");
            setSuccess("");
            try {
              await api("/users/me/consents/analytics", { method: "DELETE" });
              setAnalytics(false);
              setSuccess("Согласие на аналитику отозвано.");
              status.reload();
            } catch (e) {
              setError(messageOf(e));
            } finally {
              setBusy(false);
            }
          }}
        >
          Отозвать согласие на аналитику
        </button>
      )}
      {status.data.service && (
        <p className="form-note">
          Последнее согласие для аккаунта:{" "}
          {new Date(status.data.service.created_at).toLocaleString("ru-RU", {
            timeZone: "Asia/Almaty",
          })}
          . Версия {status.data.service.version}.
        </p>
      )}
      <ErrorNotice message={error} />
      {success && (
        <p role="status" className="success-text">
          {success}
        </p>
      )}
      <p className="form-note">
        Для вопросов об удалении аккаунта и данных:{" "}
        <Link to="/privacy">контакт владельца и порядок обращений</Link>.
      </p>
    </section>
  );
}

export default function PrivacyPage({
  consent = false,
}: {
  consent?: boolean;
}) {
  const resource = useResource<PrivacyConfig>("/privacy/config");
  const config = resource.data;
  return (
    <>
      <Breadcrumbs
        items={[{ label: consent ? "Согласия" : "Обработка данных" }]}
      />
      <PageTitle
        eyebrow="Ваш выбор"
        subtitle="Цели обработки, условия и управление согласиями"
      >
        {consent ? "Согласия на обработку данных" : "Персональные данные"}
      </PageTitle>
      {resource.loading && <Loading />}
      <ErrorNotice message={resource.error} retry={resource.reload} />
      {config && (
        <article className="privacy-document">
          <p className={config.draft ? "privacy-draft" : "form-note"}>
            {config.notice}
          </p>
          <p className="form-note">Версия: {config.version}</p>
          {consent && (
            <>
              <section id="service">
                <h2>{config.service.title}</h2>
                <p>{config.service.text}</p>
              </section>
              <section id="analytics">
                <h2>{config.analytics.title}</h2>
                <p>{config.analytics.text}</p>
              </section>
            </>
          )}
          {config.sections.map((section) => (
            <section key={section.title}>
              <h2>{section.title}</h2>
              <p>{section.text}</p>
            </section>
          ))}
          <p>
            Правовая основа:{" "}
            <a
              href="https://old.adilet.zan.kz/rus/docs/Z1300000094"
              target="_blank"
              rel="noopener noreferrer"
            >
              Закон РК «О персональных данных и их защите»
            </a>
            ,{" "}
            <a
              href="https://old.adilet.zan.kz/rus/docs/V2000021498"
              target="_blank"
              rel="noopener noreferrer"
            >
              Правила сбора и обработки
            </a>
            .
          </p>
          <Link to="/account" className="button outline">
            Настройки согласий в профиле
          </Link>
        </article>
      )}
    </>
  );
}
