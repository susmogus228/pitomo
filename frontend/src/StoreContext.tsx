import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import type { ReactNode } from "react";
import { useLocation, useNavigate } from "react-router";
import { api, ApiError, json, messageOf } from "./api";
import { clearCheckoutDraft } from "./checkoutDraft";
import type { Cart, CartItem, Product, User } from "./types";
import {
  guestCartStorage,
  guestCartView,
  GUEST_CART_KEY,
  GUEST_CART_LIMIT,
  mergeGuestResults,
} from "./guestCart";
import type { GuestState } from "./guestCart";
import type { CartMergeResult, CartMergeItem } from "./purchaseTypes";
import { operationKey } from "./purchaseTypes";
import { productImage } from "./lib";
import {
  clearSubmission as rawClearSubmission,
  PENDING_INTENT_KEY,
  replayPendingIntent,
  savePendingIntent,
} from "./lib";

const clearSubmission = () => {
  try {
    rawClearSubmission();
  } catch {
    /* Cart remains usable without session storage. */
  }
};

interface Store {
  user: User | null;
  authLoading: boolean;
  sessionError: string;
  cart: Cart | null;
  favorites: Product[];
  guestStorageWarning: boolean;
  guestMergePending: boolean;
  guestMergeUnconfirmed: boolean;
  guestMergeBusy: boolean;
  guestMergeResults: CartMergeItem[];
  retryGuestMerge: () => Promise<void>;
  changeCartQuantity: (variantId: number, quantity: number) => Promise<void>;
  removeCartItem: (variantId: number) => Promise<void>;
  restoreCartItem: (item: CartItem, key: string) => Promise<string>;
  moveCartToFavorite: (variantId: number, key: string) => Promise<void>;
  notice: string;
  setNotice: (message: string) => void;
  login: (email: string, password: string) => Promise<string | null>;
  logout: () => Promise<void>;
  setUser: (user: User) => void;
  refreshSession: () => Promise<void>;
  refreshCart: () => Promise<Cart | null>;
  refreshFavorites: () => Promise<void>;
  addToCart: (
    product: Product,
    variantId: number,
    quantity?: number,
  ) => Promise<boolean>;
  toggleFavorite: (product: Product) => Promise<void>;
  requireLogin: (returnTo?: string) => boolean;
}
const StoreContext = createContext<Store | null>(null);

export function StoreProvider({ children }: { children: ReactNode }) {
  const [user, setUserState] = useState<User | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [sessionError, setSessionError] = useState("");
  const [guest, setGuest] = useState<GuestState>(() => guestCartStorage.read());
  const [guestStorageWarning, setGuestStorageWarning] = useState(
    guestCartStorage.memoryOnly(),
  );
  const [guestMergeBusy, setGuestMergeBusy] = useState(false);
  const [guestMergeResults, setGuestMergeResults] = useState<CartMergeItem[]>(
    [],
  );
  const [cart, setCart] = useState<Cart | null>(null);
  const [favorites, setFavorites] = useState<Product[]>([]);
  const [notice, setNotice] = useState("");
  const userRef = useRef<User | null>(null);
  const favoriteBusy = useRef(new Set<number>());
  const mergeFlight = useRef<Promise<void> | null>(null);
  const sessionRevision = useRef(0);
  const authChannel = useRef<BroadcastChannel | null>(null);
  const setUser = useCallback((next: User) => {
    if (userRef.current?.id !== next.id) {
      sessionRevision.current += 1;
      setCart(null);
      setFavorites([]);
      setGuestMergeResults([]);
      setGuestMergeBusy(false);
      mergeFlight.current = null;
    }
    userRef.current = next;
    setUserState(next);
  }, []);
  const saveGuest = useCallback((state: GuestState) => {
    const persisted = guestCartStorage.save(state);
    setGuestStorageWarning(!persisted);
    setGuest(guestCartStorage.read());
  }, []);
  const navigate = useNavigate();
  const location = useLocation();

  const refreshSession = useCallback(async () => {
    const revision = sessionRevision.current;
    setAuthLoading(true);
    setSessionError("");
    try {
      const next = await api<User>("/auth/session");
      if (sessionRevision.current !== revision) return;
      setUser(next);
      userRef.current = next;
    } catch (error) {
      if (sessionRevision.current !== revision) return;
      sessionRevision.current += 1;
      setUserState(null);
      userRef.current = null;
      setCart(null);
      setFavorites([]);
      if (!(error instanceof ApiError && error.status === 401))
        setSessionError(messageOf(error));
    } finally {
      setAuthLoading(false);
    }
  }, [setUser]);

  const refreshCart = useCallback(async () => {
    const owner = userRef.current?.id;
    const revision = sessionRevision.current;
    if (!owner) {
      const state = guestCartStorage.read();
      setGuest(state);
      return guestCartView(state.rows);
    }
    const next = await api<Cart>("/cart");
    if (owner === userRef.current?.id && revision === sessionRevision.current)
      setCart(next);
    return owner === userRef.current?.id && revision === sessionRevision.current
      ? next
      : null;
  }, []);
  const refreshFavorites = useCallback(async () => {
    const owner = userRef.current?.id;
    const revision = sessionRevision.current;
    if (!owner) {
      setFavorites([]);
      return;
    }
    const next = await api<Product[]>("/favorites");
    if (owner === userRef.current?.id && revision === sessionRevision.current)
      setFavorites(next);
  }, []);

  const retryGuestMerge = useCallback(
    async (automatic = false) => {
      if (mergeFlight.current) return mergeFlight.current;
      const owner = userRef.current?.id;
      if (!owner) return;
      const revision = sessionRevision.current;
      const execute = async () => {
        if (
          userRef.current?.id !== owner ||
          sessionRevision.current !== revision
        )
          return;
        const state = guestCartStorage.read();
        if (!state.rows.length && !state.pending) return;
        if (automatic && state.paused_owner_id === owner && !state.pending)
          return;
        if (state.pending && state.pending.owner_id !== owner) {
          setNotice(
            "Незавершённое объединение относится к другому аккаунту. Войдите в него, чтобы проверить результат.",
          );
          return;
        }
        const pending = state.pending || {
          owner_id: owner,
          operation_key: operationKey(),
          items: state.rows.map(({ variant_id, quantity }) => ({
            variant_id,
            quantity,
          })),
        };
        saveGuest({ ...state, pending });
        setGuestMergeBusy(true);
        try {
          const result = await api<CartMergeResult>("/cart/merge", {
            method: "POST",
            body: json({
              operation_key: pending.operation_key,
              items: pending.items,
              expected_user_id: pending.owner_id,
            }),
          });
          // Account changes must never display or consume a different account's result.
          if (
            userRef.current?.id !== owner ||
            sessionRevision.current !== revision
          )
            return;
          const current = guestCartStorage.read();
          if (current.pending?.operation_key === pending.operation_key) {
            saveGuest({
              rows: mergeGuestResults(current.rows, result.items),
              pending: null,
              paused_owner_id: owner,
            });
          }
          setGuestMergeResults(result.items);
          clearSubmission();
          await refreshCart();
          setNotice(
            result.items.some((item) => item.remaining_quantity > 0)
              ? "Корзины объединены частично. Проверьте недоступные позиции в корзине."
              : "Гостевые товары добавлены к корзине аккаунта.",
          );
        } catch (error) {
          if (
            userRef.current?.id === owner &&
            sessionRevision.current === revision
          )
            setNotice(
              `Не удалось подтвердить объединение. Товары сохранены; повторите проверку в корзине. ${messageOf(error)}`,
            );
        } finally {
          if (
            userRef.current?.id === owner &&
            sessionRevision.current === revision
          )
            setGuestMergeBusy(false);
        }
      };
      const locks =
        typeof navigator !== "undefined" ? navigator.locks : undefined;
      const task = locks
        ? locks
            .request("pitomo-guest-cart-merge", execute)
            .then(() => undefined)
        : execute();
      mergeFlight.current = task;
      try {
        await task;
      } finally {
        if (mergeFlight.current === task) mergeFlight.current = null;
      }
    },
    [refreshCart, saveGuest],
  );

  useEffect(() => {
    void refreshSession();
  }, [refreshSession]);
  useEffect(() => {
    const refresh = () => {
      void refreshSession();
    };
    window.addEventListener("focus", refresh);
    if (typeof BroadcastChannel !== "undefined") {
      const channel = new BroadcastChannel("pitomo-auth-session");
      authChannel.current = channel;
      channel.onmessage = (event) => {
        if (event.data === "changed") refresh();
      };
    }
    return () => {
      window.removeEventListener("focus", refresh);
      authChannel.current?.close();
      authChannel.current = null;
    };
  }, [refreshSession]);
  useEffect(() => {
    if (!user) {
      setCart(null);
      setFavorites([]);
      return;
    }
    void Promise.all([refreshCart(), refreshFavorites()]).catch((error) =>
      setNotice(messageOf(error)),
    );
    void retryGuestMerge(true);
  }, [user?.id, refreshCart, refreshFavorites, retryGuestMerge]);
  useEffect(() => {
    const changed = (event: StorageEvent) => {
      if (event.key !== GUEST_CART_KEY) return;
      setGuest(guestCartStorage.read());
      if (userRef.current) void refreshCart().catch(() => undefined);
    };
    window.addEventListener("storage", changed);
    return () => window.removeEventListener("storage", changed);
  }, [refreshCart]);
  useEffect(() => {
    const expire = () => {
      clearCheckoutDraft();
      sessionRevision.current += 1;
      setUserState(null);
      userRef.current = null;
      setGuestMergeBusy(false);
      mergeFlight.current = null;
      setGuestMergeResults([]);
      setCart(null);
      setFavorites([]);
      setNotice("Сессия завершилась. Войдите ещё раз.");
    };
    window.addEventListener("pitomo:session-expired", expire);
    return () => window.removeEventListener("pitomo:session-expired", expire);
  }, []);
  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(""), 6000);
    return () => clearTimeout(timer);
  }, [notice]);

  const login = async (email: string, password: string) => {
    const next = await api<User>("/auth/browser/login", {
      method: "POST",
      body: json({ email, password }),
    });
    setUser(next);
    authChannel.current?.postMessage("changed");
    setSessionError("");
    let warning: string | null = null;
    let completedAction: string | null = null;
    try {
      const replayed = await replayPendingIntent(async (intent) => {
        if (intent.action === "add_cart") {
          // Legacy pending intent may describe a row already in the new guest cart.
          if (
            guestCartStorage
              .read()
              .rows.some((row) => row.variant_id === intent.variantId)
          )
            return;
          await api("/cart/items", {
            method: "POST",
            body: json({
              variant_id: intent.variantId,
              quantity: intent.quantity,
            }),
          });
          clearSubmission();
        } else {
          await api(`/favorites/${intent.productId}`, { method: "PUT" });
        }
      });
      if (replayed)
        completedAction =
          replayed.action === "add_cart"
            ? "Выбранный товар добавлен в корзину."
            : "Выбранный товар сохранён в избранном.";
    } catch (error) {
      warning = `Вход выполнен, но не удалось подтвердить выбранное действие. ${messageOf(error)} Проверьте корзину или избранное перед повторным добавлением.`;
    }
    await retryGuestMerge();
    const refreshed = await Promise.allSettled([
      refreshCart(),
      refreshFavorites(),
    ]);
    if (refreshed.some((result) => result.status === "rejected")) {
      warning ||= `${completedAction || "Вход выполнен."} Не удалось обновить корзину или избранное. Проверьте их перед повторным добавлением.`;
    }
    if (userRef.current?.id !== next.id)
      throw new Error("Сессия завершилась. Войдите ещё раз.");
    setUser(next);
    if (completedAction && !warning) setNotice(completedAction);
    return warning;
  };
  const logout = async () => {
    await api<void>("/auth/logout", { method: "POST" });
    authChannel.current?.postMessage("changed");
    sessionRevision.current += 1;
    userRef.current = null;
    setUserState(null);
    setGuestMergeBusy(false);
    mergeFlight.current = null;
    setGuestMergeResults([]);
    setCart(null);
    setFavorites([]);
    clearSubmission();
    clearCheckoutDraft();
    try {
      sessionStorage.removeItem(PENDING_INTENT_KEY);
    } catch {
      /* Optional legacy intent. */
    }
    navigate("/");
  };
  const requireLogin = (returnTo = location.pathname + location.search) => {
    if (user) return true;
    navigate(`/login?returnTo=${encodeURIComponent(returnTo)}`);
    return false;
  };
  const addToCart = async (
    product: Product,
    variantId: number,
    quantity = 1,
  ) => {
    if (!userRef.current) {
      const variant = product.variants.find((item) => item.id === variantId);
      if (!variant || variant.stock < 1)
        throw new Error("Этот вариант сейчас недоступен.");
      const state = guestCartStorage.read();
      if (state.pending)
        throw new Error(
          "Сначала завершите проверку объединения корзины в своём аккаунте.",
        );
      const existing = state.rows.find((item) => item.variant_id === variantId);
      if (!existing && state.rows.length >= GUEST_CART_LIMIT)
        throw new Error(
          "В гостевой корзине можно сохранить до 50 разных товаров.",
        );
      const desired = (existing?.quantity || 0) + quantity;
      if (
        !Number.isSafeInteger(desired) ||
        desired > Math.min(10000, variant.stock)
      )
        throw new Error(
          `По последней проверке доступно ${variant.stock} шт. Проверьте количество в корзине.`,
        );
      const row = {
        variant_id: variantId,
        quantity: desired,
        product_id: product.id,
        product_name: product.name,
        label: variant.label,
        sku: variant.sku,
        unit_price: variant.price,
        image_url: productImage(product),
        available_stock: variant.stock,
      };
      saveGuest({
        rows: existing
          ? state.rows.map((item) =>
              item.variant_id === variantId ? row : item,
            )
          : [...state.rows, row],
        pending: null,
      });
      clearSubmission();
      setNotice(`${product.name} — в гостевой корзине`);
      return true;
    }
    const owner = userRef.current.id;
    await api("/cart/items", {
      method: "POST",
      body: json({ variant_id: variantId, quantity }),
    });
    clearSubmission();
    try {
      await refreshCart();
      if (userRef.current?.id === owner)
        setNotice(`${product.name} — в корзине`);
    } catch {
      setNotice(
        "Товар добавлен. Не удалось обновить счётчик корзины — откройте корзину для проверки.",
      );
    }
    return true;
  };
  const changeCartQuantity = async (variantId: number, quantity: number) => {
    if (!Number.isSafeInteger(quantity) || quantity < 1 || quantity > 10000)
      throw Error("Укажите допустимое количество.");
    if (!userRef.current) {
      const state = guestCartStorage.read();
      if (state.pending)
        throw Error("Сначала проверьте незавершённое объединение корзины.");
      saveGuest({
        rows: state.rows.map((row) =>
          row.variant_id === variantId ? { ...row, quantity } : row,
        ),
        pending: null,
      });
    } else {
      await api(`/cart/items/${variantId}`, {
        method: "PATCH",
        body: json({ quantity }),
      });
      await refreshCart();
    }
    clearSubmission();
  };
  const removeCartItem = async (variantId: number) => {
    if (!userRef.current) {
      const state = guestCartStorage.read();
      if (state.pending)
        throw Error("Сначала проверьте незавершённое объединение корзины.");
      saveGuest({
        rows: state.rows.filter((row) => row.variant_id !== variantId),
        pending: null,
      });
    } else {
      await api(`/cart/items/${variantId}`, { method: "DELETE" });
      await refreshCart().catch(() =>
        setNotice(
          "Товар удалён. Счётчик корзины обновится после повторной проверки.",
        ),
      );
    }
    clearSubmission();
  };
  const restoreCartItem = async (item: CartItem, key: string) => {
    const owner = userRef.current?.id;
    if (!owner) {
      const state = guestCartStorage.read();
      if (state.pending)
        throw Error("Сначала проверьте незавершённое объединение корзины.");
      const old = state.rows.find((row) => row.variant_id === item.variant_id);
      const row = {
        variant_id: item.variant_id,
        quantity: Math.min(10000, (old?.quantity || 0) + item.quantity),
        product_id: item.product_id,
        product_name: item.product_name,
        label: item.label,
        sku: item.sku,
        unit_price: item.unit_price,
        image_url: item.image_url || null,
        available_stock: item.available_stock,
      };
      if (!old && state.rows.length >= GUEST_CART_LIMIT)
        throw Error("Сначала освободите место в гостевой корзине.");
      saveGuest({
        rows: old
          ? state.rows.map((value) =>
              value.variant_id === row.variant_id ? row : value,
            )
          : [...state.rows, row],
        pending: null,
      });
      return "Товар восстановлен в гостевой корзине. Наличие проверим после входа.";
    }
    const result = await api<CartMergeResult>("/cart/items/restore", {
      method: "POST",
      body: json({
        variant_id: item.variant_id,
        quantity: item.quantity,
        operation_key: key,
        expected_user_id: owner,
      }),
    });
    if (userRef.current?.id !== owner) return "";
    clearSubmission();
    await refreshCart();
    const restored = result.items[0];
    return restored.remaining_quantity
      ? `Восстановлено ${restored.added_quantity} из ${restored.requested_quantity} шт. Остальное сейчас недоступно.`
      : "Товар восстановлен в корзине.";
  };
  const moveCartToFavorite = async (variantId: number, key: string) => {
    if (!requireLogin("/cart")) return;
    const owner = userRef.current?.id;
    await api(`/cart/items/${variantId}/favorite`, {
      method: "POST",
      body: json({ operation_key: key, expected_user_id: owner }),
    });
    if (userRef.current?.id !== owner) return;
    clearSubmission();
    await Promise.all([refreshCart(), refreshFavorites()]);
    setNotice("Товар сохранён в избранном и удалён из корзины.");
  };
  const toggleFavorite = async (product: Product) => {
    if (!user) savePendingIntent({ action: "favorite", productId: product.id });
    if (!requireLogin() || favoriteBusy.current.has(product.id)) return;
    favoriteBusy.current.add(product.id);
    const owner = userRef.current?.id;
    const exists = favorites.some((item) => item.id === product.id);
    try {
      await api(`/favorites/${product.id}`, {
        method: exists ? "DELETE" : "PUT",
      });
      if (userRef.current?.id !== owner) return;
      setFavorites((items) =>
        exists
          ? items.filter((item) => item.id !== product.id)
          : [...items, product],
      );
      setNotice(
        exists ? "Товар удалён из избранного" : "Товар сохранён в избранном",
      );
    } finally {
      favoriteBusy.current.delete(product.id);
    }
  };

  return (
    <StoreContext.Provider
      value={{
        user,
        authLoading,
        sessionError,
        cart: user ? cart : guestCartView(guest.rows),
        favorites,
        guestStorageWarning,
        guestMergePending: Boolean(
          guest.pending || (user && guest.rows.length),
        ),
        guestMergeUnconfirmed: Boolean(guest.pending),
        guestMergeBusy,
        guestMergeResults,
        retryGuestMerge,
        changeCartQuantity,
        removeCartItem,
        restoreCartItem,
        moveCartToFavorite,
        notice,
        setNotice,
        login,
        logout,
        setUser,
        refreshSession,
        refreshCart,
        refreshFavorites,
        addToCart,
        toggleFavorite,
        requireLogin,
      }}
    >
      {children}
    </StoreContext.Provider>
  );
}

export function useStore() {
  const value = useContext(StoreContext);
  if (!value) throw new Error("StoreProvider is missing");
  return value;
}
