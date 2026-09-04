import { useState } from 'react';

import { submitApplication } from '../api.js';
import { EMPTY_APPLICATION, STEPS, findStepForField, validateField, validateStep } from '../validation.js';
import ProgressIndicator from './ProgressIndicator.jsx';
import StepAccountType from './steps/StepAccountType.jsx';
import StepAddressContact from './steps/StepAddressContact.jsx';
import StepPersonalDetails from './steps/StepPersonalDetails.jsx';

const STEP_COMPONENTS = [StepPersonalDetails, StepAddressContact, StepAccountType];

export default function ApplicationForm({ onSubmitted }) {
  // Single source of truth for all step data (US-02 DoD) — this is also
  // what keeps entered values intact across a failed validation (US-01 DoD):
  // nothing here ever gets cleared, only added to.
  const [values, setValues] = useState(EMPTY_APPLICATION);
  const [errors, setErrors] = useState({});
  const [touched, setTouched] = useState({});
  const [stepIndex, setStepIndex] = useState(0);
  const [highestStepReached, setHighestStepReached] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');

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
      const application = await submitApplication(values);
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
    </div>
  );
}
