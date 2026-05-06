const http = require('http');
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const publicDir = path.join(root, 'public');
const functionsDir = path.join(root, 'netlify', 'functions');
const port = Number(process.env.PORT || 4173);

const routes = [
  [/^\/api\/channels(?:\/(.*))?$/, 'channels'],
  [/^\/api\/clips(?:\/(.*))?$/, 'clips'],
  [/^\/api\/auth(?:\/(.*))?$/, 'auth'],
  [/^\/api\/trending$/, 'trending'],
  [/^\/api\/platforms$/, 'platforms'],
  [/^\/api\/(.*)$/, 'api'],
];

function send(res, status, headers, body) {
  res.writeHead(status, headers);
  res.end(body || '');
}

function collect(req) {
  return new Promise((resolve) => {
    let body = '';
    req.on('data', (chunk) => { body += chunk; });
    req.on('end', () => resolve(body));
  });
}

async function handleFunction(req, res, pathname, query) {
  for (const [regex, name] of routes) {
    if (regex.test(pathname)) {
      const mod = require(path.join(functionsDir, `${name}.js`));
      const body = await collect(req);
      const result = await mod.handler({
        path: pathname,
        rawQueryString: query.startsWith('?') ? query.slice(1) : query,
        httpMethod: req.method,
        headers: req.headers,
        body
      });
      return send(res, result.statusCode || 200, result.headers || {}, result.body || '');
    }
  }
  return false;
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host}`);
  if (url.pathname.startsWith('/api/')) {
    return handleFunction(req, res, url.pathname, url.search);
  }

  let filePath = path.join(publicDir, decodeURIComponent(url.pathname));
  if (url.pathname === '/' || !fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
    filePath = path.join(publicDir, 'index.html');
  }
  const ext = path.extname(filePath);
  const contentType = ext === '.html' ? 'text/html; charset=utf-8' : 'application/octet-stream';
  send(res, 200, { 'content-type': contentType }, fs.readFileSync(filePath));
});

server.listen(port, '0.0.0.0', () => console.log(`local Netlify-like test server on ${port}`));
