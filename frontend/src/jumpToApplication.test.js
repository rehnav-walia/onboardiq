import assert from 'node:assert/strict';
import { test } from 'node:test';

import { normalizeReferenceId, resolveJumpTarget } from './jumpToApplication.js';

test('normalizeReferenceId trims whitespace and upper-cases', () => {
  assert.equal(normalizeReferenceId('  onb-2026-00005  '), 'ONB-2026-00005');
  assert.equal(normalizeReferenceId('Onb-2026-00005'), 'ONB-2026-00005');
});

test('resolveJumpTarget navigates to the application when it is found, case-insensitively', async () => {
  const calls = [];
  const fetchApplication = async (referenceId) => {
    calls.push(referenceId);
    return { reference_id: referenceId };
  };

  const result = await resolveJumpTarget('onb-2026-00005', fetchApplication);

  assert.deepEqual(result, { ok: true, path: '/reviewer/ONB-2026-00005' });
  // The API is called with the normalized (upper-case) id, not the raw
  // lower-case input — proves the case-insensitivity happens before lookup.
  assert.deepEqual(calls, ['ONB-2026-00005']);
});

test('resolveJumpTarget surfaces a clear error when the application does not exist, without navigating', async () => {
  const fetchApplication = async () => {
    throw new Error('No application found with that reference ID.');
  };

  const result = await resolveJumpTarget('ONB-2026-99999', fetchApplication);

  assert.deepEqual(result, { ok: false, error: 'No application found with that reference ID.' });
});

test('resolveJumpTarget falls back to a generic message if the error has none', async () => {
  const fetchApplication = async () => {
    throw new Error();
  };

  const result = await resolveJumpTarget('ONB-2026-99999', fetchApplication);

  assert.equal(result.ok, false);
  assert.equal(result.error, 'No application found with that reference ID.');
});

test('resolveJumpTarget rejects a blank/whitespace-only input without calling the API', async () => {
  let called = false;
  const fetchApplication = async () => {
    called = true;
  };

  const result = await resolveJumpTarget('   ', fetchApplication);

  assert.equal(result.ok, false);
  assert.equal(called, false);
});
