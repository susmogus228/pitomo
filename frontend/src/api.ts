export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function readCookie(
  name: string,
  source = document.cookie,
): string | undefined {
  const entry = source
    .split(";")
    .map((value) => value.trim())
    .find((value) => value.startsWith(`${name}=`));
  if (!entry) return undefined;
  try {
    return decodeURIComponent(entry.slice(name.length + 1));
  } catch {
    return undefined;
  }
}

export function errorMessage(
  payload: unknown,
  fallback = "Не удалось выполнить запрос. Попробуйте ещё раз.",
): string {
  if (!payload || typeof payload !== "object") return fallback;
  const body = payload as { detail?: unknown; error?: { message?: string } };
  if (typeof body.detail === "string") return body.detail;
  if (Array.isArray(body.detail)) {
    return (
      body.detail
        .map((issue) =>
          typeof issue?.msg === "string"
            ? issue.msg.replace(/^Value error, /, "")
            : "",
        )
        .filter(Boolean)
        .join(". ") || fallback
    );
  }
  return body.error?.message || fallback;
}

export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type"))
    headers.set("Content-Type", "application/json");
  const method = (options.method || "GET").toUpperCase();
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const token = readCookie("pitomo_csrf");
    if (token) headers.set("X-CSRF-Token", token);
  }
  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, {
      ...options,
      headers,
      credentials: "same-origin",
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError")
      throw error;
    throw new ApiError(
      0,
      "Нет связи с магазином. Проверьте подключение и повторите попытку.",
    );
  }
  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null);
    if (response.status === 401 && !path.startsWith("/auth/"))
      window.dispatchEvent(new Event("pitomo:session-expired"));
    throw new ApiError(
      response.status,
      errorMessage(payload, `Ошибка ${response.status}. Попробуйте ещё раз.`),
    );
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const json = (value: unknown) => JSON.stringify(value);
export const messageOf = (error: unknown) =>
  error instanceof Error
    ? error.message
    : "Что-то пошло не так. Попробуйте ещё раз.";
