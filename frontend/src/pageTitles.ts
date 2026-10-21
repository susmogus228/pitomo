const titles: Record<string, string> = {
  "/": "У каждого свой характер", "/catalog": "Каталог", "/cart": "Корзина",
  "/checkout": "Оформление заказа", "/login": "Войти", "/register": "Регистрация",
  "/privacy": "Персональные данные", "/consent": "Согласия", "/account": "Личный кабинет",
  "/favorites": "Избранное", "/about": "О магазине", "/help": "Помощь", "/vets": "Ветклиники рядом",
  "/admin/discounts": "Управление скидками", "/admin/orders": "Заказы магазина",
  "/admin": "Панель администратора", "/admin/products": "Товары и остатки",
  "/admin/reviews": "Отзывы магазина", "/admin/users": "Пользователи магазина",
};

export function routeTitle(path: string) {
  const order = path.match(/^\/(admin\/)?orders\/([1-9]\d*)\/?$/);
  const title = titles[path] || (order ? `${order[1] ? "Заказ магазина" : "Заказ"} №${order[2]}` : /^\/product\/[1-9]\d*\/?$/.test(path) ? "Товар" : "Страница не найдена");
  return `${title} — Питомо`;
}

export const productTitle = (name: string) => `${name.trim() || "Товар"} — Питомо`;
