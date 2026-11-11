import { useQuery } from "@tanstack/react-query";
import { Link, NavLink, Outlet, Route, Routes } from "react-router-dom";
import { api } from "./api";
import { ThemeToggle } from "./components/ThemeToggle";
import { Documents } from "./pages/Documents";
import { Review } from "./pages/Review";

/** The routes: `/` Documents, `/documents/:id` Review. Screens fill the sheet inside the shell. */
export function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Documents />} />
        <Route path="documents/:id" element={<Review />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}

function Shell() {
  return (
    <div className="app">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="topbar">
        <Link to="/" className="brand">
          <BrandMark />
          <span className="brand__name">Pharma dates</span>
        </Link>
        <nav className="topbar__nav" aria-label="Main">
          <NavLink to="/" end className="topbar__link">
            Documents
          </NavLink>
        </nav>
        <div className="topbar__end">
          <HealthStatus />
          <ThemeToggle />
        </div>
      </header>
      <main className="sheet" id="main" tabIndex={-1}>
        <Outlet />
      </main>
    </div>
  );
}

/** A highlight box around a line of text: what the app draws on every page. */
function BrandMark() {
  return (
    <svg className="brand__mark" viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="7" className="brand__mark-ground" />
      <rect x="6" y="10" width="20" height="12" rx="2" className="brand__mark-box" />
      <path d="M10 16h12" className="brand__mark-line" />
    </svg>
  );
}

function HealthStatus() {
  const health = useQuery({ queryKey: ["health"], queryFn: () => api.getHealth(), staleTime: 60_000 });

  if (health.isPending) return <span className="health health--pending">Checking server</span>;
  if (health.isError) {
    return (
      <span className="health health--down" role="status">
        Server unreachable
      </span>
    );
  }
  const { ai_enabled, model } = health.data;
  return (
    <span className={ai_enabled ? "health health--ai" : "health"} role="status">
      <span className="health__label">{ai_enabled ? "AI on" : "Rules only"}</span>
      {ai_enabled && model ? <span className="health__model">{model}</span> : null}
    </span>
  );
}

function NotFound() {
  return (
    <div className="screen">
      <header className="title-row">
        <h1>Page not found</h1>
      </header>
      <p className="muted">
        This address does not match a screen. <Link to="/">Back to documents</Link>
      </p>
    </div>
  );
}
