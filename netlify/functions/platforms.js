const { response, proxyToBackend } = require('./_common');

exports.handler = async (event) => {
  const proxied = await proxyToBackend(event, 'platforms', '/api/platforms', '/auth/platforms');
  if (proxied) return proxied;
  return response(200, [
    { id: 'tiktok', name: 'TikTok', auth_url: '/api/auth/tiktok/start' },
    { id: 'youtube_shorts', name: 'YouTube Shorts', auth_url: '/api/auth/google/start' },
    { id: 'instagram', name: 'Instagram Reels', auth_url: '/api/auth/instagram/start' }
  ]);
};
