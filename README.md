# IRCTC Tatkal: Cloud Autoscaling PoC (IT457, Theme 1)

Shows how a small web app behind a load balancer scales out automatically when
Tatkal-style traffic spikes, and scales back in when it drops.

## Architecture
```
k6 (separate machine) -> Application Load Balancer (/health checks)
                              -> Auto Scaling Group (min 1, max 4, 2 AZs)
                                   EC2 t3.micro running Docker app
CloudWatch: avg CPU > 50% -> add instance (target tracking)
```

## Repo layout
- `app/` Node.js API (`/health`, `/tatkal`, `/book`) + Dockerfile
- `infra/` EC2 user-data script and AWS console setup steps
- `loadtest/` k6 script and CloudWatch plotting script
- `results/` CSVs, graphs, screenshots
- `docs/` report, architecture diagram, weekly progress

## Endpoints
| Path | Purpose |
|---|---|
| `/health` | Load balancer health check |
| `/tatkal` | Returns `{"status":"Tatkal Ticket Available"}` |
| `/book` | ~60-100 ms of CPU work (simulates captcha/payment) so CPU actually rises |

## Run locally
```
cd app && node server.js          # or: docker build -t tatkal . && docker run -p 3000:3000 tatkal
curl localhost:3000/tatkal
```
Tune `WORK_ITERATIONS` (env var) so `/book` takes ~60-100 ms on your instance type.

## Deploy
Follow `infra/aws-setup.md`.

## Load test
```
k6 run -e BASE_URL=http://<ALB-DNS> --out csv=results/k6_autoscale.csv loadtest/tatkal.js
```
Run it from your laptop or a separate VM, never from the app servers.

## Plot results
```
pip install boto3 matplotlib
python loadtest/plot_results.py --asg tatkal-asg --alb app/tatkal-alb/<id> \
    --start <UTC start> --end <UTC end> --out results/autoscale.png
```

## Baseline comparison (recommended)
Set the ASG to min=max=1 (scaling off), run the same k6 test, save as
`results/k6_fixed.csv`, and compare latency and errors against the autoscaled run.

## Clean up
Delete the ASG, ALB, target group and launch template after the demo.
