import { Component, lazy, Suspense, useEffect, useLayoutEffect, useRef } from "react";
import type { ErrorInfo, ReactNode } from "react";
import { Route, Routes, useLocation } from "react-router";
import {
  Footer,
  Header,
  Icon,
  Loading,
  RequireAdmin,
  RequireAuth,
} from "./components";
import { Favorites, Home, ProductDetail } from "./pages/Shop";
import { Catalog } from "./pages/Catalog";
import { About, Help, NotFound } from "./pages/Info";
import { useStore } from "./StoreContext";
import { routeTitle } from "./pageTitles";

const Auth = lazy(() => import("./pages/Auth"));
const PrivacyPage = lazy(() => import("./Privacy"));
const Cart = lazy(() => import("./pages/Cart"));
const Checkout = lazy(() => import("./pages/Checkout"));
const Account = lazy(() => import("./pages/Account"));
const Order = lazy(() => import("./pages/Order"));
const Vets = lazy(() => import("./pages/Vets"));
const Discounts = lazy(() => import("./pages/Discounts"));
const AdminOrders = lazy(() => import("./pages/AdminOrders"));
const AdminOrderDetail = lazy(() =>
  import("./pages/AdminOrders").then((module) => ({
    default: module.AdminOrderDetail,
  })),
);
const AdminLayout = lazy(() =>
  import("./pages/Admin").then((module) => ({ default: module.AdminLayout })),
);
const AdminOverview = lazy(() =>
  import("./pages/Admin").then((module) => ({ default: module.AdminOverview })),
);
const AdminProducts = lazy(() =>
  import("./pages/Admin").then((module) => ({ default: module.AdminProducts })),
);
const AdminReviews = lazy(() =>
  import("./pages/Admin").then((module) => ({ default: module.AdminReviews })),
);
const AdminUsers = lazy(() =>
  import("./pages/Admin").then((module) => ({ default: module.AdminUsers })),
);

class PageErrorBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(
      "Storefront rendering failed",
      error.name,
      info.componentStack,
    );
  }
  render() {
    return this.state.failed ? (
      <div className="empty-state" role="alert">
        <h1>Не удалось открыть страницу</h1>
        <p>Обновите магазин, чтобы попробовать снова.</p>
        <button className="button" onClick={() => window.location.reload()}>
          Обновить страницу
        </button>
      </div>
    ) : (
      this.props.children
    );
  }
}

function RouteEffects() {
  const location = useLocation();
  const previousPath = useRef(location.pathname);
  useLayoutEffect(() => { document.title = routeTitle(location.pathname); }, [location.pathname]);
  useEffect(() => {
    if (previousPath.current !== location.pathname) {
      document.getElementById("main-content")?.focus({ preventScroll: true });
      previousPath.current = location.pathname;
    }
    if (!location.hash) window.scrollTo({ top: 0, behavior: "instant" });
    else
      requestAnimationFrame(() =>
        document.getElementById(location.hash.slice(1))?.scrollIntoView(),
      );
  }, [location.pathname, location.hash]);
  return null;
}

export default function App() {
  const { user, notice, setNotice, sessionError, refreshSession } = useStore();
  return (
    <>
      <a className="skip-link" href="#main-content">
        Перейти к содержимому
      </a>
      <RouteEffects />
      <Header />
      {sessionError && (
        <div className="session-banner shell" role="alert">
          {sessionError}
          <button className="text-button" onClick={() => void refreshSession()}>
            Повторить
          </button>
        </div>
      )}
      <main className="shell main" id="main-content" tabIndex={-1}>
        <PageErrorBoundary>
          <Suspense fallback={<Loading />}>
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/catalog" element={<Catalog />} />
              <Route path="/product/:id" element={<ProductDetail />} />
              <Route path="/login" element={<Auth />} />
              <Route path="/register" element={<Auth register />} />
              <Route path="/privacy" element={<PrivacyPage />} />
              <Route path="/consent" element={<PrivacyPage consent />} />
              <Route
                path="/favorites"
                element={
                  <RequireAuth>
                    <Favorites />
                  </RequireAuth>
                }
              />
              <Route
                path="/cart"
                element={<Cart key={user?.id ?? "guest"} />}
              />
              <Route
                path="/checkout"
                element={
                  <RequireAuth>
                    <Checkout key={user?.id ?? "guest"} />
                  </RequireAuth>
                }
              />
              <Route
                path="/orders/:id"
                element={
                  <RequireAuth>
                    <Order key={user?.id ?? "guest"} />
                  </RequireAuth>
                }
              />
              <Route
                path="/account"
                element={
                  <RequireAuth>
                    <Account />
                  </RequireAuth>
                }
              />
              <Route path="/about" element={<About />} />
              <Route path="/help" element={<Help />} />
              <Route path="/vets" element={<Vets />} />
              <Route
                path="/admin"
                element={
                  <RequireAdmin>
                    <AdminLayout />
                  </RequireAdmin>
                }
              >
                <Route index element={<AdminOverview />} />
                <Route path="products" element={<AdminProducts />} />
                <Route path="orders" element={<AdminOrders />} />
                <Route path="orders/:id" element={<AdminOrderDetail />} />
                <Route path="reviews" element={<AdminReviews />} />
                <Route path="discounts" element={<Discounts />} />
                <Route path="users" element={<AdminUsers />} />
              </Route>
              <Route path="*" element={<NotFound />} />
            </Routes>
          </Suspense>
        </PageErrorBoundary>
      </main>
      <Footer />
      {notice && (
        <div className="toast" role="status">
          <span>{notice}</span>
          <button
            onClick={() => setNotice("")}
            aria-label="Закрыть уведомление"
          >
            <Icon name="close" size={18} />
          </button>
        </div>
      )}
    </>
  );
}
