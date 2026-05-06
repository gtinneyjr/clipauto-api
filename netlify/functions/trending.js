const { response, proxyToBackend } = require('./_common');

exports.handler = async (event) => {
  const proxied = await proxyToBackend(event, 'trending', '/api/trending', '/trending');
  if (proxied) return proxied;
  return response(200, { fetched_at: new Date().toISOString(), videos: [] });
};
