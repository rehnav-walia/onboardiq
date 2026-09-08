// Client-side mirror of backend/app/validators.py. This is a UX convenience
// only (US-04) — the backend re-checks everything independently, because a
// crafted API request bypasses this file entirely (US-01 DoD).

export const ACCOUNT_TYPES = [
  { value: 'SAVINGS', label: 'Savings Account' },
  { value: 'CURRENT', label: 'Current Account' },
];

// US-08: the controlled list an applicant declares a document as — kept in
// sync with backend/app/models.py's DocumentType enum.
export const DOCUMENT_TYPES = [
  { value: 'PASSPORT', label: 'Passport' },
  { value: 'NATIONAL_ID', label: 'National ID' },
  { value: 'DRIVING_LICENCE', label: 'Driving Licence' },
];

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const PHONE_PATTERN = /^\+?[0-9\s\-()]{7,20}$/;

export function validateField(name, rawValue) {
  const value = rawValue ?? '';

  switch (name) {
    case 'full_name':
      return value.trim() ? '' : 'Full name is required.';

    case 'date_of_birth': {
      if (!value) return 'Date of birth is required.';
      const dob = new Date(`${value}T00:00:00`);
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      if (Number.isNaN(dob.getTime())) return 'Enter a valid date.';
      if (dob > today) return 'Date of birth cannot be in the future.';
      return '';
    }

    case 'id_number':
      return value.trim() ? '' : 'ID number is required.';

    case 'address':
      return value.trim() ? '' : 'Address is required.';

    case 'email': {
      if (!value.trim()) return 'Email is required.';
      return EMAIL_PATTERN.test(value.trim())
        ? ''
        : 'Enter a valid email address, e.g. name@example.com.';
    }

    case 'phone': {
      if (!value.trim()) return 'Phone number is required.';
      const digitCount = value.replace(/\D/g, '').length;
      if (!PHONE_PATTERN.test(value) || digitCount < 7 || digitCount > 15) {
        return 'Enter a valid phone number, e.g. +1 555 123 4567.';
      }
      return '';
    }

    case 'account_type':
      return value ? '' : 'Please select an account type.';

    default:
      return '';
  }
}

export const STEPS = [
  { label: 'Personal Details', fields: ['full_name', 'date_of_birth', 'id_number'] },
  { label: 'Address & Contact', fields: ['address', 'email', 'phone'] },
  { label: 'Account Type', fields: ['account_type'] },
];

export function validateStep(stepIndex, values) {
  const errors = {};
  for (const field of STEPS[stepIndex].fields) {
    const message = validateField(field, values[field]);
    if (message) errors[field] = message;
  }
  return errors;
}

export function findStepForField(fieldName) {
  return STEPS.findIndex((step) => step.fields.includes(fieldName));
}

export const EMPTY_APPLICATION = {
  full_name: '',
  date_of_birth: '',
  id_number: '',
  address: '',
  email: '',
  phone: '',
  account_type: '',
};
