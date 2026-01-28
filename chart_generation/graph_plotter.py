"""Production plotting utilities."""

import matplotlib
matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import MultipleLocator


def plot_crosses(df, channel, data, ax, label_positions=None):
    """Plot marker crosses at specified data points with annotations."""
    if df is not None:
        label_positions = label_positions or {}

        # Ensure the annotated axis is drawn above the others
        ax.set_zorder(3)
        ax.patch.set_visible(False)

        # Predefined annotation positions for all key points
        predefined_positions = {
            "SOS": {"x_offset": 10, "y_offset": 10},
            "SOH": {"x_offset": 10, "y_offset": 10},
            "EOH": {"x_offset": 10, "y_offset": 10},
        }

        idx_cols = [c for c in df.columns if c.endswith("_Index")]

        for col in idx_cols:
            label = col.removesuffix("_Index")
            idxs = df[col].dropna().astype(int)

            for idx in idxs:
                t = data["Datetime"].loc[idx]
                y = data[channel].loc[idx]

                # Use predefined first, then user-defined overrides if given
                pos = label_positions.get(label, predefined_positions.get(label, {}))
                offset_x = pos.get("x_offset", 0)
                offset_y = pos.get("y_offset", 5)

                ax.plot(
                    t, y,
                    marker='x',
                    linestyle='none',
                    markersize=8,
                    color='black',
                )
                ax.annotate(
                    label,
                    xy=(t, y),
                    xytext=(offset_x, offset_y),
                    textcoords="offset points",
                    ha="center",
                    va="center",
                    fontsize=10,
                )


def plot_production_channel_data(cleaned_data):
    """Generate production chart with pressure and ambient temperature."""
    # Copy so we don't modify the caller's dataframe
    df = cleaned_data.copy()

    # Parse Datetime (drop any bad rows)
    df = df.dropna(subset=["Datetime"])

    pressure_cols = [c for c in df.columns if c not in ("Datetime", "Ambient Temperature")]

    pressure_col = pressure_cols[0]

    axis_map = {"Pressure": "left", "Temperature": "right"}

    # Create axes
    fig, ax_p = plt.subplots(figsize=(11.96, 8.49))
    ax_t = ax_p.twinx()
    axes = {"left": ax_p, "right": ax_t}

    # Plot pressure (left)
    p_label = f"{pressure_col} (psi)"
    p_line = ax_p.plot(df["Datetime"], df[pressure_col], label=p_label, color="#FF0000", lw=1)[0]
    ax_p.set_ylabel(p_label, color="#FF0000")
    ax_p.tick_params(axis="y", colors="#FF0000")
    ax_p.spines["top"].set_visible(False)
    ax_p.spines["right"].set_visible(False)
    ax_p.spines["left"].set_edgecolor("#FF0000")
    ax_p.spines["left"].set_linewidth(0.5)
    ax_p.spines["bottom"].set_linewidth(0.5)
    ax_p.margins(x=0)
    ax_p.set_ylim(0, ax_p.get_ylim()[1])

    # Plot ambient temperature (right)
    t_label = "Ambient Temperature (°C)"
    t_line = ax_t.plot(df["Datetime"], df["Ambient Temperature"], label=t_label, color="#0000FF", ls=":", lw=1)[0]
    ax_t.set_ylabel(t_label, color="#0000FF")
    ax_t.tick_params(axis="y", colors="#0000FF")
    ax_t.spines["top"].set_visible(False)
    ax_t.spines["left"].set_visible(False)
    ax_t.spines["bottom"].set_visible(False)
    ax_t.spines["right"].set_edgecolor("#0000FF")
    ax_t.spines["right"].set_linewidth(0.5)
    ax_t.margins(x=0)
    ax_t.set_ylim(-60, 260)
    ax_t.yaxis.set_major_locator(MultipleLocator(10))

    # X axis formatting
    ax_p.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m/%Y\n%H:%M:%S"))
    x_min, x_max = df["Datetime"].min(), df["Datetime"].max()
    if pd.notna(x_min) and pd.notna(x_max) and x_min != x_max:
        ax_p.set_xticks(pd.date_range(x_min, x_max, periods=10))

    # Legend + layout
    fig.legend([p_line, t_line], [p_label, t_label], loc="lower center", ncol=2, frameon=False, bbox_to_anchor=(0.5, 0.05))
    fig.tight_layout(rect=[0, 0.075, 1, 1])

    return fig, ax_p


def plot_calibration_data(cleaned_data, channel_index=None):
    """Generate calibration chart with the calibrated channel as the only axis."""
    df = cleaned_data.copy()
    df = df.dropna(subset=["Datetime"])

    # Create axes
    fig, ax_p = plt.subplots(figsize=(11.96, 8.49))

    # Legend label should show Channel "index"
    legend_label = f"Channel {channel_index}" if channel_index is not None else "Channel"

    # All calibration plots use "Counts" for the Y-axis title.
    y_label = "Counts"

    # Plot calibrated channel (left)
    p_line = ax_p.plot(df["Datetime"], df["Calibrated Channel"], label=legend_label, color="#FF0000", lw=1)[0]
    ax_p.set_ylabel(y_label, color="#FF0000")
    ax_p.tick_params(axis="y", colors="#FF0000")
    ax_p.spines["top"].set_visible(False)
    ax_p.spines["right"].set_visible(False)
    ax_p.spines["left"].set_edgecolor("#FF0000")
    ax_p.spines["left"].set_linewidth(0.5)
    ax_p.spines["bottom"].set_linewidth(0.5)
    ax_p.margins(x=0)

    # X axis formatting
    ax_p.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m/%Y\n%H:%M:%S"))
    x_min, x_max = df["Datetime"].min(), df["Datetime"].max()
    if pd.notna(x_min) and pd.notna(x_max) and x_min != x_max:
        ax_p.set_xticks(pd.date_range(x_min, x_max, periods=10))

    # Legend + layout
    fig.legend([p_line], [legend_label], loc="lower center", ncol=1, frameon=False, bbox_to_anchor=(0.5, 0.05))
    fig.tight_layout(rect=[0, 0.075, 1, 1])

    return fig, ax_p
