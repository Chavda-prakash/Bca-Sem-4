#!/usr/bin/env python3
"""Collect CPU and memory usage of the uvicorn process during load testing."""
import json
import sys
import time
import psutil
def find_uvicorn_pid() -> int | None:
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmdline = proc.info.get("cmdline") or []
            if any("uvicorn" in str(c) for c in cmdline):
                return proc.info["pid"]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None
def main() -> None:
    pid = find_uvicorn_pid()
    if pid is None:
        print("ERROR: uvicorn process not found", file=sys.stderr)
        sys.exit(1)
    proc = psutil.Process(pid)
    proc.cpu_percent()  # prime the counter
    samples: list[dict] = []
    duration = int(sys.argv[1]) if len(sys.argv) > 1 else 70
    interval = 2
    print(f"Monitoring PID {pid} for ~{duration}s ...")
    start = time.time()
    while time.time() - start < duration:
        try:
            mem = proc.memory_info()
            samples.append({
                "t": round(time.time() - start, 1),
                "cpu_pct": proc.cpu_percent(interval=None),
                "rss_mb": round(mem.rss / (1024 * 1024), 1),
                "vms_mb": round(mem.vms / (1024 * 1024), 1),
                "threads": proc.num_threads(),
            })
        except psutil.NoSuchProcess:
            break
        time.sleep(interval)
    # Summary
    if samples:
        cpus = [s["cpu_pct"] for s in samples]
        rss = [s["rss_mb"] for s in samples]
        summary = {
            "samples": len(samples),
            "cpu_avg": round(sum(cpus) / len(cpus), 1),
            "cpu_max": round(max(cpus), 1),
            "rss_avg_mb": round(sum(rss) / len(rss), 1),
            "rss_max_mb": round(max(rss), 1),
            "threads_max": max(s["threads"] for s in samples),
        }
        print(json.dumps(summary, indent=2))
        with open("results/system_metrics.json", "w") as f:
            json.dump({"summary": summary, "samples": samples}, f, indent=2)
    else:
        print("No samples collected.")
if __name__ == "__main__":
    main()
