import { Link, NavLink, Outlet, useMatch, useNavigate } from 'react-router-dom';

import { reviewerLogout } from '../api.js';
import { clearReviewerSession, getReviewerSession } from '../reviewerAuth.js';

// Re-read on every render (cheap localStorage lookup) rather than held in
// state — this app has no global state store, and a full page nav happens
// on login/logout anyway (see handleLogout below), so this always reflects
// the current session without needing a context provider.
function ReviewerSessionStatus() {
  const session = getReviewerSession();
  const navigate = useNavigate();

  async function handleLogout() {
    await reviewerLogout();
    clearReviewerSession();
    navigate('/');
  }

  if (!session) return null;
  return (
    <span className="reviewer-session-status">
      Reviewer: <strong>{session.username}</strong>{' '}
      <button type="button" className="link-button" onClick={handleLogout}>
        Log out
      </button>
    </span>
  );
}

// Only meaningful on an actual review detail screen (/reviewer/{referenceId})
// — not the queue itself, and not /reviewer/login, which the same pattern
// would otherwise also match (":referenceId" happily binds to "login").
function BackToQueueLink() {
  const match = useMatch('/reviewer/:referenceId');
  const navigate = useNavigate();
  const referenceId = match?.params.referenceId;
  if (!referenceId || referenceId === 'login') return null;

  return (
    // navigate(-1) rather than a Link to a fixed "/reviewer" path — the
    // latter would drop whatever filters/sort/page the reviewer had set
    // (US-20 AC: filter state persists while navigating). Living in the
    // nav bar (rather than the page body) means it's visible immediately,
    // even while the review detail page itself is still loading or failed
    // to load.
    <button type="button" className="top-nav__back" onClick={() => navigate(-1)}>
      ← Back to queue
    </button>
  );
}

// Single shared layout for every route (React Router "layout route" — see
// App.jsx) so the nav bar is defined once, not repeated per page, and is
// structurally guaranteed to appear on every screen rather than relying on
// each page to remember to render it.
export default function Layout() {
  return (
    <>
      <header className="top-nav">
        <Link to="/" className="top-nav__brand">
          OnboardIQ
        </Link>
        <NavLink to="/" end>
          Apply
        </NavLink>
        <NavLink to="/reviewer">Reviewer Queue</NavLink>
        <BackToQueueLink />
        <ReviewerSessionStatus />
      </header>
      <main className="app-shell">
        <Outlet />
      </main>
    </>
  );
}
