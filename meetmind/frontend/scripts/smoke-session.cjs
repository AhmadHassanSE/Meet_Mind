// Shared sign-in helpers for browser smoke checks.
// Real-backend scripts sign up (first run) or sign in with a fixed test account;
// mocked-API scripts answer the session endpoints with an organizer/admin fixture.
const ACCOUNT = { email: 'smoke@meetmind.test', name: 'Smoke Organizer', password: 'smoke-test-password' };
const ME = { id: 'smoke-user', email: ACCOUNT.email, name: ACCOUNT.name, role: 'organizer', is_admin: true, organizer_request: null };
const ACCESS = { role: 'organizer', can_organize: true, owned_items: [], admin_override: false };
const RIGHTS = { can_edit: true, can_decide: true, can_override: false, assignee_id: null };

async function signIn(page, base) {
  const signup = await page.request.post(base + '/api/auth/signup', { data: ACCOUNT });
  if (signup.status() !== 201) {
    const login = await page.request.post(base + '/api/auth/login', { data: { email: ACCOUNT.email, password: ACCOUNT.password } });
    if (!login.ok()) throw new Error('Smoke sign-in failed: ' + login.status() + ' ' + await login.text());
  }
  await page.goto(base);
}

// Returns mocked session data for a request URL, or undefined for other routes.
function sessionData(url) {
  const { pathname, search } = new URL(url);
  if (pathname === '/api/auth/me') return ME;
  if (pathname === '/api/users/directory') return [{ id: ME.id, name: ME.name, email: ME.email, role: ME.role }];
  if (pathname === '/api/artifacts' && search.includes('awaiting_me')) return [];
  if (pathname.endsWith('/members')) return [{ id: ME.id, name: ME.name, email: ME.email, role: 'organizer' }];
  return undefined;
}

module.exports = { ACCOUNT, ACCESS, RIGHTS, signIn, sessionData };
