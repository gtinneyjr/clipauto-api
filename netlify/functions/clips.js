const { response, method, proxyToBackend } = require('./_common');

const demoClips = [
  { id: 1, title: 'Demo viral clip', channel: 'ClipAuto', youtube_video_id: 'dQw4w9WgXcQ', viral_score: 92, start_second: 0, end_second: 45, status: 'ready' }
];

exports.handler = async (event) => {
  const proxied = await proxyToBackend(event, 'clips', '/api/clips', '/clips');
  if (proxied) return proxied;
  if (method(event) === 'OPTIONS') return response(204, {});
  if (method(event) === 'GET') return response(200, demoClips);
  return response(202, { status: 'accepted', demo: true });
};
