const { response, method, suffix, proxyToBackend } = require('./_common');

exports.handler = async (event) => {
  const proxied = await proxyToBackend(event, 'auth', '/api/auth', '/auth');
  if (proxied) return proxied;
  const s = suffix(event, 'auth', '/api/auth');
  if (method(event) === 'OPTIONS') return response(204, {});
  if (method(event) === 'GET' && s === '/status') return response(200, { tiktok: false, youtube_shorts: false, instagram: false, authenticated: false, demo: true });
  if (s.endsWith('/start')) return { statusCode: 302, headers: { location: '/', 'cache-control': 'no-store' }, body: '' };
  if (['/login', '/signup'].includes(s) && method(event) === 'POST') return response(501, { error: 'backend_not_configured', message: 'Set BACKEND_URL in Netlify to enable live authentication.' });
  return response(404, { error: 'not_found', message: 'Auth endpoint not found' });
};
