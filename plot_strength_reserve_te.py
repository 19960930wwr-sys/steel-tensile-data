from pathlib import Path

import pandas as pd
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(r"E:\本人信息\博士后\Papers\steel_data_extraction")
DATA_PATH = ROOT / "origin_ready_strength_reserve_TE_plot.xlsx"
PNG_PATH = ROOT / "strength_reserve_vs_total_elongation.png"


def main() -> None:
    scatter = pd.read_excel(DATA_PATH, sheet_name="scatter")
    quartile_band = pd.read_excel(DATA_PATH, sheet_name="quartile_band")
    median_line = pd.read_excel(DATA_PATH, sheet_name="median_line")

    width, height = 2160, 1680
    left, right, top, bottom = 220, 80, 80, 190
    plot_w = width - left - right
    plot_h = height - top - bottom

    x_min, x_max = 0.0, 0.8
    y_min, y_max = 0.0, 120.0

    def sx(x: float) -> float:
        return left + (x - x_min) / (x_max - x_min) * plot_w

    def sy(y: float) -> float:
        return top + plot_h - (y - y_min) / (y_max - y_min) * plot_h

    img = Image.new("RGBA", (width, height), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img, "RGBA")

    try:
        font_axis = ImageFont.truetype("arial.ttf", 80)
        font_tick = ImageFont.truetype("arial.ttf", 60)
        font_note = ImageFont.truetype("arial.ttf", 42)
    except OSError:
        font_axis = ImageFont.load_default()
        font_tick = ImageFont.load_default()
        font_note = ImageFont.load_default()

    # Quartile band
    upper = [(sx(x), sy(y)) for x, y in zip(quartile_band["x_center"], quartile_band["TE_q3"])]
    lower = [(sx(x), sy(y)) for x, y in zip(reversed(quartile_band["x_center"]), reversed(quartile_band["TE_q1"]))]
    band_polygon = upper + lower
    draw.polygon(band_polygon, fill=(144, 183, 255, 110))

    # Scatter points
    r = 5
    for x, y in zip(scatter["strength_reserve"], scatter["total_elongation"]):
        px, py = sx(float(x)), sy(float(y))
        draw.ellipse((px - r, py - r, px + r, py + r), fill=(93, 109, 242, 45))

    # Median line
    median_points = [(sx(x), sy(y)) for x, y in zip(median_line["x_center"], median_line["TE_median"])]
    draw.line(median_points, fill=(23, 59, 140, 255), width=8)

    # Axes
    axis_color = (30, 30, 30, 255)
    draw.line((left, top, left, top + plot_h), fill=axis_color, width=5)
    draw.line((left, top + plot_h, left + plot_w, top + plot_h), fill=axis_color, width=5)

    # Ticks and labels
    for xv in [0, 0.2, 0.4, 0.6, 0.8]:
        px = sx(xv)
        draw.line((px, top + plot_h, px, top + plot_h - 20), fill=axis_color, width=4)
        label = f"{xv:.1f}"
        bbox = draw.textbbox((0, 0), label, font=font_tick)
        draw.text((px - (bbox[2] - bbox[0]) / 2, top + plot_h + 26), label, fill=axis_color, font=font_tick)

    for yv in [0, 20, 40, 60, 80, 100, 120]:
        py = sy(yv)
        draw.line((left, py, left + 20, py), fill=axis_color, width=4)
        label = f"{yv:d}"
        bbox = draw.textbbox((0, 0), label, font=font_tick)
        draw.text((left - 28 - (bbox[2] - bbox[0]), py - (bbox[3] - bbox[1]) / 2), label, fill=axis_color, font=font_tick)

    # Axis titles
    x_title = "Strain-hardening reserve, 1 - σy/σt"
    bbox = draw.textbbox((0, 0), x_title, font=font_axis)
    draw.text((left + plot_w / 2 - (bbox[2] - bbox[0]) / 2, height - 105), x_title, fill=axis_color, font=font_axis)

    y_title = "Total elongation (%)"
    y_text = Image.new("RGBA", (80, 700), (255, 255, 255, 0))
    y_draw = ImageDraw.Draw(y_text)
    y_draw.text((0, 0), y_title, fill=axis_color, font=font_axis)
    y_text = y_text.rotate(90, expand=True)
    img.alpha_composite(y_text, (40, top + plot_h // 2 - y_text.height // 2))

    # Note
    note = f"n = {len(scatter):,}"
    bbox = draw.textbbox((0, 0), note, font=font_note)
    draw.text((width - right - (bbox[2] - bbox[0]), top + 10), note, fill=axis_color, font=font_note)

    img.convert("RGB").save(PNG_PATH)
    print(PNG_PATH)


if __name__ == "__main__":
    main()
