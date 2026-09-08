import { Navigate, useLocation } from 'react-router-dom';

import { getReviewerSession } from '../reviewerAuth.js';

// Addition on top of the PRD (see backend/app/auth.py) — gates the two
// reviewer-only pages behind a login, redirecting back to where the
// reviewer was headed once they've logged in.
export default function RequireReviewerAuth({ children }) {
  const location = useLocation();
  if (!getReviewerSession()) {
    return <Navigate to="/reviewer/login" state={{ from: location.pathname }} replace />;
  }
  return children;
}
