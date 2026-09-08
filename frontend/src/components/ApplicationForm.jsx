import { useState } from 'react';

import { createDraft, submitApplication, submitDraft, updateDraft } from '../api.js';
import { EMPTY_APPLICATION, STEPS, findStepForField, validateField, validateStep } from '../validation.js';
import ProgressIndicator from './ProgressIndicator.jsx';
import StepAccountType from './steps/StepAccountType.jsx';
import StepAddressContact from './steps/StepAddressContact.jsx';
import StepPersonalDetails from './steps/StepPersonalDetails.jsx';

const STEP_COMPONENTS = [StepPersonalDetails, StepAddressContact, StepAccountType];

// US-03: a draft's fields come back from the API as null until filled in —
// controlled inputs need '' instead, same shape as EMPTY_APPLICATION.
function valuesFromDraft(draft) {
  const values = { ...EMPTY_APPLICATION };
  for (const key of Object.keys(values)) {
    if (draft[key] !== null && draft[key] !== undefined) values[key] = draft[key];
  }
  return values;
}

// US-03: the draft API rejects a blank-but-provided string ("" is not the
// same as "not answered yet") — every field is sent on every save, so blanks
// must become null rather than "".
function toDraftPayload(values) {
  const payload = {};
  for (const [key, value] of Object.entries(values)) {
    payload[key] = value === '' ? null : value;
  }
  return payload;
}

export default function ApplicationForm({ onSubmitted, initialDraft }) {
  // Single source of truth for all step data (US-02 DoD) — this is also
  // what keeps entered values intact across a failed validation (US-01 DoD):
  // nothing here ever gets cleared, only added to.
  const [values, setValues] = useState(initialDraft ? valuesFromDraft(initialDraft) : EMPTY_APPLICATION);
  const [errors, setErrors] = useState({});
  const [touched, setTouched] = useState({});
  const [stepIndex, setStepIndex] = useState(0);
  const [highestStepReached, setHighestStepReached] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');

  // US-03: once a draft exists (either resumed, or created via "Save for
  // later" below), every further save updates the SAME reference ID instead
  // of creating a new application, and the final submit transitions it
  // rather than creating a brand new one.
  const [draftReferenceId, setDraftReferenceId] = useState(initialDraft?.reference_id ?? null);
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState('');
  const [saveError, setSaveError] = useState('');

  function updateField(name, value) {
    setValues((prev) => ({ ...prev, [name]: value }));
    setTouched((prev) => ({ ...prev, [name]: true }));
    setErrors((prev) => ({ ...prev, [name]: validateField(name, value) }));
  }

  function markStepTouched(stepIdx) {
    const updates = {};
    for (const field of STEPS[stepIdx].fields) updates[field] = true;
    setTouched((prev) => ({ ...prev, ...updates }));
  }

  function goNext() {
    const stepErrors = validateStep(stepIndex, values);
    markStepTouched(stepIndex);
    setErrors((prev) => ({ ...prev, ...stepErrors }));
    if (Object.keys(stepErrors).length === 0) {
      const next = stepIndex + 1;
      setStepIndex(next);
      setHighestStepReached((prev) => Math.max(prev, next));
    }
  }

  function goBack() {
    setStepIndex((prev) => Math.max(0, prev - 1));
  }

  function goToStep(index) {
    // US-02 DoD: direct navigation to a later, not-yet-completed step is blocked.
    if (index <= highestStepReached) setStepIndex(index);
  }

  async function handleSubmit() {
    const stepErrors = validateStep(stepIndex, values);
    markStepTouched(stepIndex);
    if (Object.keys(stepErrors).length > 0) {
      setErrors((prev) => ({ ...prev, ...stepErrors }));
      return;
    }

    setSubmitting(true);
    setSubmitError('');
    try {
      const application = draftReferenceId
        ? await updateDraft(draftReferenceId, toDraftPayload(values)).then(() => submitDraft(draftReferenceId))
        : await submitApplication(values);
      onSubmitted(application);
    } catch (err) {
      if (err.fieldErrors && Object.keys(err.fieldErrors).length > 0) {
        setErrors((prev) => ({ ...prev, ...err.fieldErrors }));
        setTouched((prev) => {
          const next = { ...prev };
          for (const field of Object.keys(err.fieldErrors)) next[field] = true;
          return next;
        });
        const firstBadStep = Object.keys(err.fieldErrors)
          .map(findStepForField)
          .filter((idx) => idx !== -1)
          .sort((a, b) => a - b)[0];
        if (firstBadStep !== undefined) {
          setStepIndex(firstBadStep);
          setHighestStepReached((prev) => Math.max(prev, firstBadStep));
        }
      } else {
        setSubmitError(err.message || 'Something went wrong. Please try again.');
      }
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSaveForLater() {
    setSaving(true);
    setSaveError('');
    setSaveMessage('');
    try {
      const draft = draftReferenceId
        ? await updateDraft(draftReferenceId, toDraftPayload(values))
        : await createDraft(toDraftPayload(values));
      setDraftReferenceId(draft.reference_id);
      setSaveMessage(`Saved. Your reference ID is ${draft.reference_id} — use it to resume later.`);
    } catch (err) {
      setSaveError(err.message || 'Could not save your progress. Please try again.');
    } finally {
      setSaving(false);
    }
  }

  const StepComponent = STEP_COMPONENTS[stepIndex];
  const isLastStep = stepIndex === STEPS.length - 1;

  return (
    <div className="application-form">
      <ProgressIndicator
        currentStep={stepIndex}
        highestStepReached={highestStepReached}
        onStepClick={goToStep}
      />

      <StepComponent values={values} errors={errors} touched={touched} onChange={updateField} />

      {submitError && (
        <p className="form-error" role="alert">
          {submitError}
        </p>
      )}

      <div className="form-nav">
        {stepIndex > 0 && (
          <button type="button" onClick={goBack} disabled={submitting}>
            Back
          </button>
        )}
        {!isLastStep && (
          <button type="button" onClick={goNext} disabled={submitting}>
            Next
          </button>
        )}
        {isLastStep && (
          <button type="button" onClick={handleSubmit} disabled={submitting}>
            {submitting ? 'Submitting…' : 'Submit Application'}
          </button>
        )}
      </div>

      {/* US-03: available on every step — a draft is allowed to be
          incomplete by definition, so this never runs the full-form
          validation handleSubmit does. */}
      <div className="save-for-later">
        <button type="button" className="link-button" onClick={handleSaveForLater} disabled={saving || submitting}>
          {saving ? 'Saving…' : 'Save and finish later'}
        </button>
        {saveMessage && (
          <p className="save-for-later__message" role="status">
            {saveMessage}
          </p>
        )}
        {saveError && (
          <p className="form-error" role="alert">
            {saveError}
          </p>
        )}
      </div>
    </div>
  );
}
