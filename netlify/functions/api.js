const { response, proxyToBackend } = require('./_common');

exports.handler = async (event) => {
  const proxied = await proxyToBackend(event, 'api', '/api', '');
  if (proxied) return proxied;
  return response(404, { error: 'not_found', message: 'API route is not configured. Set BACKEND_URL or add a Netlify function for this path.' });
};
