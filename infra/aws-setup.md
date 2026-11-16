# AWS setup (as actually built)

Region: **us-east-1 (N. Virginia)**. Mumbai (ap-south-1) was not available on this account.
Live URL: `http://tatkal-alb-1581951320.us-east-1.elb.amazonaws.com/tatkal`

## Architecture

```
k6 (laptop) -> Application Load Balancer (tatkal-alb, HTTP 80)
                  -> Target group tatkal-tg (health check: /health)
                       -> Auto Scaling Group tatkal-asg (min 1, max 3, us-east-1a + us-east-1b)
                            EC2 t3.micro, Amazon Linux 2023, Docker container running the Node app
CloudWatch alarms (created by the cpu50 policy): average CPU > 50% -> add server
```

## 1. Security groups
| Name | Inbound rule |
|---|---|
| `alb-sg` | HTTP 80 from 0.0.0.0/0 |
| `ec2-sg` | HTTP 80 from `alb-sg` only |

## 2. Launch template `tatkal-lt`
- AMI: Amazon Linux 2023, instance type `t3.micro`, security group `ec2-sg`, no key pair
- User data: `infra/user-data.sh` (installs Docker and git, clones this repo, builds the image, runs it on port 80)
- Version 1 had a placeholder repo URL and every server failed to start. Version 2 (default) has the correct URL.

## 3. Target group `tatkal-tg`
- Target type Instances, HTTP 80, health check path `/health`
- Health check settings (confirmed in the console on 2026-11-16): healthy threshold 2, unhealthy threshold 2, timeout 5 s, interval 10 s, success code 200

## 4. Load balancer `tatkal-alb`
- Internet-facing, zones us-east-1a and us-east-1b, security group `alb-sg`
- Listener HTTP:80 forwards to `tatkal-tg`

## 5. Auto Scaling Group `tatkal-asg`
- Launch template `tatkal-lt` (default version), same two zones, attached to `tatkal-tg`
- ELB health checks on, grace period 300 s
- Min 1, desired 1, max 3
- Group metrics collection enabled
- Scaling policy `cpu50`: target tracking, average CPU utilization 50%, instance warm-up 120 s, scale-in enabled

## 6. Load test (from a laptop, not from the servers)
```
k6 run -e BASE_URL=http://tatkal-alb-1581951320.us-east-1.elb.amazonaws.com --out csv=results/k6_autoscale.csv loadtest/tatkal.js
```
Stages: 1 min at 10 users, 30 s ramp to 60 users, 12 min at 60 users, 1 min down to 10, 3 min at 10.

## 7. Results (2026-11-14, UTC)
| Time | Event |
|---|---|
| 14:43:17 | Alarm fired, desired capacity 1 -> 2 |
| 14:45:34 | 2nd server in service |
| 14:46:17 | Alarm fired, desired capacity 2 -> 3 |
| 14:48:32 | 3rd server in service |
| 15:11:30 | Low-CPU alarm fired, 3 -> 2 |
| 15:12:30 | 2 -> 1 |

### Run 4: pre-warmed (2026-11-15, UTC)
Scheduled action `prewarm` (10:18:08) set min 3, max 5, desired 3, so 3 servers were running before the test.
k6 ran 15:14:22 to 15:31:52 (30,371 requests, 0 non-200 responses).

| Time | Event |
|---|---|
| 15:19:17 | Alarm fired, desired capacity 3 -> 5 |
| 15:21:30 | 4th and 5th servers in service (7.2 min after test start) |
| 15:44:33 | Low-CPU alarm, 5 -> 4 |
| 15:46:53 | 4 -> 3 (stops at 3 because min is 3) |

| Window | Requests/s | Median | p95 |
|---|---|---|---|
| 3 servers, peak, before scale-out | 25.6 | 1.77 s | 4.88 s |
| 5 servers, peak | 41.3 | 0.56 s | 4.30 s |

Even 3 servers could not hold CPU at 50% under 60 users: average CPU reached about 100% and the group asked for 5.
Console check: the target group shows no 5xx data over the last day.

Run files in `results/`: `run1_before_fix` (failed run), `run2_baseline_1server` (no scaling), `k6_autoscale` (autoscaled run), `run4_prewarmed` (pre-warmed run), plus graphs.

## 8. Problems we hit and fixes
1. Launch template had a placeholder repo URL: servers never started the app. Fixed with template version 2.
2. The load balancer used the default security group instead of `alb-sg`: health checks timed out.
3. The Auto Scaling Group had no scaling policy: CPU reached 100% but capacity stayed at 1. Added `cpu50`.
4. CPU-heavy `/book` requests blocked `/health` on the same thread: servers were replaced during load (72% failed requests). The app now does the CPU work asynchronously and the health check settings are more tolerant.
5. k6 failed to connect on an IPv6 network. Fixed with `dns: { policy: 'preferIPv6' }` in the k6 options.
6. Mumbai was not available, so everything runs in us-east-1.

## 9. Clean-up (the load balancer bills every hour)
Delete in this order: Auto Scaling Group, Load Balancer, Target Group, Launch Template.

## 10. Live dashboard (added 2026-11-16)
`/dashboard` shows which server and zone answered each request. `user-data.sh` reads the zone and instance id from the EC2
metadata service and passes them to the container as `AZ` and `INSTANCE_ID`. To use it: push the repo, create launch template
version 3 with the new user data, set it as the default, then replace the running servers. Servers started from version 2
show their zone as `unknown`.
