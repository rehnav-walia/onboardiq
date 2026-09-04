import { STEPS } from '../validation.js';

export default function ProgressIndicator({ currentStep, highestStepReached, onStepClick }) {
  return (
    <nav className="progress-indicator" aria-label="Application progress">
      <p className="progress-status">
        Step {currentStep + 1} of {STEPS.length}: {STEPS[currentStep].label}
      </p>
      <ol>
        {STEPS.map((step, index) => {
          const status =
            index === currentStep ? 'active' : index < currentStep ? 'complete' : 'upcoming';
          return (
            <li key={step.label} className={status}>
              <button
                type="button"
                disabled={index > highestStepReached}
                aria-current={index === currentStep ? 'step' : undefined}
                onClick={() => onStepClick(index)}
              >
                {index + 1}. {step.label}
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
