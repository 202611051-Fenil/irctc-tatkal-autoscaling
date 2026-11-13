// k6 load test shaped like a Tatkal opening: calm -> sudden spike -> hold -> drop.
// Run:  k6 run -e BASE_URL=http://<ALB-DNS> --out csv=results/k6_autoscale.csv loadtest/tatkal.js
import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE = __ENV.BASE_URL;

export const options = {
  stages: [
    { duration: '1m',  target: 10  },   // normal traffic before 10:00
    { duration: '30s', target: 100 }, // 10:00 AM - sudden spike
    { duration: '8m',  target: 100 }, // sustained peak (scale-out happens here)
    { duration: '1m',  target: 10  },   // rush is over
    { duration: '5m',  target: 10  },   // watch scale-in
  ],
  thresholds: {
    http_req_failed:   ['rate<0.05'],
    http_req_duration: ['p(95)<2000'],
  },
};

export default function () {
  const r = http.get(`${BASE}/book`);
  check(r, { 'status 200': (res) => res.status === 200 });
  sleep(Math.random() * 0.5);        // think time
}
