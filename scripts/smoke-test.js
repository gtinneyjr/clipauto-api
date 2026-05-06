const fs = require('fs');
const html = fs.readFileSync('public/index.html', 'utf8');
const required = ['page-channels', 'page-clips', 'function hydrateLazyPage', 'channels/connect'];
const missing = required.filter((needle) => !html.includes(needle));
if (missing.length) {
  console.error('Missing frontend markers:', missing.join(', '));
  process.exit(1);
}
for (const file of ['netlify.toml', 'netlify/functions/channels.js', 'netlify/functions/auth.js', 'netlify/functions/clips.js']) {
  if (!fs.existsSync(file)) {
    console.error('Missing required file:', file);
    process.exit(1);
  }
}
console.log('Smoke test passed');
