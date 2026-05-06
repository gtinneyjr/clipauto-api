const { response, method, suffix, proxyToBackend } = require('./_common');

exports.handler = async (event) => {
  const proxied = await proxyToBackend(event, 'channels', '/api/channels', '/youtube');
  if (proxied) return proxied;

  const m = method(event);
  const s = suffix(event, 'channels', '/api/channels');
  if (m === 'OPTIONS') return response(204, {});
  if (m === 'GET' && (s === '/' || s === '')) return response(200, []);
  if (m === 'POST' && s === '/connect') {
    let payload = {};
    try { payload = JSON.parse(event.body || '{}'); } catch {}
    const handle = String(payload.url_or_handle || '@demo-channel').replace(/^https?:\/\/(www\.)?youtube\.com\//, '').replace(/^@?/, '@');
    return response(201, { id: Date.now(), channel_handle: handle, channel_title: handle.replace('@', '') || 'Demo Channel', is_active: true, clips_per_video: payload.clips_per_video || 3, demo: true });
  }
  if (m === 'DELETE') return response(204, {});
  return response(404, { error: 'not_found', message: 'Channel endpoint not found' });
};
