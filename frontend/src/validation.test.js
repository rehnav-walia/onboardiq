import assert from 'node:assert/strict';
import { test } from 'node:test';

import { STEPS, findStepForField, validateField, validateStep } from './validation.js';

// Formats in LOCAL date parts (not toISOString, which converts to UTC and
// can shift the calendar date by a day depending on the machine's
// timezone) — matches how validateField itself builds "today" internally,
// via `new Date()` + setHours(0,0,0,0), never UTC.
function isoDate(daysFromToday) {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() + daysFromToday);
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

// --- full_name / id_number / address: required, mirrors
// backend/app/validators.py's require_non_blank (same exact message text,
// e.g. "Full name is required.") -------------------------------------------

for (const [field, label] of [
  ['full_name', 'Full name'],
  ['id_number', 'ID number'],
  ['address', 'Address'],
]) {
  test(`${field}: rejects blank/whitespace-only, accepts a real value`, () => {
    assert.equal(validateField(field, ''), `${label} is required.`);
    assert.equal(validateField(field, '   '), `${label} is required.`);
    assert.equal(validateField(field, 'A real value'), '');
  });
}

// --- date_of_birth: mirrors validators.validate_date_of_birth, which only
// rejects a FUTURE date — nothing else. Deliberately does NOT reject a
// minor: minimum age is advisory-only (app/rules.py check_minimum_age),
// computed post-submission as a risk factor a reviewer can still override,
// never a submission-blocking rule (CLAUDE.md non-negotiable #1). Asserting
// that here guards against ever "inventing" an age-floor the backend
// doesn't actually enforce at intake. -----------------------------------

test('date_of_birth: rejects a blank value', () => {
  assert.equal(validateField('date_of_birth', ''), 'Date of birth is required.');
});

test('date_of_birth: accepts today (boundary — not in the future, so valid)', () => {
  assert.equal(validateField('date_of_birth', isoDate(0)), '');
});

test('date_of_birth: accepts a date 10 years ago (under 18) — age is never checked at intake', () => {
  const tenYearsAgo = new Date();
  tenYearsAgo.setHours(0, 0, 0, 0);
  tenYearsAgo.setFullYear(tenYearsAgo.getFullYear() - 10);
  const year = tenYearsAgo.getFullYear();
  const month = String(tenYearsAgo.getMonth() + 1).padStart(2, '0');
  const day = String(tenYearsAgo.getDate()).padStart(2, '0');
  assert.equal(validateField('date_of_birth', `${year}-${month}-${day}`), '');
});

test('date_of_birth: accepts a clearly past adult date', () => {
  assert.equal(validateField('date_of_birth', '1990-05-15'), '');
});

test('date_of_birth: rejects tomorrow (boundary — first invalid day)', () => {
  assert.equal(validateField('date_of_birth', isoDate(1)), 'Date of birth cannot be in the future.');
});

test('date_of_birth: rejects a far-future date', () => {
  assert.equal(validateField('date_of_birth', isoDate(3650)), 'Date of birth cannot be in the future.');
});

// --- email: mirrors the common-case shape pydantic's EmailStr requires
// (something@something.something, no whitespace) — see the validation.js
// module comment for the documented gap against EmailStr's fuller RFC
// checks on malformed edge cases. ------------------------------------------

test('email: rejects blank', () => {
  assert.equal(validateField('email', ''), 'Email is required.');
});

test('email: rejects a value with no @ or no domain dot', () => {
  assert.equal(validateField('email', 'not-an-email'), 'Enter a valid email address, e.g. name@example.com.');
  assert.equal(validateField('email', 'name@example'), 'Enter a valid email address, e.g. name@example.com.');
});

test('email: accepts a typical address', () => {
  assert.equal(validateField('email', 'jane.doe@example.com'), '');
});

// --- phone: mirrors validators.PHONE_PATTERN + the 7-15 digit-count check
// exactly (same regex, same inclusive bounds). -----------------------------

test('phone: rejects blank', () => {
  assert.equal(validateField('phone', ''), 'Phone number is required.');
});

test('phone: rejects 6 digits (boundary — one below the 7-digit minimum)', () => {
  assert.equal(validateField('phone', '123456'), 'Enter a valid phone number, e.g. +1 555 123 4567.');
});

test('phone: accepts 7 digits (boundary — the minimum)', () => {
  assert.equal(validateField('phone', '5551234'), '');
});

test('phone: accepts 15 digits (boundary — the maximum)', () => {
  assert.equal(validateField('phone', '123456789012345'), '');
});

test('phone: rejects 16 digits (boundary — one past the maximum)', () => {
  assert.equal(validateField('phone', '1234567890123456'), 'Enter a valid phone number, e.g. +1 555 123 4567.');
});

test('phone: rejects letters', () => {
  assert.equal(validateField('phone', 'abc1234567'), 'Enter a valid phone number, e.g. +1 555 123 4567.');
});

test('phone: accepts a realistic formatted number', () => {
  assert.equal(validateField('phone', '+1 (555) 123-4567'), '');
});

// --- account_type: a plain presence check — the dropdown only ever offers
// the two real enum values, so there's no reachable "wrong value" case. ----

test('account_type: rejects blank', () => {
  assert.equal(validateField('account_type', ''), 'Please select an account type.');
});

test('account_type: accepts SAVINGS and CURRENT', () => {
  assert.equal(validateField('account_type', 'SAVINGS'), '');
  assert.equal(validateField('account_type', 'CURRENT'), '');
});

// --- validateStep / findStepForField -----------------------------------

test('validateStep returns an error only for the invalid fields on that step', () => {
  const values = { full_name: '', date_of_birth: '1990-05-15', id_number: 'A1' };
  const errors = validateStep(0, values);
  assert.deepEqual(Object.keys(errors), ['full_name']);
});

test('validateStep returns no errors once every field on the step is valid', () => {
  const values = { full_name: 'Jane Doe', date_of_birth: '1990-05-15', id_number: 'A1234567' };
  assert.deepEqual(validateStep(0, values), {});
});

test('findStepForField maps each field to its own step index', () => {
  assert.equal(findStepForField('full_name'), 0);
  assert.equal(findStepForField('email'), 1);
  assert.equal(findStepForField('account_type'), 2);
  assert.equal(findStepForField('not_a_real_field'), -1);
});

test('every field declared in STEPS is handled by validateField (no silent pass-through)', () => {
  for (const step of STEPS) {
    for (const field of step.fields) {
      // An empty string must produce a message for every real field here —
      // if validateField's switch were missing a case, this would silently
      // return '' (its default) for a value that should be invalid.
      assert.notEqual(validateField(field, ''), '', `expected ${field} to reject a blank value`);
    }
  }
});
