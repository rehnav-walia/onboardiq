const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api';

class ApiError extends Error {
  constructor(message, fieldErrors = {}) {
    super(message);
    this.fieldErrors = fieldErrors;
  }
}

async function parseErrorResponse(response) {
  const data = await response.json().catch(() => ({}));
  return new ApiError(
    data.message || 'Something went wrong. Please try again.',
    data.errors || {}
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

export async function uploadDocument(referenceId, file) {
  const formData = new FormData();
  formData.append('file', file);
  const response = await fetch(`${API_BASE}/applications/${encodeURIComponent(referenceId)}/documents`, {
    method: 'POST',
    body: formData,
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

export function getApplication(referenceId) {
  return getJson(`${API_BASE}/applications/${encodeURIComponent(referenceId)}`);
}

export function listDocuments(referenceId) {
  return getJson(`${API_BASE}/applications/${encodeURIComponent(referenceId)}/documents`);
}

export function getExtraction(referenceId) {
  return getJson(`${API_BASE}/applications/${encodeURIComponent(referenceId)}/extraction`);
}

export function getAuditLog(referenceId) {
  return getJson(`${API_BASE}/applications/${encodeURIComponent(referenceId)}/audit-log`);
}

export function getDecision(referenceId) {
  return getJson(`${API_BASE}/applications/${encodeURIComponent(referenceId)}/decision`);
}

export function getQueue(limit, offset) {
  return getJson(`${API_BASE}/reviewer/queue?limit=${limit}&offset=${offset}`);
}

export async function submitDecision(referenceId, payload) {
  const response = await fetch(`${API_BASE}/applications/${encodeURIComponent(referenceId)}/decision`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw await parseErrorResponse(response);
  }
  return response.json();
}
