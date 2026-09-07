import { useState } from 'react';

import { submitDecision } from '../api.js';
import FieldError from './FieldError.jsx';

const ACTIONS = [
  { value: 'APPROVE', label: 'Approve' },
  { value: 'REJECT', label: 'Reject' },
  { value: 'REQUEST_INFO', label: 'Request More Information' },
];

export default function DecisionForm({ referenceId, onDecided }) {
  const [reviewerId, setReviewerId] = useState('');
  const [action, setAction] = useState('APPROVE');
  const [reasoning, setReasoning] = useState('');
  const [errors, setErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState('');

  const reasoningRequired = action === 'REJECT' || action === 'REQUEST_INFO';

  function validate() {
    const nextErrors = {};
    if (!reviewerId.trim()) {
      nextErrors.reviewer_id = 'Enter your reviewer ID before submitting a decision.';
    }
    if (reasoningRequired && !reasoning.trim()) {
      nextErrors.reasoning = 'Reasoning is required when rejecting or requesting more information.';
    }
    setErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (!validate()) return;

    setSubmitting(true);
    setFormError('');
    try {
      const decision = await submitDecision(referenceId, {
        reviewer_id: reviewerId.trim(),
        action,
        reasoning: reasoning.trim() || null,
      });
      onDecided(decision);
    } catch (err) {
      if (err.fieldErrors && Object.keys(err.fieldErrors).length > 0) {
        setErrors(err.fieldErrors);
      } else {
        setFormError(err.message || 'Could not submit the decision. Please try again.');
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="decision-form" onSubmit={handleSubmit}>
      <h2>Decision</h2>

      <div className="form-field">
        <label htmlFor="reviewer_id">Reviewer ID</label>
        <input
          id="reviewer_id"
          type="text"
          value={reviewerId}
          onChange={(e) => setReviewerId(e.target.value)}
          disabled={submitting}
        />
        <FieldError message={errors.reviewer_id} />
      </div>

      <div className="form-field">
        <label htmlFor="action">Action</label>
        <select id="action" value={action} onChange={(e) => setAction(e.target.value)} disabled={submitting}>
          {ACTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      <div className="form-field">
        <label htmlFor="reasoning">Reasoning {reasoningRequired ? '(required)' : '(optional)'}</label>
        <textarea
          id="reasoning"
          rows={3}
          value={reasoning}
          onChange={(e) => setReasoning(e.target.value)}
          disabled={submitting}
        />
        <FieldError message={errors.reasoning} />
      </div>

      {formError && (
        <p className="form-error" role="alert">
          {formError}
        </p>
      )}

      <button type="submit" disabled={submitting}>
        {submitting ? 'Submitting…' : 'Submit Decision'}
      </button>
    </form>
  );
}
