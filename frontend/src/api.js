import { reviewerAuthHeader } from './reviewerAuth.js';

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api';

class ApiError extends Error {
  constructor(message, fieldErrors = {}, status = null) {
    super(message);
    this.fieldErrors = fieldErrors;
    this.status = status;
  }
}

async function parseErrorResponse(response) {
  const data = await response.json().catch(() => ({}));
  return new ApiError(
    data.message || 'Something went wrong. Please try again.',
    data.errors || {},
    response.status
  );
}

export async function submitApplication(payload) {
  const response = await fetch(`${API_BASE}/applications`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw await parseErrorResponse(response);
  }
  return response.json();
}

export async function uploadDocument(referenceId, file, declaredType) {
  const formData = new FormData();
  formData.append('file', file);
  if (declaredType) formData.append('declared_type', declaredType);
  const response = await fetch(`${API_BASE}/applications/${encodeURIComponent(referenceId)}/documents`, {
    method: 'POST',
    body: formData,
  });
  if (!response.ok) {
    throw await parseErrorResponse(response);
  }
  return response.json();
}

export async function createDraft(values) {
  const response = await fetch(`${API_BASE}/applications/draft`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(values),
  });
  if (!response.ok) {
    throw await parseErrorResponse(response);
  }
  return response.json();
}

export async function updateDraft(referenceId, values) {
  const response = await fetch(`${API_BASE}/applications/draft/${encodeURIComponent(referenceId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(values),
  });
  if (!response.ok) {
    throw await parseErrorResponse(response);
  }
  return response.json();
}

export async function submitDraft(referenceId) {
  const response = await fetch(`${API_BASE}/applications/draft/${encodeURIComponent(referenceId)}/submit`, {
    method: 'POST',
  });
  if (!response.ok) {
    throw await parseErrorResponse(response);
  }
  return response.json();
}

export function documentFileUrl(referenceId, documentId) {
  return `${API_BASE}/applications/${encodeURIComponent(referenceId)}/documents/${documentId}/file`;
}

async function getJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw await parseErrorResponse(response);
  }
  return response.json();
}

// Reviewer-only reads (addition on top of the PRD — see backend/app/auth.py):
// extraction, risk, the audit log (and its export), and decision history
// are never shown to an applicant, so these always send the reviewer's
// session header. Contrast with getJson above, used for the handful of
// endpoints the applicant-facing status view also depends on (the bare
// application record, the document list, the current/singular decision).
async function getJsonAsReviewer(url) {
  const response = await fetch(url, { headers: { ...reviewerAuthHeader() } });
  if (!response.ok) {
    throw await parseErrorResponse(response);
  }
  return response.json();
}

export function getApplication(referenceId) {
  return getJson(`${API_BASE}/applications/${encodeURIComponent(referenceId)}`);
}

export function listDocuments(referenceId) {
  return getJson(`${API_BASE}/applications/${encodeURIComponent(referenceId)}/documents`);
}

export function getExtraction(referenceId) {
  return getJsonAsReviewer(`${API_BASE}/applications/${encodeURIComponent(referenceId)}/extraction`);
}

export function getAuditLog(referenceId) {
  return getJsonAsReviewer(`${API_BASE}/applications/${encodeURIComponent(referenceId)}/audit-log`);
}

export function getDecision(referenceId) {
  return getJson(`${API_BASE}/applications/${encodeURIComponent(referenceId)}/decision`);
}

export function getDecisions(referenceId) {
  return getJsonAsReviewer(`${API_BASE}/applications/${encodeURIComponent(referenceId)}/decisions`);
}

// Reviewer-only, and unlike the JSON reads above, this triggers a file
// download rather than returning data — a plain `<a href>` can't carry the
// reviewer's Authorization header, so this fetches the file itself (with
// the header) and hands back a Blob for the caller to save.
export async function fetchAuditExport(referenceId, format) {
  const url = `${API_BASE}/applications/${encodeURIComponent(referenceId)}/audit-log/export?format=${format}`;
  const response = await fetch(url, { headers: { ...reviewerAuthHeader() } });
  if (!response.ok) {
    throw await parseErrorResponse(response);
  }
  const disposition = response.headers.get('content-disposition') || '';
  const match = disposition.match(/filename="([^"]+)"/);
  const filename = match ? match[1] : `${referenceId}_audit_export.${format}`;
  return { blob: await response.blob(), filename };
}

export async function getQueue(params) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') {
      query.set(key, value);
    }
  }
  // Reviewer login required (addition on top of the PRD — see
  // backend/app/auth.py). Applicant-facing calls elsewhere in this file
  // never send this header.
  const response = await fetch(`${API_BASE}/reviewer/queue?${query.toString()}`, {
    headers: { ...reviewerAuthHeader() },
  });
  if (!response.ok) {
    throw await parseErrorResponse(response);
  }
  return response.json();
}

export function getQueueStats() {
  // Reviewer login required, same as getQueue — covers statuses (APPROVED,
  // REJECTED) that a page of queue results never includes at all, so the
  // summary bar can't be derived from getQueue's own response.
  return getJsonAsReviewer(`${API_BASE}/reviewer/queue/stats`);
}

export function getRisk(referenceId) {
  return getJsonAsReviewer(`${API_BASE}/applications/${encodeURIComponent(referenceId)}/risk`);
}

export async function submitDecision(referenceId, payload) {
  // The logged-in reviewer's identity is attached server-side from this
  // header — the request body carries only `action`/`reasoning`, never a
  // free-text reviewer id (see backend/app/schemas.py DecisionCreate).
  const response = await fetch(`${API_BASE}/applications/${encodeURIComponent(referenceId)}/decision`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...reviewerAuthHeader() },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw await parseErrorResponse(response);
  }
  return response.json();
}

export async function reviewerLogin(username, password) {
  const response = await fetch(`${API_BASE}/auth/reviewer/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  if (!response.ok) {
    throw await parseErrorResponse(response);
  }
  return response.json();
}

export async function reviewerLogout() {
  await fetch(`${API_BASE}/auth/reviewer/logout`, {
    method: 'POST',
    headers: { ...reviewerAuthHeader() },
  }).catch(() => {});
  // Best-effort — the client-side session is cleared regardless (see
  // reviewerAuth.clearReviewerSession), so a failed network call here
  // never traps the user in a logged-in-looking but broken state.
}

export async function askPolicyQuestion(question) {
  const response = await fetch(`${API_BASE}/policy-assistant/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  });
  if (!response.ok) {
    throw await parseErrorResponse(response);
  }
  return response.json();
}
