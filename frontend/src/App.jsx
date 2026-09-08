import { NavLink, Route, Routes, useNavigate } from 'react-router-dom';

import { reviewerLogout } from './api.js';
import RequireReviewerAuth from './components/RequireReviewerAuth.jsx';
import ApplicantFlow from './pages/ApplicantFlow.jsx';
import ReviewDetailPage from './pages/ReviewDetailPage.jsx';
import ReviewerLoginPage from './pages/ReviewerLoginPage.jsx';
import ReviewerQueuePage from './pages/ReviewerQueuePage.jsx';
import { clearReviewerSession, getReviewerSession } from './reviewerAuth.js';

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

export default function App() {
  return (
    <>
      <nav className="top-nav">
        <NavLink to="/" end>
          Apply
        </NavLink>
        <NavLink to="/reviewer">Reviewer Queue</NavLink>
        <ReviewerSessionStatus />
      </nav>
      <main className="app-shell">
        <Routes>
          <Route path="/" element={<ApplicantFlow />} />
          <Route path="/reviewer/login" element={<ReviewerLoginPage />} />
          <Route
            path="/reviewer"
            element={
              <RequireReviewerAuth>
                <ReviewerQueuePage />
              </RequireReviewerAuth>
            }
          />
          <Route
            path="/reviewer/:referenceId"
            element={
              <RequireReviewerAuth>
                <ReviewDetailPage />
              </RequireReviewerAuth>
            }
          />
        </Routes>
      </main>
    </>
  );
}
