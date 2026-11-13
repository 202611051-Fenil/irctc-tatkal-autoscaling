# AWS setup (Console steps)

Region: **ap-south-1 (Mumbai)**. Take a screenshot at each major step for the report.

## 0. Safety first
- Billing > Budgets > create a budget (e.g. $5) with an email alert.

## 1. Security groups
- **alb-sg**: inbound HTTP 80 from `0.0.0.0/0`.
- **ec2-sg**: inbound HTTP 80 **from alb-sg only**. (SSH not needed; use EC2 Instance Connect if you must debug.)

## 2. Launch Template (`tatkal-lt`)
- AMI: Amazon Linux 2023
- Instance type: `t3.micro` (or `t2.micro` if free tier)
- Security group: `ec2-sg`
- Advanced > User data: paste `infra/user-data.sh` (after setting `REPO_URL`)
- Advanced > Detailed CloudWatch monitoring: **Enable** (1-minute metrics, faster scaling)

## 3. Target group (`tatkal-tg`)
- Type: Instances, protocol HTTP, port 80
- Health check path: `/health`
- Health check interval 10 s, healthy threshold 2 (faster registration)

## 4. Application Load Balancer (`tatkal-alb`)
- Internet-facing, **select at least 2 AZs** (ap-south-1a and ap-south-1b)
- Security group: `alb-sg`
- Listener HTTP:80 -> forward to `tatkal-tg`

## 5. Auto Scaling Group (`tatkal-asg`)
- Launch template: `tatkal-lt`, same 2 AZs/subnets
- Attach to existing load balancer target group `tatkal-tg`
- Turn on ELB health checks, health check grace period 120 s
- Group size: **min 1, desired 1, max 4**
- Scaling policy: **Target tracking**, metric *Average CPU utilization*, target **50**, instance warm-up 120 s
- Monitoring: enable **Group metrics collection** (GroupInServiceInstances etc.)

## 6. Verify
- `curl http://<ALB-DNS>/tatkal` -> `{"status":"Tatkal Ticket Available",...}`
- Hit it repeatedly; the `server` field should change once there are 2+ instances.

## 7. Clean up after the demo (important, ALB bills hourly)
1. Delete the Auto Scaling Group (terminates the instances)
2. Delete the Load Balancer
3. Delete the Target Group and Launch Template
