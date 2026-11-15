"""Plot k6 results against Auto Scaling events (no AWS login needed).

Reads the k6 CSV files and draws:
  1. results/autoscale_response_vs_instances.png
       response time (p50, p95) and throughput vs number of servers over time
  2. results/baseline_vs_autoscale.png
       the same test with 1 fixed server vs with autoscaling, side by side
  3. results/phase_stats.txt
       fair comparison table: same 60-user load, 1 vs 2 vs 3 servers

Run from the repo folder:
  pip install matplotlib
  python loadtest/plot_k6.py

Instance counts come from the Auto Scaling Activity history (UTC times).
Edit the two event lists below if your times differ.
"""
import csv
import os
import sys
from datetime import datetime, timezone

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np

AUTOSCALE_CSV = "results/k6_autoscale.csv"
BASELINE_CSV = "results/run2_baseline_1server.csv"
OUT_MAIN = "results/autoscale_response_vs_instances.png"
OUT_COMPARE = "results/baseline_vs_autoscale.png"
OUT_PHASES = "results/phase_stats.txt"
BIN_SECONDS = 30

# From tatkal-asg > Activity (all UTC, 2026-11-14).
# Servers actually in service: (time, count after the change)
IN_SERVICE_EVENTS = [
    ("14:45:34", 2),   # 1st extra server finished launching
    ("14:48:32", 3),   # 2nd extra server finished launching
    ("15:11:39", 2),   # scale-in: 3 -> 2
    ("15:12:41", 1),   # scale-in: 2 -> 1
]
# What the policy asked for (desired capacity): (time, count)
DESIRED_EVENTS = [
    ("14:43:17", 2),
    ("14:46:17", 3),
    ("15:11:30", 2),
    ("15:12:30", 1),
]
EVENT_DATE = "2026-11-14"


def parse_ts(value):
    try:
        return float(value)                      # k6 default: unix seconds
    except ValueError:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def load_k6(path):
    """Return arrays (timestamps, duration_seconds) for http_req_duration."""
    ts, dur = [], []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            if row["metric_name"] == "http_req_duration":
                ts.append(parse_ts(row["timestamp"]))
                dur.append(float(row["metric_value"]) / 1000.0)   # ms -> s
    return np.array(ts), np.array(dur)


def bin_stats(ts, dur, start):
    """Per-bin p50, p95 and requests/sec. Returns arrays keyed by bin start."""
    idx = ((ts - start) // BIN_SECONDS).astype(int)
    xs, p50, p95, rps = [], [], [], []
    for b in range(idx.min(), idx.max() + 1):
        d = dur[idx == b]
        if len(d) == 0:
            continue
        xs.append(start + b * BIN_SECONDS + BIN_SECONDS / 2)
        p50.append(np.percentile(d, 50))
        p95.append(np.percentile(d, 95))
        rps.append(len(d) / BIN_SECONDS)
    return np.array(xs), np.array(p50), np.array(p95), np.array(rps)


def to_dt(unix_list):
    return [datetime.fromtimestamp(t, tz=timezone.utc) for t in unix_list]


def event_unix(hms):
    return datetime.fromisoformat(f"{EVENT_DATE}T{hms}").replace(tzinfo=timezone.utc).timestamp()


def step_series(events, start, end, initial=1):
    """Build x/y arrays for a step line from (time, count) events."""
    xs, ys = [start], [initial]
    for hms, n in events:
        t = event_unix(hms)
        xs += [t, t]
        ys += [ys[-1], n]
    xs.append(end)
    ys.append(ys[-1])
    return np.array(xs), np.array(ys)


def summary(label, ts, dur):
    print(f"{label}: {len(dur)} requests | median {np.median(dur):.2f}s | "
          f"p95 {np.percentile(dur, 95):.2f}s | max {dur.max():.2f}s | "
          f"avg {len(dur) / (ts.max() - ts.min()):.1f} req/s")


def window_stats(label, ts, dur, start, a, b):
    """Stats for requests between a and b seconds after the test start."""
    m = (ts - start >= a) & (ts - start < b)
    d = dur[m]
    if len(d) == 0:
        return f"{label:<40} (no data)"
    return (f"{label:<40} {len(d):>6} req | {len(d) / (b - a):5.1f} req/s | "
            f"median {np.median(d):5.2f}s | p95 {np.percentile(d, 95):5.2f}s")


def write_phase_stats(ts, dur, start, bts, bdur, bstart):
    """Compare the 60-user peak fairly: same load, different server counts."""
    t2 = event_unix("14:45:34") - start       # 2nd server in service
    t3 = event_unix("14:48:32") - start       # 3rd server in service
    peak_end = 90 + 12 * 60                   # 1m + 30s ramp, then 12 min peak
    lines = ["Peak load = 60 users in every row (k6 stages: 1m calm, 30s ramp, then peak)", ""]
    if bts is not None:
        lines.append(window_stats("Baseline: 1 fixed server", bts, bdur, bstart, 120, 560))
    lines.append(window_stats("Autoscaled: 1 server (before scaling)", ts, dur, start, 120, t2 - 10))
    lines.append(window_stats("Autoscaled: 2 servers", ts, dur, start, t2 + 30, t3 - 10))
    lines.append(window_stats("Autoscaled: 3 servers", ts, dur, start, t3 + 30, peak_end - 10))
    lines += ["", f"2nd server in service {t2 / 60:.1f} min after test start, "
                  f"3rd at {t3 / 60:.1f} min."]
    text = "\n".join(lines)
    print(text)
    with open(OUT_PHASES, "w") as f:
        f.write(text + "\n")
    print("saved", OUT_PHASES)


def main():
    for p in (AUTOSCALE_CSV,):
        if not os.path.exists(p):
            sys.exit(f"Cannot find {p}. Run this from the repo folder.")

    ts, dur = load_k6(AUTOSCALE_CSV)
    start, end = ts.min(), ts.max()
    # extend the right edge so the scale-in events are visible
    last_event = max(event_unix(h) for h, _ in IN_SERVICE_EVENTS + DESIRED_EVENTS)
    plot_end = max(end, last_event) + 120
    xs, p50, p95, rps = bin_stats(ts, dur, start)

    # ---------- Figure 1: response time + instances + throughput ----------
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True,
                                   gridspec_kw={"height_ratios": [3, 2]})
    ax1.plot(to_dt(xs), p50, color="tab:green", label="Median response time")
    ax1.plot(to_dt(xs), p95, color="tab:red", label="p95 response time")
    ax1.set_ylabel("Response time (seconds)")
    fig.suptitle("Tatkal load test: response time vs number of servers (k6 -> ALB)", y=0.995)
    ax1.grid(alpha=0.3)

    ax1b = ax1.twinx()
    sx, sy = step_series(IN_SERVICE_EVENTS, start, plot_end)
    dx, dy = step_series(DESIRED_EVENTS, start, plot_end)
    ax1b.plot(to_dt(sx), sy, color="tab:blue", linewidth=2.5, label="Servers in service")
    ax1b.plot(to_dt(dx), dy, color="tab:blue", linestyle="--", linewidth=1.2,
              label="Desired capacity (policy request)")
    ax1b.set_ylabel("Number of servers")
    ax1b.set_ylim(0, 4)
    ax1b.set_yticks([0, 1, 2, 3, 4])
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax1b.get_legend_handles_labels()
    fig.legend(h1 + h2, l1 + l2, loc="upper center", bbox_to_anchor=(0.5, 0.965), ncol=4, fontsize=9)

    ax2.plot(to_dt(xs), rps, color="tab:purple")
    ax2.set_ylabel("Requests per second")
    ax2.set_xlabel("Time (UTC)")
    ax2.grid(alpha=0.3)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    plt.tight_layout(rect=[0, 0, 1, 0.93])
    plt.savefig(OUT_MAIN, dpi=150)
    plt.close()
    print("saved", OUT_MAIN)
    summary("Autoscaled", ts, dur)

    # ---------- Figure 2: baseline vs autoscale ----------
    bts = bdur = bstart = None
    if os.path.exists(BASELINE_CSV):
        bts, bdur = load_k6(BASELINE_CSV)
        bstart = bts.min()
        bx, bp50, bp95, brps = bin_stats(bts, bdur, bstart)
        fig, (a1, a2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
        a1.plot((bx - bstart) / 60, bp95, color="tab:orange", label="Baseline (1 fixed server) p95")
        a1.plot((xs - start) / 60, p95, color="tab:red", label="Autoscaled p95")
        a1.plot((bx - bstart) / 60, bp50, color="tab:orange", linestyle="--", label="Baseline median")
        a1.plot((xs - start) / 60, p50, color="tab:green", linestyle="--", label="Autoscaled median")
        a1.set_ylabel("Response time (seconds)")
        a1.set_title("Same test: 1 fixed server vs Auto Scaling (minutes since test start)")
        a1.legend()
        a1.grid(alpha=0.3)
        a2.plot((bx - bstart) / 60, brps, color="tab:orange", label="Baseline")
        a2.plot((xs - start) / 60, rps, color="tab:purple", label="Autoscaled")
        a2.set_ylabel("Requests per second")
        a2.set_xlabel("Minutes since test start")
        a2.legend()
        a2.grid(alpha=0.3)
        plt.tight_layout()
        plt.savefig(OUT_COMPARE, dpi=150)
        plt.close()
        print("saved", OUT_COMPARE)
        summary("Baseline ", bts, bdur)
    else:
        print(f"Baseline file {BASELINE_CSV} not found, skipped comparison graph.")

    write_phase_stats(ts, dur, start, bts, bdur, bstart)


if __name__ == "__main__":
    main()
