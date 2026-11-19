"""Turn results/*.csv into PNG graphs in results/plots/. Skips experiments that have no CSV yet."""
import csv
import statistics
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
    """series: [(name, colour, values)] or [(name, colour, values, ranges)], where ranges is a list of
    (min, max) per bar drawn as a whisker. Bars with a 2 px gap, values labelled on top."""
    n = len(series)
    width = 0.8 / n
    for i, (name, colour, values, *rest) in enumerate(series):
        ranges = rest[0] if rest else None
        xs = [x - 0.4 + width * (i + 0.5) for x in range(len(labels))]
        vals = [v if v is not None else 0 for v in values]
        bars = ax.bar(xs, vals, width=width * 0.92, color=colour, label=name, zorder=2)
        # A zero-height bar is invisible; draw a coloured stub on the axis so zeros (e.g. 0 lost)
        # still read as a result for that series rather than a missing bar.
        for b, v in zip(bars, values):
            if v == 0:
                ax.hlines(0, b.get_x(), b.get_x() + b.get_width(), colors=colour, linewidth=4,
                          zorder=3, clip_on=False)
        if ranges:
            ax.errorbar(xs, vals, yerr=[[v - lo for v, (lo, _) in zip(vals, ranges)],
                                        [hi - v for v, (_, hi) in zip(vals, ranges)]],
                        fmt="none", ecolor=INK_2, elinewidth=1, capsize=4, zorder=3)
        for j, (b, v) in enumerate(zip(bars, values)):
            if v is not None:
                top = ranges[j][1] if ranges else b.get_height()
                ax.annotate(f"{v:g}{unit}", (b.get_x() + b.get_width() / 2, top),
                            xytext=(0, 3), textcoords="offset points", ha="center", fontsize=8, color=INK_2)
    ax.set_xticks(range(len(labels)), labels)
    ax.tick_params(axis="x", length=0)
    if n > 1:
        # Push the legend below however many lines the x labels take (2 lines -> -0.12, as before).
        lines = max(str(lab).count("\n") + 1 for lab in labels)
        ax.legend(loc="upper left", bbox_to_anchor=(0, -0.06 * lines), ncol=n)


def save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / f"{name}.png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    print(OUT / f"{name}.png")


def broker_kill(rows):
    # One group per profile (lite / default), median with a min-max whisker: every run restarts its
    # trial count at 1, so per-trial bars repeat labels.
    profiles = profiles_in(rows)
    by_profile = {p: [r for r in rows if r["profile"] == p] for p in profiles}
    labels = [f"{p} profile\n({len(by_profile[p])} trials)" for p in profiles]

    def timing(col):
        vals = {p: [v for r in by_profile[p] if (v := num(r[col])) is not None] for p in profiles}
        return ([round(statistics.median(vals[p]), 2) if vals[p] else None for p in profiles],
                [(min(vals[p]), max(vals[p])) if vals[p] else (0, 0) for p in profiles])

    lost = sum(int(r["lost"]) for r in rows)
    acked = sum(int(r["acked"]) for r in rows)
    fig, ax = plt.subplots(figsize=(7.5, 4))
    grouped_bars(ax, labels, [
        ("broker pod Ready", BLUE, *timing("broker_ready_s")),
        ("all partitions in sync", ORANGE, *timing("in_sync_s")),
        ("longest producer stall", AQUA, *timing("producer_stall_s")),
    ], "s")
    ax.set_title("Kafka broker killed under load: recovery time", pad=38)
    ax.text(0, 1.03, f"Messages lost: {lost} of {acked:,} acknowledged across {len(rows)} trial(s) "
            "(acked by Kafka vs rows in Postgres)\nmedian; whiskers show min-max across trials",
            transform=ax.transAxes, color=INK_2, fontsize=9)
    ax.set_ylabel("seconds after the kill")
    save(fig, "broker_kill")


def profiles_in(rows):
    """Profiles present in the rows, lite before default."""
    return sorted({r["profile"] for r in rows}, key=lambda p: (p != "lite", p))


def median_range(groups, col):
    """groups: [rows]. Returns ([median per group], [(min, max) per group]) for one numeric column."""
    vals = [[v for r in g if (v := num(r[col])) is not None] for g in groups]
    return ([round(statistics.median(v), 2) if v else None for v in vals],
            [(min(v), max(v)) if v else (0, 0) for v in vals])


def consumer_kill(rows):
    # One group per failure mode, split by profile when the CSV holds more than one (every run
    # restarts its trial count at 1, so per-trial bars get crowded and ambiguous): timings as median
    # with a min-max whisker, delivery counts as totals.
    profiles = profiles_in(rows)
    keys = [(m, p) for m in sorted({r["mode"] for r in rows}) for p in profiles]
    groups = [[r for r in rows if (r["mode"], r["profile"]) == k] for k in keys]
    keys, groups = zip(*[(k, g) for k, g in zip(keys, groups) if g])
    labels = [f"{m}\n{p}\n({len(g)} trials)" if len(profiles) > 1 else f"{m}\n({len(g)} trials)"
              for (m, p), g in zip(keys, groups)]

    def timing(col):
        return median_range(groups, col)

    def total(col):
        return [int(sum(num(r[col]) or 0 for r in g)) for g in groups]

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(14 if len(profiles) > 1 else 11, 4.2))
    grouped_bars(a1, labels, [
        ("partitions reassigned", BLUE, *timing("rebalance_s")),
        ("group back to full size", ORANGE, *timing("group_full_s")),
    ], "s")
    a1.set_title("Consumer lost mid-load: rebalance time", pad=24)
    a1.text(0, 1.03, "median; whiskers show min-max across trials", transform=a1.transAxes,
            color=INK_2, fontsize=9)
    a1.set_ylabel("seconds after the kill")
    grouped_bars(a2, labels, [
        ("redelivered, absorbed by upsert", BLUE, total("redelivered_absorbed")),
        ("duplicate rows", ORANGE, total("duplicate_rows")),
        ("lost", AQUA, total("lost")),
    ], "")
    a2.set_title("At-least-once delivery, idempotent writes", pad=24)
    written = sum(int(num(r["rows"]) or 0) for r in rows)
    a2.text(0, 1.03, f"totals across all trials ({written:,} rows written)", transform=a2.transAxes,
            color=INK_2, fontsize=9)
    a2.set_ylabel("messages / rows")
    fig.tight_layout()
    save(fig, "consumer_kill")


PROFILE_COLOURS = {"lite": ORANGE, "default": BLUE}


def sample_times(pts):
    """t_s of the samples (in the order taken), never decreasing. Runs recorded before
    exp_keda_burst used the monotonic clock can step back ~0.2 s when WSL adjusts the wall clock,
    which would draw the line doubling back on itself."""
    out = []
    for s in pts:
        t = num(s["t_s"])
        out.append(max(t, out[-1]) if out else t)
    return out


def keda_burst(series, summary):
    profiles = profiles_in(summary)
    if len(profiles) > 1:
        return keda_burst_compare(series, summary, profiles)
    run_id = summary[-1]["run_id"]
    pts = [s for s in series if s["run_id"] == run_id]
    t = sample_times(pts)
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(8, 5.5), sharex=True, gridspec_kw={"height_ratios": [3, 2]})
    a1.plot(t, [num(s["lag"]) or 0 for s in pts], color=BLUE)
    a1.set_title("Burst load: consumer lag (KEDA's scaling signal)")
    a1.set_ylabel("messages behind")
    a2.step(t, [int(s["desired"]) for s in pts], where="post", color=ORANGE, label="desired")
    a2.step(t, [int(s["ready"]) for s in pts], where="post", color=AQUA, label="ready")
    a2.set_title("listing-store replicas")
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


def keda_burst_compare(series, summary, profiles):
    """Most recent burst of each profile overlaid; footer gives medians across all bursts."""
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(8, 6), sharex=True, gridspec_kw={"height_ratios": [3, 2]})
    notes = []
    for p in profiles:
        runs = [s for s in summary if s["profile"] == p]
        pts = [s for s in series if s["run_id"] == runs[-1]["run_id"]]
        t = sample_times(pts)
        colour = PROFILE_COLOURS.get(p, AQUA)
        a1.plot(t, [num(s["lag"]) or 0 for s in pts], color=colour, label=f"{p} profile")
        a2.step(t, [int(s["ready"]) for s in pts], where="post", color=colour, label=f"{p} profile")
        med = {c: median_range([runs], c)[0][0] for c in ("scale_out_s", "peak_replicas", "drained_s")}
        notes.append(f"{p} ({len(runs)} bursts): scale-out {med['scale_out_s']:g} s, peak "
                     f"{med['peak_replicas']:g} replicas, drained {med['drained_s']:g} s")
    a1.set_title("Burst load: consumer lag (KEDA's scaling signal)")
    a1.set_ylabel("messages behind")
    a1.legend(loc="upper right")
    a2.set_title("listing-store replicas ready")
    a2.set_ylabel("pods")
    a2.set_xlabel("seconds since the first message of the burst")
    a2.yaxis.get_major_locator().set_params(integer=True)
    s = summary[-1]
    fig.text(0.01, -0.04, f"Most recent burst per profile ({int(s['count']):,} messages at {num(s['rate']):g}/s). "
             "Medians across bursts:\n" + "\n".join(notes), color=INK_2, fontsize=9)
    fig.tight_layout()
    save(fig, "keda_burst")


def knative_coldstart_compare(rows, profiles):
    """One group per profile, median with min-max whiskers (per-run bars get too crowded)."""
    groups = [[r for r in rows if r["profile"] == p] for p in profiles]
    labels = [f"{p} profile\n({len(g)} cold starts)" for p, g in zip(profiles, groups)]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 4), gridspec_kw={"width_ratios": [3, 2]})
    grouped_bars(a1, labels, [
        ("cold (scaled from zero)", BLUE, *median_range(groups, "cold_ms")),
        ("warm (median)", ORANGE, *median_range(groups, "warm_median_ms")),
    ], "")
    a1.set_yscale("log")
    a1.set_ylim(1, a1.get_ylim()[1] * 3)
    a1.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:g}"))
    a1.set_title("Scorer request latency, Knative", pad=24)
    a1.text(0, 1.03, "median; whiskers show min-max", transform=a1.transAxes, color=INK_2, fontsize=9)
    a1.set_ylabel("milliseconds (log scale)")
    grouped_bars(a2, [p for p in profiles], [("idle until zero pods", BLUE, *median_range(groups, "scale_to_zero_s"))], "s")
    a2.set_title("Scale to zero after the last request", pad=24)
    a2.set_ylabel("seconds")
    fig.tight_layout()
    save(fig, "knative_coldstart")


def knative_coldstart(rows):
    profiles = profiles_in(rows)
    if len(profiles) > 1:
        return knative_coldstart_compare(rows, profiles)
    # Number cold starts across all runs in the CSV; each run restarts its own iteration count at 1.
    labels = [str(n) for n in range(1, len(rows) + 1)]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 4), gridspec_kw={"width_ratios": [3, 2]})
    grouped_bars(a1, labels, [
        ("cold (scaled from zero)", BLUE, [num(r["cold_ms"]) for r in rows]),
        ("warm (median)", ORANGE, [num(r["warm_median_ms"]) for r in rows]),
    ], "")
    # Log scale: warm requests are ~1000x faster than cold ones and vanish on a linear axis.
    a1.set_yscale("log")
    a1.set_ylim(1, a1.get_ylim()[1] * 3)
    a1.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:g}"))
    a1.set_title("Scorer request latency, Knative")
    a1.set_ylabel("milliseconds (log scale)")
    a1.set_xlabel("cold start #")
    zero = [(lab, num(r["scale_to_zero_s"])) for lab, r in zip(labels, rows) if num(r["scale_to_zero_s"]) is not None]
    if zero:
        grouped_bars(a2, [z[0] for z in zero], [("idle until zero pods", BLUE, [z[1] for z in zero])], "s")
    a2.set_title("Scale to zero after the last request")
    a2.set_ylabel("seconds")
    a2.set_xlabel("cold start #")
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
