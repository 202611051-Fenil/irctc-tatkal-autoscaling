// Tatkal PoC API - zero dependencies, stateless.
const http = require('http');
const crypto = require('crypto');
const cluster = require('cluster');
const os = require('os');
const fs = require('fs');
const path = require('path');

const PORT = process.env.PORT || 3000;
const HOST_NAME = process.env.HOST_NAME || os.hostname();
// Set by infra/user-data.sh from the EC2 metadata service (shown on the dashboard).
const AZ = process.env.AZ || 'unknown';
const INSTANCE_ID = process.env.INSTANCE_ID || 'unknown';
// Higher = more CPU per /book call. Tune so one call takes ~60-100 ms.
const WORK_ITERATIONS = parseInt(process.env.WORK_ITERATIONS || '100000', 10);

// Use every vCPU. A single Node process would cap a 2-vCPU t3.micro at ~50% CPU.
if (cluster.isPrimary) {
  const n = os.cpus().length;
  for (let i = 0; i < n; i++) cluster.fork();
  cluster.on('exit', () => cluster.fork());
  console.log(`primary up, ${n} workers, port ${PORT}`);
} else {
  const send = (res, code, body) => {
    res.writeHead(code, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(body));
  };

  // Dashboard page (read once per worker). Served from the same address as the API,
  // so the browser can call /whoami and /book without any cross-site problems.
  let dashboardHtml = '<h1>dashboard.html not found</h1>';
  try { dashboardHtml = fs.readFileSync(path.join(__dirname, 'dashboard.html'), 'utf8'); } catch (e) {}

  // Who am I? Used by the dashboard to see which server and zone answered.
  const who = () => ({ server: HOST_NAME, instance_id: INSTANCE_ID, az: AZ, pid: process.pid });

  http.createServer((req, res) => {
    if (req.url === '/health') return send(res, 200, { ok: true });

    if (req.url === '/dashboard') {
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
      return res.end(dashboardHtml);
    }

    if (req.url.startsWith('/whoami')) {
      return send(res, 200, { ...who(), uptime_s: Math.round(process.uptime()), time: Date.now() });
    }

    // Home page: so opening the bare load balancer URL shows a useful answer.
    if (req.url === '/' || req.url === '/tatkal') {
      return send(res, 200, {
        status: 'Tatkal Ticket Available',
        ...who(),
        endpoints: ['/tatkal', '/book', '/health', '/whoami', '/dashboard'],
      });
    }

    if (req.url === '/book') {
      // Fake CPU work: stands in for captcha / payment / seat validation.
      // Async version runs on the libuv thread pool, so the main thread stays
      // free and /health always answers, even when the CPU is saturated.
      const t0 = Date.now();
      crypto.pbkdf2('seat-validation', 'salt', WORK_ITERATIONS, 64, 'sha512', (err) => {
        if (err) return send(res, 500, { error: 'work failed' });
        send(res, 200, {
          status: 'Booking Confirmed',
          pnr: Math.floor(1e9 + Math.random() * 9e9),
          ...who(),
          work_ms: Date.now() - t0,
        });
      });
      return;
    }

    send(res, 404, { error: 'not found' });
  }).listen(PORT);
}