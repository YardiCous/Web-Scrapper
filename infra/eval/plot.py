"""Turn results/*.csv into PNG graphs in results/plots/. Skips experiments that have no CSV yet."""
import csv
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"
OUT = RESULTS / "plots"

# Reference palette (light): fixed categorical order, recessive chrome, text in ink colours only.
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK_2, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "font.family": "DejaVu Sans", "font.size": 10,   # bundled with matplotlib, so identical everywhere
    "text.color": INK, "axes.labelcolor": INK_2, "axes.titlesize": 11, "axes.titleweight": "bold",
    "axes.titlecolor": INK, "axes.titlelocation": "left",
    "axes.edgecolor": AXIS, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "axes.grid.axis": "y", "grid.color": GRID, "grid.linewidth": 0.8,
    "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelcolor": INK_2, "ytick.labelcolor": INK_2,
    "legend.frameon": False, "lines.linewidth": 2,
})


def read(name):
    path = RESULTS / f"{name}.csv"
    if not path.exists():
        return []
    with path.open() as f:
        return list(csv.DictReader(f))


def num(v):
    return float(v) if v not in ("", None, "None") else None


def grouped_bars(ax, labels, series, unit):
    """series: [(name, colour, values)]. Bars with a 2 px gap, values labelled on top."""
    n = len(series)
    width = 0.8 / n
    for i, (name, colour, values) in enumerate(series):
        xs = [x - 0.4 + width * (i + 0.5) for x in range(len(labels))]
        vals = [v if v is not None else 0 for v in values]
        bars = ax.bar(xs, vals, width=width * 0.92, color=colour, label=name, zorder=2)
        for b, v in zip(bars, values):
            if v is not None:
                ax.annotate(f"{v:g}{unit}", (b.get_x() + b.get_width() / 2, b.get_height()),
                            xytext=(0, 3), textcoords="offset points", ha="center", fontsize=8, color=INK_2)
    ax.set_xticks(range(len(labels)), labels)
    ax.tick_params(axis="x", length=0)
    if n > 1:
        ax.legend(loc="upper left", bbox_to_anchor=(0, -0.12), ncol=n)


def save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / f"{name}.png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    print(OUT / f"{name}.png")


def broker_kill(rows):
    labels = [f"trial {r['trial']}\n({r['profile']})" for r in rows]
    lost = sum(int(r["lost"]) for r in rows)
    acked = sum(int(r["acked"]) for r in rows)
    fig, ax = plt.subplots(figsize=(7.5, 4))
    grouped_bars(ax, labels, [
        ("broker pod Ready", BLUE, [num(r["broker_ready_s"]) for r in rows]),
        ("all partitions in sync", ORANGE, [num(r["in_sync_s"]) for r in rows]),
        ("longest producer stall", AQUA, [num(r["producer_stall_s"]) for r in rows]),
    ], "s")
    ax.set_title("Kafka broker killed under load: recovery time", pad=24)
    ax.text(0, 1.03, f"Messages lost: {lost} of {acked:,} acknowledged across {len(rows)} trial(s) "
            "(acked by Kafka vs rows in Postgres)", transform=ax.transAxes, color=INK_2, fontsize=9)
    ax.set_ylabel("seconds after the kill")
    save(fig, "broker_kill")


def consumer_kill(rows):
    rows = sorted(rows, key=lambda r: (r["mode"], int(r["trial"])))
    labels = [f"{r['mode']}\n#{r['trial']}" for r in rows]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.2))
    grouped_bars(a1, labels, [
        ("partitions reassigned", BLUE, [num(r["rebalance_s"]) for r in rows]),
        ("group back to full size", ORANGE, [num(r["group_full_s"]) for r in rows]),
    ], "s")
    a1.set_title("Consumer lost mid-load: rebalance time")
    a1.set_ylabel("seconds after the kill")
    grouped_bars(a2, labels, [
        ("redelivered, absorbed by upsert", BLUE, [num(r["redelivered_absorbed"]) for r in rows]),
        ("duplicate rows", ORANGE, [num(r["duplicate_rows"]) for r in rows]),
        ("lost", AQUA, [num(r["lost"]) for r in rows]),
    ], "")
    a2.set_title("At-least-once delivery, idempotent writes")
    a2.set_ylabel("messages / rows")
    fig.tight_layout()
    save(fig, "consumer_kill")


def keda_burst(series, summary):
    run_id = summary[-1]["run_id"]
    pts = [s for s in series if s["run_id"] == run_id]
    t = [num(s["t_s"]) for s in pts]
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(8, 5.5), sharex=True, gridspec_kw={"height_ratios": [3, 2]})
    a1.plot(t, [num(s["lag"]) or 0 for s in pts], color=BLUE)
    a1.set_title("Burst load: consumer lag (KEDA's scaling signal)")
    a1.set_ylabel("messages behind")
    a2.step(t, [int(s["desired"]) for s in pts], where="post", color=ORANGE, label="desired")
    a2.step(t, [int(s["ready"]) for s in pts], where="post", color=AQUA, label="ready")
    a2.set_title("smoke-consumer replicas")
    a2.set_ylabel("pods")
    a2.set_xlabel("seconds since the first message of the burst")
    a2.yaxis.get_major_locator().set_params(integer=True)
    a2.legend(loc="upper right")
    s = summary[-1]
    for ax in (a1, a2):
        ax.axvline(num(s["load_done_s"]), color=MUTED, linewidth=1, linestyle=":")
    a1.annotate("load finished", (num(s["load_done_s"]), a1.get_ylim()[1]), xytext=(4, -12),
                textcoords="offset points", color=INK_2, fontsize=8)
    fig.text(0.01, -0.02, f"Scale-out decided at {s['scale_out_s']} s, peak {s['peak_replicas']} replicas at "
             f"{s['time_to_peak_s']} s, lag drained at {s['drained_s']} s ({int(s['count']):,} messages at "
             f"{num(s['rate']):g}/s).", color=INK_2, fontsize=9)
    fig.tight_layout()
    save(fig, "keda_burst")


def knative_coldstart(rows):
    labels = [r["iteration"] for r in rows]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 4), gridspec_kw={"width_ratios": [3, 2]})
    grouped_bars(a1, labels, [
        ("cold (scaled from zero)", BLUE, [num(r["cold_ms"]) for r in rows]),
        ("warm (median)", ORANGE, [num(r["warm_median_ms"]) for r in rows]),
    ], "")
    a1.set_title("Scorer request latency, Knative")
    a1.set_ylabel("milliseconds")
    a1.set_xlabel("iteration")
    zero = [(r["iteration"], num(r["scale_to_zero_s"])) for r in rows if num(r["scale_to_zero_s"]) is not None]
    if zero:
        grouped_bars(a2, [z[0] for z in zero], [("idle until zero pods", BLUE, [z[1] for z in zero])], "s")
    a2.set_title("Scale to zero after the last request")
    a2.set_ylabel("seconds")
    a2.set_xlabel("iteration")
    fig.tight_layout()
    save(fig, "knative_coldstart")


def main():
    made = 0
    if rows := read("broker_kill"):
        broker_kill(rows); made += 1
    if rows := read("consumer_kill"):
        consumer_kill(rows); made += 1
    if (summary := read("keda_burst")) and (series := read("keda_burst_timeseries")):
        keda_burst(series, summary); made += 1
    if rows := read("knative_coldstart"):
        knative_coldstart(rows); made += 1
    if not made:
        print(f"no CSVs in {RESULTS}; run the experiments first")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
