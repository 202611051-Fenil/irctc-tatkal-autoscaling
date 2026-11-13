// Tatkal PoC API - zero dependencies, stateless.
const http = require('http');
const crypto = require('crypto');
const cluster = require('cluster');
const os = require('os');

const PORT = process.env.PORT || 3000;
const HOST_NAME = process.env.HOST_NAME || os.hostname();
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

  http.createServer((req, res) => {
    if (req.url === '/health') return send(res, 200, { ok: true });

    if (req.url === '/tatkal') {
      return send(res, 200, { status: 'Tatkal Ticket Available', server: HOST_NAME });
    }

    if (req.url === '/book') {
      // Fake CPU work: stands in for captcha / payment / seat validation.
      const t0 = Date.now();
      crypto.pbkdf2Sync('seat-validation', 'salt', WORK_ITERATIONS, 64, 'sha512');
      return send(res, 200, {
        status: 'Booking Confirmed',
        pnr: Math.floor(1e9 + Math.random() * 9e9),
        server: HOST_NAME,
        work_ms: Date.now() - t0,
      });
    }

    send(res, 404, { error: 'not found' });
  }).listen(PORT);
}
