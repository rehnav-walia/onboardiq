import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

import { reviewerLogin } from '../api.js';
import FieldError from '../components/FieldError.jsx';
import { setReviewerSession } from '../reviewerAuth.js';

// Reviewer login — an addition on top of the PRD (see backend/app/auth.py).
// A small, fixed set of demo accounts, not a full user-management system;
// applicants never see this page or authenticate at all.
export default function ReviewerLoginPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const redirectTo = location.state?.from || '/reviewer';

  async function handleSubmit(event) {
    event.preventDefault();
    setSubmitting(true);
    setError('');
    try {
      const { token } = await reviewerLogin(username.trim(), password);
      setReviewerSession(token, username.trim());
      navigate(redirectTo, { replace: true });
    } catch (err) {
      setError(err.message || 'Invalid username or password.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="reviewer-login">
      <h1>Reviewer Login</h1>
      <p className="reviewer-login__hint">
        Demo accounts: <code>reviewer_1</code>, <code>reviewer_2</code>, or <code>reviewer_42</code> — password{' '}
        <code>changeme123</code>. Not a production authentication system.
      </p>
      <form onSubmit={handleSubmit}>
        <div className="form-field">
          <label htmlFor="reviewer-username">Username</label>
          <input
            id="reviewer-username"
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            disabled={submitting}
            autoFocus
          />
        </div>
        <div className="form-field">
          <label htmlFor="reviewer-password">Password</label>
          <input
            id="reviewer-password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={submitting}
          />
        </div>
        {error && <FieldError message={error} />}
        <button type="submit" disabled={submitting || !username.trim() || !password}>
          {submitting ? 'Logging in…' : 'Log in'}
        </button>
      </form>
    </div>
  );
}
