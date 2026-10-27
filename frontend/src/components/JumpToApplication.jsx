import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { getApplication } from '../api.js';
import { getReviewerSession } from '../reviewerAuth.js';
import { resolveJumpTarget } from '../jumpToApplication.js';

// Reviewer-only (same self-contained session check Layout.jsx's other
// nav-bar pieces use — see ReviewerSessionStatus/BackToQueueLink) — an
// applicant has no reason to jump straight to a reference ID by typing it.
export default function JumpToApplication() {
  const [value, setValue] = useState('');
  const [error, setError] = useState('');
  const [checking, setChecking] = useState(false);
  const navigate = useNavigate();

  if (!getReviewerSession()) return null;

  async function handleSubmit(event) {
    event.preventDefault();
    if (checking) return;
    setChecking(true);
    const result = await resolveJumpTarget(value, getApplication);
    setChecking(false);
    if (result.ok) {
      setValue('');
      setError('');
      navigate(result.path);
    } else {
      setError(result.error);
    }
  }

  return (
    <form className="jump-to-application" onSubmit={handleSubmit}>
      <input
        type="text"
        value={value}
        onChange={(event) => {
          setValue(event.target.value);
          if (error) setError('');
        }}
        placeholder="Jump to ONB-…"
        aria-label="Jump to application by reference ID"
        disabled={checking}
      />
      {error && (
        <span className="jump-to-application__error" role="alert">
          {error}
        </span>
      )}
    </form>
  );
}
