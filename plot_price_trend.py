"""Plot average price trend by brand from china_nev_price_war.csv."""

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

CSV_PATH = "docs/china_nev_price_war.csv"
OUTPUT_PATH = "price_trend.png"

# Fixed categorical order + colors: deep red for the most aggressive price
# cutters, black/gray steps for the rest. Kept in a fixed order (never
# re-cycled) so a brand's color stays stable if the data is re-sorted.
BRAND_COLORS = {
    "BYD": "#8B1A1A",       # deep red (hero) - steepest cuts, entry EV
    "Xiaopeng": "#D9534F",  # lighter red
    "Tesla": "#1A1A1A",     # near-black
    "NIO": "#6E6E6E",       # dark gray
    "Geely": "#A6A6A6",     # light gray
}

df = pd.read_csv(CSV_PATH)
months = sorted(df["month"].unique())

fig, ax = plt.subplots(figsize=(10, 6), dpi=150)
fig.patch.set_facecolor("white")
ax.set_facecolor("white")

for brand, color in BRAND_COLORS.items():
    sub = df[df["brand"] == brand].sort_values("month")
    x = sub["month"]
    y = sub["avg_price_usd"]

    ax.plot(
        x, y,
        color=color,
        linewidth=2,
        solid_joinstyle="round",
        solid_capstyle="round",
        label=brand,
        zorder=3,
    )
    # End marker with a surface-color ring so it stays legible over the line.
    ax.plot(
        x.iloc[-1], y.iloc[-1],
        marker="o", markersize=8,
        markerfacecolor=color, markeredgecolor="white", markeredgewidth=1.5,
        zorder=4,
    )
    # Direct end label, in ink (not the series color), supplementing the legend.
    ax.annotate(
        brand,
        xy=(x.iloc[-1], y.iloc[-1]),
        xytext=(8, 0), textcoords="offset points",
        va="center", ha="left",
        fontsize=9, color="#333333",
    )

# Recessive, hairline gridlines behind the data.
ax.yaxis.grid(True, color="#e0e0e0", linewidth=0.8, zorder=0)
ax.xaxis.grid(False)
ax.set_axisbelow(True)

for spine in ("top", "right"):
    ax.spines[spine].set_visible(False)
for spine in ("left", "bottom"):
    ax.spines[spine].set_color("#b0b0b0")

ax.set_xlabel("Month", color="#333333")
ax.set_ylabel("Average Price (USD)", color="#333333")
ax.set_title(
    "China NEV Price War: Average Price Trend (2023-2024)",
    fontsize=14, fontweight="bold", color="#1a1a1a", pad=14,
)
ax.set_xlim(-0.3, len(months) - 0.3 + 0.6)  # extra room for end labels
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"${v:,.0f}"))
ax.tick_params(colors="#333333")

ax.legend(
    loc="upper right", frameon=False, fontsize=9,
    title="Brand", title_fontsize=9,
)

fig.tight_layout()
fig.savefig(OUTPUT_PATH, dpi=150, facecolor="white")
print(f"Saved {OUTPUT_PATH}")
