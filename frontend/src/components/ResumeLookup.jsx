import { useState } from 'react';

import { getApplication } from '../api.js';
import FieldError from './FieldError.jsx';

// US-03 AC: "Applicant can resume using the reference ID." Also doubles as
// the general "check status" entry point for SUBMITTED+ applications (e.g.
// coming back to see an INFO_REQUESTED note, or a final decision) — the
// backend's GET-by-reference-ID endpoint already works for every status.
export default function ResumeLookup({ onFound }) {
  const [open, setOpen] = useState(false);
  const [referenceId, setReferenceId] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    if (!referenceId.trim()) {
      setError('Enter your reference ID.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const application = await getApplication(referenceId.trim());
      onFound(application);
    } catch (err) {
      setError(err.message || 'No application found with that reference ID.');
    } finally {
      setLoading(false);
    }
  }

  if (!open) {
    return (
      <p className="resume-lookup-toggle">
        Already started an application?{' '}
        <button type="button" className="link-button" onClick={() => setOpen(true)}>
          Resume or check status
        </button>
      </p>
    );
  }

  return (
    <form className="resume-lookup" onSubmit={handleSubmit}>
      <div className="form-field">
        <label htmlFor="resume-reference-id">Reference ID</label>
        <input
          id="resume-reference-id"
          type="text"
          placeholder="ONB-2026-00001"
          value={referenceId}
          onChange={(e) => setReferenceId(e.target.value)}
          disabled={loading}
        />
        <FieldError message={error} />
      </div>
      <div className="resume-lookup__actions">
        <button type="submit" disabled={loading}>
          {loading ? 'Looking up…' : 'Continue'}
        </button>
        <button type="button" className="link-button" onClick={() => setOpen(false)} disabled={loading}>
          Cancel
        </button>
      </div>
    </form>
  );
}
