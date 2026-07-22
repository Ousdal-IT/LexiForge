from collections.abc import Mapping
from html import escape


def bar_chart_svg(title: str, values: Mapping[str, int], *, width: int = 720) -> str:
    """Render a deterministic, accessible pure-XML horizontal bar chart."""
    ordered = sorted(values.items())
    row_height = 28
    top = 48
    label_width = 150
    chart_width = width - label_width - 40
    height = top + max(1, len(ordered)) * row_height + 24
    maximum = max((value for _, value in ordered), default=1) or 1
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title">'
        ),
        f'  <title id="title">{escape(title)}</title>',
        "  <style>text{font-family:system-ui,sans-serif;font-size:13px}.bar{fill:#315b8a}</style>",
        f'  <text x="12" y="28" font-size="18">{escape(title)}</text>',
    ]
    if not ordered:
        lines.append(f'  <text x="12" y="{top + 18}">No data</text>')
    for index, (label, value) in enumerate(ordered):
        y = top + index * row_height
        bar_width = round(chart_width * value / maximum)
        lines.extend(
            [
                f'  <text x="12" y="{y + 17}">{escape(str(label))}</text>',
                (
                    f'  <rect class="bar" x="{label_width}" y="{y + 3}" '
                    f'width="{bar_width}" height="18"/>'
                ),
                f'  <text x="{label_width + bar_width + 6}" y="{y + 17}">{value}</text>',
            ]
        )
    lines.append("</svg>")
    return "\n".join(lines) + "\n"
