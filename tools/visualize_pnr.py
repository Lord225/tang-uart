#!/usr/bin/env python3
"""Generate a LUT placement heatmap from a nextpnr JSON file."""

from __future__ import annotations

import argparse
import html
import json
import re
from collections import defaultdict
from pathlib import Path


BEL_RE = re.compile(r"^X(?P<x>\d+)Y(?P<y>\d+)/(?P<bel>[^/]+)$")
LUT_TYPES = ("LUT", "MUX2_LUT")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate an HTML LUT heatmap from build/top_pnr.json."
    )
    parser.add_argument(
        "--input",
        "-i",
        type=Path,
        default=Path("build/top_pnr.json"),
        help="nextpnr JSON input file.",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("build/top_visualization.html"),
        help="HTML output file.",
    )
    parser.add_argument(
        "--top",
        default="top",
        help="Module name to visualize.",
    )
    return parser.parse_args()


def is_lut_cell(cell_type: str) -> bool:
    return cell_type.startswith(LUT_TYPES)


def load_lut_tiles(path: Path, module_name: str) -> tuple[dict[tuple[int, int], list[str]], int]:
    with path.open() as f:
        design = json.load(f)

    modules = design.get("modules", {})
    if module_name not in modules:
        available = ", ".join(sorted(modules)) or "<none>"
        raise SystemExit(f"Module {module_name!r} not found. Available modules: {available}")

    tiles: dict[tuple[int, int], list[str]] = defaultdict(list)
    lut_cell_count = 0

    for cell_name, cell in modules[module_name].get("cells", {}).items():
        cell_type = cell.get("type", "")
        if not is_lut_cell(cell_type):
            continue

        bel = cell.get("attributes", {}).get("NEXTPNR_BEL")
        if not bel:
            continue

        match = BEL_RE.match(bel)
        if not match:
            continue

        lut_cell_count += 1
        x = int(match.group("x"))
        y = int(match.group("y"))
        bel_name = match.group("bel")
        tiles[(x, y)].append(f"{cell_name} ({cell_type}, {bel_name})")

    return tiles, lut_cell_count


def color_for_count(count: int, max_count: int) -> str:
    if count == 0:
        return "#f4f4f5"

    scale = count / max_count
    if scale <= 0.25:
        return "#bae6fd"
    if scale <= 0.50:
        return "#38bdf8"
    if scale <= 0.75:
        return "#facc15"
    return "#ef4444"


def render_html(tiles: dict[tuple[int, int], list[str]], lut_cell_count: int) -> str:
    if tiles:
        max_x = max(x for x, _ in tiles)
        max_y = max(y for _, y in tiles)
        max_count = max(len(cells) for cells in tiles.values())
    else:
        max_x = max_y = 0
        max_count = 1

    cell_size = 12
    gap = 1
    label_margin = 44
    width = label_margin + ((max_x + 1) * (cell_size + gap))
    height = label_margin + ((max_y + 1) * (cell_size + gap))

    rects: list[str] = []
    for y in range(max_y, -1, -1):
        for x in range(max_x + 1):
            count = len(tiles.get((x, y), []))
            fill = color_for_count(count, max_count)
            svg_x = label_margin + x * (cell_size + gap)
            svg_y = (max_y - y) * (cell_size + gap)
            title_lines = [f"X{x}Y{y}: {count} LUT cell(s)"]
            title_lines.extend(tiles.get((x, y), []))
            title = html.escape("\n".join(title_lines))
            rects.append(
                f'<rect x="{svg_x}" y="{svg_y}" width="{cell_size}" height="{cell_size}" '
                f'rx="1" fill="{fill}"><title>{title}</title></rect>'
            )

    x_labels = []
    for x in range(max_x + 1):
        if x % 5 == 0 or x == max_x:
            svg_x = label_margin + x * (cell_size + gap) + cell_size / 2
            x_labels.append(
                f'<text x="{svg_x}" y="{height - 18}" text-anchor="middle">{x}</text>'
            )

    y_labels = []
    for y in range(max_y + 1):
        if y % 5 == 0 or y == max_y:
            svg_y = (max_y - y) * (cell_size + gap) + cell_size * 0.8
            y_labels.append(f'<text x="32" y="{svg_y}" text-anchor="end">{y}</text>')

    legend = f"""
      <div class="legend">
        <span><i style="background:#f4f4f5"></i>0</span>
        <span><i style="background:#bae6fd"></i>low</span>
        <span><i style="background:#38bdf8"></i>medium</span>
        <span><i style="background:#facc15"></i>high</span>
        <span><i style="background:#ef4444"></i>max ({max_count}/tile)</span>
      </div>
    """

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LUT Heatmap</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #ffffff;
      color: #18181b;
    }}
    body {{
      margin: 0;
      padding: 24px;
    }}
    header {{
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 24px;
      margin-bottom: 18px;
    }}
    h1 {{
      margin: 0;
      font-size: 22px;
      font-weight: 700;
    }}
    .meta {{
      margin-top: 6px;
      color: #52525b;
      font-size: 14px;
    }}
    .legend {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      font-size: 13px;
      color: #3f3f46;
    }}
    .legend span {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }}
    .legend i {{
      width: 14px;
      height: 14px;
      border: 1px solid #d4d4d8;
      display: inline-block;
    }}
    .canvas {{
      overflow: auto;
      border: 1px solid #d4d4d8;
      background: #fafafa;
      padding: 16px;
    }}
    svg {{
      display: block;
      background: #ffffff;
    }}
    text {{
      fill: #52525b;
      font-size: 10px;
    }}
  </style>
</head>
<body>
  <header>
    <div>
      <h1>LUT Heatmap</h1>
      <div class="meta">{lut_cell_count} placed LUT cells across {len(tiles)} occupied tiles</div>
    </div>
    {legend}
  </header>
  <main class="canvas">
    <svg width="{width}" height="{height}" role="img" aria-label="LUT placement heatmap">
      <g>
        {''.join(rects)}
      </g>
      <g>
        {''.join(x_labels)}
        {''.join(y_labels)}
        <text x="{label_margin}" y="{height - 2}">X</text>
        <text x="0" y="12">Y</text>
      </g>
    </svg>
  </main>
</body>
</html>
"""


def main() -> None:
    args = parse_args()
    if not args.input.exists():
        raise SystemExit(f"Input file not found: {args.input}. Run `just default` first.")

    tiles, lut_cell_count = load_lut_tiles(args.input, args.top)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_html(tiles, lut_cell_count))
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
