// Pure, framework-free logic behind the nav bar's "jump to application"
// search (see components/JumpToApplication.jsx). Kept separate from the
// React component specifically so the found/not-found behavior can be unit
// tested with Node's built-in test runner — this project has no frontend
// test framework (see package.json), and this one small piece of new logic
// doesn't justify adding one.

export function normalizeReferenceId(value) {
  return (value || '').trim().toUpperCase();
}

// `fetchApplication` is injected rather than imported directly, so this
// stays testable with a plain stub instead of mocking module internals —
// the real component passes api.getApplication; tests pass something else.
// Resolves to { ok: true, path } on success, { ok: false, error } otherwise
// — never throws, so the caller never needs its own try/catch.
export async function resolveJumpTarget(rawValue, fetchApplication) {
  const referenceId = normalizeReferenceId(rawValue);
  if (!referenceId) {
    return { ok: false, error: 'Enter a reference ID.' };
  }

  try {
    // Case-insensitive lookup: the backend compares reference IDs exactly
    // (see app/crud.py get_application_by_reference), so normalizing to
    // upper case here is what makes a lower/mixed-case paste still work.
    await fetchApplication(referenceId);
    return { ok: true, path: `/reviewer/${encodeURIComponent(referenceId)}` };
  } catch (err) {
    // Forwards the backend's own message (e.g. "No application found with
    // that reference ID.") rather than a separately maintained copy of it —
    // same pattern the rest of this app's error handling already follows
    // (see ReviewerQueuePage's and DecisionForm's use of err.message).
    return { ok: false, error: err.message || 'No application found with that reference ID.' };
  }
}
