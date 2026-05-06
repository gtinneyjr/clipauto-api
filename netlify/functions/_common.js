const JSON_HEADERS = {
  'content-type': 'application/json; charset=utf-8',
  'cache-control': 'no-store'
};

function response(statusCode, body, extraHeaders = {}) {
  return { statusCode, headers: { ...JSON_HEADERS, ...extraHeaders }, body: JSON.stringify(body) };
}

function textResponse(statusCode, text, contentType = 'application/json; charset=utf-8') {
  return { statusCode, headers: { 'content-type': contentType, 'cache-control': 'no-store' }, body: text };
}

function method(event) {
  return (event.httpMethod || 'GET').toUpperCase();
}

function suffix(event, functionName, apiPrefix) {
  const path = event.path || '';
  let s = '';
  const fnNeedle = `/.netlify/functions/${functionName}`;
  if (path.startsWith(fnNeedle)) s = path.slice(fnNeedle.length);
  else if (path.startsWith(apiPrefix)) s = path.slice(apiPrefix.length);
  if (!s) s = '';
  return s.startsWith('/') ? s : `/${s}`;
}

async function proxyToBackend(event, functionName, apiPrefix, backendPrefix) {
  const backend = (process.env.BACKEND_URL || '').replace(/\/$/, '');
  if (!backend) return null;
  const qs = event.rawQueryString ? `?${event.rawQueryString}` : '';
  const target = `${backend}${backendPrefix}${suffix(event, functionName, apiPrefix)}${qs}`;
  const headers = { 'content-type': event.headers?.['content-type'] || 'application/json' };
  const init = { method: method(event), headers };
  if (!['GET', 'HEAD'].includes(init.method)) init.body = event.body || '';
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), Number(process.env.BACKEND_PROXY_TIMEOUT_MS || 3500));
    init.signal = controller.signal;
    const res = await fetch(target, init);
    clearTimeout(timeout);
    const body = await res.text();
    return textResponse(res.status, body, res.headers.get('content-type') || 'application/json; charset=utf-8');
  } catch (err) {
    // If a configured backend is down or unreachable, return null so the individual
    // function can serve its safe public/demo fallback instead of timing out the UI.
    return null;
  }
}

module.exports = { response, method, suffix, proxyToBackend };
