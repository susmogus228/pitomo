import type { CheckoutInput } from "./types";
export type FieldErrors = Record<string, string>;
export function authFieldErrors(
  values: Record<string, string | boolean>,
  register: boolean,
): FieldErrors {
  const errors: FieldErrors = {};
  const text = (name: string) => String(values[name] ?? "");
  if (register && !text("first_name").trim())
    errors.first_name = "Укажите имя.";
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(text("email").trim()))
    errors.email = "Укажите корректную электронную почту.";
  if (
    text("password").length < (register ? 8 : 1) ||
    text("password").length > 128
  )
    errors.password = register
      ? "Пароль должен содержать от 8 до 128 символов."
      : "Введите пароль.";
  if (register && text("password") !== text("password_confirm"))
    errors.password_confirm = "Пароли не совпадают. Повторите пароль.";
  if (register && !/^\s*\S+(?:\s+\S+)+\s*$/.test(text("consent_name")))
    errors.consent_name = "Укажите фамилию и имя, отчество — при наличии.";
  if (register && !values.service_consent)
    errors.service_consent =
      "Для создания аккаунта подтвердите согласие на обработку данных.";
  return errors;
}
export function checkoutFieldErrors(input: CheckoutInput): FieldErrors {
  const errors: FieldErrors = {};
  if (!input.contact_name.trim())
    errors.contact_name = "Укажите имя получателя.";
  if (
    !/^\+?[0-9 ()-]+$/.test(input.phone) ||
    input.phone.replace(/\D/g, "").length < 7
  )
    errors.phone = "Укажите корректный номер телефона: не менее 7 цифр.";
  if (input.delivery_method === "delivery") {
    if (!input.address || input.address.trim().length < 5)
      errors.address = "Укажите город, улицу и номер дома.";
    else if (input.address.length > 500)
      errors.address = "Адрес слишком длинный. Сократите его до 500 символов.";
  }
  return errors;
}

export function focusFirstError(
  form: HTMLFormElement,
  errors: FieldErrors,
): void {
  const control = Array.from(form.elements).find(
    (element) =>
      "name" in element && Boolean(errors[(element as HTMLInputElement).name]),
  );
  if (control && "focus" in control) (control as HTMLElement).focus();
}
