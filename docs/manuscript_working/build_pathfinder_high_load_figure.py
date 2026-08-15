from __future__ import annotations

import csv
import hashlib
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter, MultipleLocator


ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "龙阳路" / "高负荷"
OUT = ROOT / "docs" / "manuscript_working" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

METHODS = {
    "Improved A*": {
        "occupants": RAW / "龙阳路improved高负荷 _occupants.csv",
        "params": RAW / "龙阳路improved高负荷 _occupant_params.csv",
        "geom": RAW / "龙阳路improved高负荷 .geom",
        "color": "#6F7275",
        "linestyle": (0, (4, 2)),
        "marker": "s",
    },
    "AA*": {
        "occupants": RAW / "龙阳路AA高负荷 _occupants.csv",
        "params": RAW / "龙阳路AA高负荷 _occupant_params.csv",
        "geom": RAW / "龙阳路AA高负荷 .geom",
        "color": "#1769AA",
        "linestyle": "-",
        "marker": "o",
    },
    "PF-LQ": {
        "occupants": RAW / "any exit（test）_occupants.csv",
        "params": RAW / "any exit（test）_occupant_params.csv",
        "geom": RAW / "any exit（test）.geom",
        "color": "#D28E2B",
        "linestyle": (0, (1.4, 1.4)),
        "marker": "^",
    },
}

Q_LEVELS = [0.50, 0.80, 0.90, 0.95, 0.99, 1.00]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig", low_memory=False)


def summarize(label: str, frame: pd.DataFrame) -> dict[str, float | int | str]:
    exit_t = frame["exit time(s)"].astype(float).to_numpy()
    congestion = frame["congestion time total(s)"].astype(float).to_numpy()
    distance = frame["distance (m)"].astype(float).to_numpy()
    result: dict[str, float | int | str] = {
        "method": label,
        "n": int(exit_t.size),
        "mean_exit_time_s": float(np.mean(exit_t)),
        "sd_exit_time_s": float(np.std(exit_t, ddof=0)),
        "mean_congestion_time_s": float(np.mean(congestion)),
        "total_congestion_person_s": float(np.sum(congestion)),
        "mean_distance_m": float(np.mean(distance)),
        "mean_level_congestion_s": float(frame["level congestion time"].astype(float).mean()),
        "mean_stair_congestion_s": float(frame["stair congestion time"].astype(float).mean()),
    }
    for q in Q_LEVELS:
        result[f"T{int(q * 100):02d}_s"] = float(
            np.quantile(exit_t, q, method="linear") if q < 1.0 else np.max(exit_t)
        )
    return result


def write_completion_source(frames: dict[str, pd.DataFrame]) -> None:
    destination = OUT / "fig2_pathfinder_high_load_completion_source.csv"
    with destination.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["method", "rank", "exit_time_s", "cumulative_completed_pct"])
        for label, frame in frames.items():
            values = np.sort(frame["exit time(s)"].astype(float).to_numpy())
            cumulative = np.arange(1, values.size + 1, dtype=float) / values.size * 100.0
            writer.writerows(
                (label, rank, f"{time:.6f}", f"{pct:.8f}")
                for rank, (time, pct) in enumerate(zip(values, cumulative), start=1)
            )


def equivalence_audit(frames: dict[str, pd.DataFrame]) -> list[str]:
    lines: list[str] = []
    geometry_hashes = {label: sha256(spec["geom"]) for label, spec in METHODS.items()}
    lines.append("GEOMETRY SHA-256")
    for label, digest in geometry_hashes.items():
        lines.append(f"{label}: {digest}")
    lines.append(f"All .geom files byte-identical: {len(set(geometry_hashes.values())) == 1}")
    lines.append("")

    base_label = "Improved A*"
    base_raw = read_csv(METHODS[base_label]["params"])
    excluded = {"behavior"}
    compare_columns = [column for column in base_raw.columns if column not in excluded]
    lines.append("OCCUPANT COHORT AND PARAMETER AUDIT")
    lines.append(f"Reference protocol: {base_label}")
    lines.append(f"Compared columns ({len(compare_columns)}): all columns except behavior")
    for label in METHODS:
        alignment_key = "name" if label in {"Improved A*", "AA*"} else "id"
        base_params = base_raw.sort_values(alignment_key).reset_index(drop=True)
        params = read_csv(METHODS[label]["params"]).sort_values(alignment_key).reset_index(drop=True)
        same_keys = base_params[alignment_key].astype(str).equals(params[alignment_key].astype(str))
        mismatches: dict[str, int] = {}
        if same_keys and len(base_params) == len(params):
            for column in compare_columns:
                if column == alignment_key:
                    continue
                left = base_params[column].fillna("").astype(str)
                right = params[column].fillna("").astype(str)
                count = int((left != right).sum())
                if count:
                    mismatches[column] = count
        else:
            mismatches["name_or_row_count"] = abs(len(base_params) - len(params)) or 1
        lines.append(
            f"{label}: n={len(params)}; alignment={alignment_key}; same alignment-key set={same_keys}; "
            f"non-behavior mismatch columns={mismatches if mismatches else 'none'}"
        )

    lines.append("")
    lines.append("OUTCOME TABLE COHORT AUDIT")
    base_ids = set(frames[base_label]["id"].astype(str))
    for label, frame in frames.items():
        ids = set(frame["id"].astype(str))
        lines.append(
            f"{label}: n={len(frame)}; unique ids={len(ids)}; "
            f"same id set as {base_label}={ids == base_ids}"
        )
    return lines


def paired_summary(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    aa = frames["AA*"][["name", "exit time(s)"]].rename(columns={"exit time(s)": "aa_s"})
    rows = []
    for comparator in ["Improved A*"]:
        other = frames[comparator][["name", "exit time(s)"]].rename(
            columns={"exit time(s)": "other_s"}
        )
        paired = aa.merge(other, on="name", how="inner")
        saved = paired["other_s"].astype(float) - paired["aa_s"].astype(float)
        rows.append(
            {
                "comparison": f"AA* vs {comparator}",
                "paired_n": int(len(paired)),
                "mean_time_saved_by_AA_s": float(saved.mean()),
                "median_time_saved_by_AA_s": float(saved.median()),
                "AA_faster_n": int((saved > 0).sum()),
                "AA_faster_pct": float((saved > 0).mean() * 100.0),
                "AA_equal_n": int((saved == 0).sum()),
                "AA_slower_n": int((saved < 0).sum()),
            }
        )
    return pd.DataFrame(rows)


def set_style() -> None:
    mpl.rcParams.update(
        {
            "font.family": "Arial",
            "font.size": 7.0,
            "axes.titlesize": 8.0,
            "axes.labelsize": 7.2,
            "xtick.labelsize": 6.5,
            "ytick.labelsize": 6.5,
            "legend.fontsize": 6.6,
            "axes.linewidth": 0.65,
            "xtick.major.width": 0.6,
            "ytick.major.width": 0.6,
            "xtick.major.size": 3.0,
            "ytick.major.size": 3.0,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
            "savefig.bbox": "tight",
            "savefig.pad_inches": 0.04,
        }
    )


def finish_axis(ax: plt.Axes) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(direction="out")


def panel_label(ax: plt.Axes, label: str) -> None:
    ax.text(
        -0.15,
        1.07,
        label,
        transform=ax.transAxes,
        fontsize=9.2,
        fontweight="bold",
        va="top",
        ha="left",
    )


def build_figure(frames: dict[str, pd.DataFrame], summary: pd.DataFrame) -> None:
    set_style()
    fig, axes = plt.subplots(2, 2, figsize=(7.20, 5.05), constrained_layout=True)
    ax_a, ax_b, ax_c, ax_d = axes.flat

    for label, spec in METHODS.items():
        values = np.sort(frames[label]["exit time(s)"].astype(float).to_numpy())
        cumulative = np.arange(1, values.size + 1, dtype=float) / values.size * 100.0
        ax_a.plot(
            values,
            cumulative,
            label=label,
            color=spec["color"],
            linestyle=spec["linestyle"],
            linewidth=1.55 if label == "AA*" else 1.25,
        )
    ax_a.set_xlabel("Individual completion time (s)")
    ax_a.set_ylabel("Cumulative completed (%)")
    ax_a.set_xlim(0, 1500)
    ax_a.set_ylim(0, 101)
    ax_a.yaxis.set_major_locator(MultipleLocator(20))
    ax_a.xaxis.set_major_locator(MultipleLocator(300))
    ax_a.legend(frameon=False, loc="lower right", ncol=1, handlelength=2.6)
    ax_a.set_title("Station-wide completion profile", loc="left", pad=5)
    finish_axis(ax_a)
    panel_label(ax_a, "a")

    quantile_names = ["T50", "T80", "T95", "T99", "T100"]
    y = np.arange(len(quantile_names))
    offsets = {"Improved A*": -0.18, "AA*": 0.0, "PF-LQ": 0.18}
    for label, spec in METHODS.items():
        row = summary.loc[summary["method"] == label].iloc[0]
        values = [row[f"{name}_s"] for name in quantile_names]
        ax_b.scatter(
            values,
            y + offsets[label],
            s=23,
            marker=spec["marker"],
            color=spec["color"],
            edgecolor="white",
            linewidth=0.45,
            zorder=3,
            label=label,
        )
        ax_b.plot(values, y + offsets[label], color=spec["color"], linewidth=0.7, alpha=0.42)
    ax_b.set_yticks(y, quantile_names)
    ax_b.invert_yaxis()
    ax_b.set_xlim(0, 1500)
    ax_b.xaxis.set_major_locator(MultipleLocator(300))
    ax_b.set_xlabel("Completion-time quantile (s)")
    ax_b.set_title("Median-to-tail completion", loc="left", pad=5)
    ax_b.grid(axis="x", color="#D9D9D9", linewidth=0.45, alpha=0.65)
    finish_axis(ax_b)
    panel_label(ax_b, "b")

    for label, spec in METHODS.items():
        row = summary.loc[summary["method"] == label].iloc[0]
        x = float(row["mean_exit_time_s"])
        y_value = float(row["T100_s"])
        ax_c.scatter(
            x,
            y_value,
            s=50,
            marker=spec["marker"],
            color=spec["color"],
            edgecolor="white",
            linewidth=0.65,
            zorder=3,
        )
        dx, dy = {"Improved A*": (6, -20), "AA*": (6, 10), "PF-LQ": (6, 10)}[label]
        ax_c.annotate(label, (x, y_value), xytext=(dx, dy), textcoords="offset points", color=spec["color"])
    ax_c.set_xlim(330, 455)
    ax_c.set_ylim(1200, 1500)
    ax_c.set_xlabel("Mean completion time (s)")
    ax_c.set_ylabel("Last completion, T100 (s)")
    ax_c.set_title("Mean–tail trade-off", loc="left", pad=5)
    ax_c.annotate(
        "lower is faster",
        xy=(342, 1220),
        xytext=(390, 1285),
        arrowprops={"arrowstyle": "->", "lw": 0.7, "color": "#555555"},
        color="#555555",
        ha="center",
    )
    finish_axis(ax_c)
    panel_label(ax_c, "c")

    for label, spec in METHODS.items():
        row = summary.loc[summary["method"] == label].iloc[0]
        x = float(row["mean_distance_m"])
        y_value = float(row["mean_congestion_time_s"])
        ax_d.scatter(
            x,
            y_value,
            s=50,
            marker=spec["marker"],
            color=spec["color"],
            edgecolor="white",
            linewidth=0.65,
            zorder=3,
        )
        dx, dy = {"Improved A*": (6, 7), "AA*": (6, 7), "PF-LQ": (6, -14)}[label]
        ax_d.annotate(label, (x, y_value), xytext=(dx, dy), textcoords="offset points", color=spec["color"])
    x_min = float(summary["mean_distance_m"].min()) - 5
    x_max = float(summary["mean_distance_m"].max()) + 8
    y_min = float(summary["mean_congestion_time_s"].min()) - 12
    y_max = float(summary["mean_congestion_time_s"].max()) + 12
    ax_d.set_xlim(x_min, x_max)
    ax_d.set_ylim(y_min, y_max)
    ax_d.set_xlabel("Mean distance travelled (m)")
    ax_d.set_ylabel("Mean congestion time (s)")
    ax_d.set_title("Route–waiting consequence", loc="left", pad=5)
    ax_d.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:.0f}"))
    finish_axis(ax_d)
    panel_label(ax_d, "d")

    fig.suptitle(
        "Cross-model microscopic comparison under train-arrival-augmented demand",
        x=0.01,
        y=1.02,
        ha="left",
        fontsize=9.4,
        fontweight="bold",
    )

    stem = OUT / "fig2_pathfinder_high_load_validation"
    fig.savefig(stem.with_suffix(".png"), dpi=400, facecolor="white")
    fig.savefig(stem.with_suffix(".pdf"), facecolor="white")
    fig.savefig(stem.with_suffix(".svg"), facecolor="white")
    fig.savefig(stem.with_suffix(".tiff"), dpi=600, facecolor="white", pil_kwargs={"compression": "tiff_lzw"})
    plt.close(fig)


def main() -> None:
    for label, spec in METHODS.items():
        for key in ["occupants", "params", "geom"]:
            path = spec[key]
            if not path.exists():
                raise FileNotFoundError(f"Missing {label} {key}: {path}")

    frames = {label: read_csv(spec["occupants"]) for label, spec in METHODS.items()}
    summary = pd.DataFrame([summarize(label, frame) for label, frame in frames.items()])
    summary.to_csv(OUT / "table_pathfinder_high_load_summary.csv", index=False, encoding="utf-8-sig")
    paired_summary(frames).to_csv(
        OUT / "table_pathfinder_high_load_paired.csv", index=False, encoding="utf-8-sig"
    )
    write_completion_source(frames)
    (OUT / "pathfinder_high_load_equivalence_audit.txt").write_text(
        "\n".join(equivalence_audit(frames)) + "\n", encoding="utf-8"
    )
    build_figure(frames, summary)
    print(summary.to_string(index=False))
    print()
    print(paired_summary(frames).to_string(index=False))


if __name__ == "__main__":
    main()
