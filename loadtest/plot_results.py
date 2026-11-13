"""Pull CloudWatch metrics and plot response time vs instance count.

  pip install boto3 matplotlib
  python loadtest/plot_results.py \
      --asg tatkal-asg \
      --alb app/tatkal-alb/1234567890abcdef \
      --start 2026-11-20T10:00:00 --end 2026-11-20T10:25:00 \
      --out results/autoscale.png

--alb is the ALB's "LoadBalancer" dimension value (the part of its ARN after
'loadbalancer/'), e.g. app/tatkal-alb/1234567890abcdef.  Times are UTC.
"""
import argparse
import csv
from datetime import datetime, timezone

import boto3
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

p = argparse.ArgumentParser()
p.add_argument("--asg", required=True)
p.add_argument("--alb", required=True)
p.add_argument("--start", required=True)
p.add_argument("--end", required=True)
p.add_argument("--region", default="ap-south-1")
p.add_argument("--out", default="results/autoscale.png")
a = p.parse_args()

start = datetime.fromisoformat(a.start).replace(tzinfo=timezone.utc)
end = datetime.fromisoformat(a.end).replace(tzinfo=timezone.utc)
cw = boto3.client("cloudwatch", region_name=a.region)


def get(namespace, metric, dims, stat=None, ext=None):
    kw = dict(Namespace=namespace, MetricName=metric, Dimensions=dims,
              StartTime=start, EndTime=end, Period=60)
    if ext:
        kw["ExtendedStatistics"] = [ext]
    else:
        kw["Statistics"] = [stat]
    pts = cw.get_metric_statistics(**kw)["Datapoints"]
    pts.sort(key=lambda d: d["Timestamp"])
    key = ext if ext else stat
    val = (lambda d: d["ExtendedStatistics"][ext]) if ext else (lambda d: d[stat])
    return [d["Timestamp"] for d in pts], [val(d) for d in pts]


asg = [{"Name": "AutoScalingGroupName", "Value": a.asg}]
alb = [{"Name": "LoadBalancer", "Value": a.alb}]

t_inst, inst = get("AWS/AutoScaling", "GroupInServiceInstances", asg, "Average")
t_cpu, cpu = get("AWS/EC2", "CPUUtilization", asg, "Average")
t_rt, rt_p95 = get("AWS/ApplicationELB", "TargetResponseTime", alb, ext="p95")
t_req, req = get("AWS/ApplicationELB", "RequestCount", alb, "Sum")

# Save raw data too (good evidence for the report)
with open(a.out.replace(".png", ".csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["series", "timestamp_utc", "value"])
    for name, ts, vs in [("instances", t_inst, inst), ("cpu_pct", t_cpu, cpu),
                         ("p95_response_s", t_rt, rt_p95), ("requests_per_min", t_req, req)]:
        for t, v in zip(ts, vs):
            w.writerow([name, t.isoformat(), v])

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 8), sharex=True)

ax1.plot(t_rt, [v * 1000 for v in rt_p95], color="tab:red", label="p95 response time (ms)")
ax1.set_ylabel("Response time (ms)", color="tab:red")
ax1b = ax1.twinx()
ax1b.step(t_inst, inst, where="post", color="tab:blue", label="Instances in service")
ax1b.set_ylabel("Instances", color="tab:blue")
ax1b.set_ylim(0, max(inst + [1]) + 1)
ax1.set_title("Tatkal load test: response time vs instance count")

ax2.plot(t_cpu, cpu, color="tab:green", label="Avg CPU %")
ax2.axhline(50, color="gray", linestyle="--", label="Scaling target (50%)")
ax2.set_ylabel("CPU %")
ax2.set_xlabel("Time (UTC)")
ax2.legend(loc="upper left")

plt.tight_layout()
plt.savefig(a.out, dpi=150)
print(f"saved {a.out} and {a.out.replace('.png', '.csv')}")
