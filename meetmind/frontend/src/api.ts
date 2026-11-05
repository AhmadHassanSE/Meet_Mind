import { useEffect, useState } from 'react';

export type Me = { id: string; email: string; name: string; role: 'member' | 'organizer'; is_admin: boolean;
  organizer_request: { id: string; status: string; reason: string; note: string | null; created_at: string } | null };
export type Access = { role: 'organizer' | 'owner' | 'viewer' | 'admin'; can_organize: boolean; owned_items: string[]; admin_override: boolean };
export type DirectoryUser = { id: string; name: string; email: string; role: string };

export const SIGNED_OUT = 'meetmind:signed-out';

/** fetch for the MeetMind API: adds the CSRF header and reports expired sessions. */
export async function apiFetch(input: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers);
  headers.set('X-Requested-With', 'meetmind');
  const response = await fetch(input, { ...init, headers, credentials: 'same-origin' });
  if (response.status === 401 && !input.startsWith('/api/auth/')) window.dispatchEvent(new Event(SIGNED_OUT));
  return response;
}

export async function api<T>(path: string, method = 'GET', body?: object): Promise<T> {
  const response = await apiFetch(`/api${path}`, { method, headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined });
  const value = response.status === 204 ? null : await response.json().catch(() => ({}));
  if (!response.ok) throw Object.assign(new Error(detail(value)), { status: response.status });
  return value as T;
}

function detail(value: { detail?: unknown } | null) {
  const raw = value?.detail;
  if (typeof raw === 'string') return raw;
  if (Array.isArray(raw) && raw[0]?.msg) return String(raw[0].msg).replace(/^Value error, /, '');
  return 'Request failed. Check your input and try again.';
}

/** Minimal path router: the current path, and navigate() without a page reload. */
export function useRoute(): [string, (path: string) => void] {
  const [path, setPath] = useState(window.location.pathname);
  useEffect(() => {
    const update = () => setPath(window.location.pathname);
    window.addEventListener('popstate', update);
    return () => window.removeEventListener('popstate', update);
  }, []);
  return [path, (next: string) => {
    if (next !== window.location.pathname) window.history.pushState(null, '', next);
    setPath(next); window.scrollTo(0, 0);
  }];
}
