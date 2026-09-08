// Minimal reviewer session storage — an addition on top of the PRD (see
// backend/app/auth.py). Deliberately just localStorage, no context
// provider or state library: this app doesn't use one anywhere else.

const TOKEN_KEY = 'onboardiq_reviewer_token';
const USERNAME_KEY = 'onboardiq_reviewer_username';

export function getReviewerSession() {
  const token = localStorage.getItem(TOKEN_KEY);
  const username = localStorage.getItem(USERNAME_KEY);
  return token && username ? { token, username } : null;
}

export function setReviewerSession(token, username) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USERNAME_KEY, username);
}

export function clearReviewerSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USERNAME_KEY);
}

export function reviewerAuthHeader() {
  const session = getReviewerSession();
  return session ? { Authorization: `Bearer ${session.token}` } : {};
}
