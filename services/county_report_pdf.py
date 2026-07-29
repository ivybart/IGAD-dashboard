"""Focused PDF export of the county planning brief shown in the dashboard."""

from __future__ import annotations

from io import BytesIO
from math import isfinite

from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas


PAGE_W, PAGE_H = A4
INK = HexColor("#173B36")
MUTED = HexColor("#697B76")
GREEN = HexColor("#27866F")
DEEP_GREEN = HexColor("#123D3A")
LIGHT_GREEN = HexColor("#EDF4F0")
LINE = HexColor("#DDE7E2")
AMBER = HexColor("#F0B541")
RED = HexColor("#C95F4B")
GOOD = HexColor("#69A85E")
PANEL = HexColor("#F7F9F8")


def _text(canvas: Canvas, value: object, x: float, y: float, size: float = 9, color=INK, font: str = "Helvetica") -> None:
    canvas.setFillColor(color)
    canvas.setFont(font, size)
    canvas.drawString(x, y, str(value))


def _right_text(canvas: Canvas, value: object, x: float, y: float, size: float = 9, color=INK, font: str = "Helvetica") -> None:
    canvas.setFillColor(color)
    canvas.setFont(font, size)
    canvas.drawRightString(x, y, str(value))


def _wrap_lines(value: str, width: float, size: float, font: str = "Helvetica") -> list[str]:
    words = value.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if not current or stringWidth(candidate, font, size) <= width:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _wrap(canvas: Canvas, value: str, x: float, y: float, width: float, size: float = 8.5, leading: float = 11, color=INK, max_lines: int = 4, font: str = "Helvetica") -> float:
    lines = _wrap_lines(value, width, size, font)
    for index, line in enumerate(lines[:max_lines]):
        suffix = "..." if index == max_lines - 1 and len(lines) > max_lines else ""
        _text(canvas, line + suffix, x, y - index * leading, size, color, font)
    return y - min(len(lines), max_lines) * leading


def _panel(canvas: Canvas, x: float, y: float, width: float, height: float, fill=white, stroke=LINE) -> None:
    canvas.setFillColor(fill)
    canvas.setStrokeColor(stroke)
    canvas.setLineWidth(0.7)
    canvas.rect(x, y, width, height, fill=1, stroke=1)


def _value(column: str, value: float) -> str:
    if not isfinite(value):
        return "NA"
    return f"{value:.3f}" if column in ("NDVI", "msdi") else f"{value:.1f}"


def _draw_header(canvas: Canvas, county: str, selected_date, condition: str) -> None:
    canvas.setFillColor(DEEP_GREEN)
    canvas.rect(0, PAGE_H - 118, PAGE_W, 118, fill=1, stroke=0)
    _text(canvas, "RANGELAND OBSERVATORY HUB  /  COUNTY PLANNING", 32, PAGE_H - 30, 7.4, HexColor("#A8D2C4"), "Helvetica-Bold")
    _text(canvas, "County planning brief", 32, PAGE_H - 67, 24, white, "Helvetica-Bold")
    _text(canvas, f"{selected_date:%B %Y}".upper(), PAGE_W - 150, PAGE_H - 37, 8, white, "Helvetica-Bold")
    _text(canvas, condition.upper(), PAGE_W - 150, PAGE_H - 68, 11, AMBER, "Helvetica-Bold")
    _text(canvas, "Grazing conditions and early-action priorities", 32, PAGE_H - 92, 8.5, HexColor("#CFE2DB"))


def _draw_metrics(canvas: Canvas, summary: dict, metric_labels: dict) -> None:
    metrics, baseline = summary["metrics"], summary["baseline"]
    x, y, gap = 32, 574, 7
    width = (PAGE_W - 64 - gap * 4) / 5
    for column in metric_labels:
        _panel(canvas, x, y, width, 69, PANEL)
        _text(canvas, metric_labels[column].upper(), x + 8, y + 51, 6, MUTED, "Helvetica-Bold")
        _text(canvas, _value(column, metrics[column]), x + 8, y + 29, 14, INK, "Helvetica-Bold")
        precision = 3 if column in ("NDVI", "msdi") else 1
        delta = metrics[column] - baseline[column]
        _text(canvas, f"LTA {baseline[column]:.{precision}f} / {delta:+.{precision}f}", x + 8, y + 10, 5.5, GREEN)
        x += width + gap


def _draw_wards(canvas: Canvas, summary: dict) -> None:
    x, y, gap = 32, 471, 12
    width = (PAGE_W - 64 - gap) / 2
    items = [
        ("PRIORITY WARDS", "Poor / very poor", summary["bad_wards"], RED),
        ("STRONGER WARDS", "Good / very good", summary["good_wards"], GOOD),
    ]
    for kicker, heading, wards, accent in items:
        _panel(canvas, x, y, width, 82, white)
        canvas.setFillColor(accent)
        canvas.rect(x, y, 4, 82, fill=1, stroke=0)
        _text(canvas, kicker, x + 14, y + 62, 6.4, accent, "Helvetica-Bold")
        _text(canvas, heading, x + 14, y + 45, 10, INK, "Helvetica-Bold")
        names = ", ".join(f"{ward['ADM3_EN']} - {ward['GCI']:.1f}" for ward in wards) or "None in this month"
        _wrap(canvas, names, x + 14, y + 26, width - 28, 8.2, 10, INK, 2, "Helvetica-Bold")
        x += width + gap


def _draw_outlook(canvas: Canvas, outlook: dict, metric_labels: dict) -> None:
    x, y, width, height = 32, 295, PAGE_W - 64, 155
    canvas.setFillColor(DEEP_GREEN)
    canvas.rect(x, y, width, height, fill=1, stroke=0)
    _text(canvas, "NEXT-MONTH OUTLOOK", x + 16, y + height - 23, 6.5, HexColor("#A8D2C4"), "Helvetica-Bold")
    _text(canvas, f"Trend estimate for {outlook['target_date']:%B %Y}", x + 16, y + height - 44, 13, white, "Helvetica-Bold")

    gap = 8
    cell_width = (width - 32 - gap * 4) / 5
    for index, column in enumerate(metric_labels):
        result = outlook[column]
        cx = x + 16 + index * (cell_width + gap)
        _text(canvas, metric_labels[column], cx, y + 84, 6.2, HexColor("#A8D2C4"), "Helvetica-Bold")
        _text(canvas, _value(column, result["point"]), cx, y + 61, 13, white, "Helvetica-Bold")
        precision = 3 if column in ("NDVI", "msdi") else 1
        range_text = (
            f"95% range {result['lower']:.{precision}f}-{result['upper']:.{precision}f}"
            if isfinite(result["lower"])
            else "Insufficient history"
        )
        _wrap(canvas, range_text, cx, y + 43, cell_width, 5.3, 7, AMBER, 2)

    method = "Ranges come from a linear trend fitted only to prior observations for the forecast month; they express statistical uncertainty, not a weather forecast."
    _wrap(canvas, method, x + 16, y + 18, width - 32, 6.4, 8, HexColor("#CFE2DB"), 2)


def _draw_actions(canvas: Canvas, actions: list[str]) -> None:
    _text(canvas, "Recommended planning checks", 32, 268, 12, INK, "Helvetica-Bold")
    cursor = 247
    for index, action in enumerate(actions, start=1):
        canvas.setFillColor(LIGHT_GREEN)
        canvas.circle(39, cursor + 2, 7, fill=1, stroke=0)
        _text(canvas, index, 36.5, cursor - 0.5, 6.5, GREEN, "Helvetica-Bold")
        next_cursor = _wrap(canvas, action, 54, cursor + 5, PAGE_W - 86, 8.2, 10.5, INK, 2)
        cursor = next_cursor - 7

    caveat_y = max(55, cursor - 56)
    _panel(canvas, 32, caveat_y, PAGE_W - 64, 47, LIGHT_GREEN, LIGHT_GREEN)
    _text(canvas, "SCREENING BRIEF", 46, caveat_y + 29, 6.2, GREEN, "Helvetica-Bold")
    caveat = "Confirm resource access, ownership, condition and local authority guidance before deployment."
    _wrap(canvas, caveat, 46, caveat_y + 15, PAGE_W - 92, 7.5, 9, INK, 2)


def build_county_report_pdf(*, county: str, selected_date, condition: str, summary: dict, outlook: dict, metric_labels: dict, actions: list[str]) -> bytes:
    """Create the downloadable one-page version of the on-screen county brief."""
    stream = BytesIO()
    canvas = Canvas(stream, pagesize=A4, pageCompression=1)
    canvas.setTitle(f"{county} county planning brief - {selected_date:%B %Y}")
    canvas.setAuthor("Rangeland Observatory Hub")

    _draw_header(canvas, county, selected_date, condition)
    _text(canvas, f"{county} grazing and resource brief", 32, 695, 18, INK, "Helvetica-Bold")
    priority = len(summary["bad_wards"])
    lead = (
        f"The county mean GCI is {summary['metrics']['GCI']:.1f}, classified as {condition.lower()}. "
        f"The assessment covers {summary['wards']} wards; {priority} "
        f"{'is' if priority == 1 else 'are'} currently poor or very poor."
    )
    _wrap(canvas, lead, 32, 674, PAGE_W - 64, 9.2, 12, MUTED, 2)
    _draw_metrics(canvas, summary, metric_labels)
    _draw_wards(canvas, summary)
    _draw_outlook(canvas, outlook, metric_labels)
    _draw_actions(canvas, actions)

    canvas.setStrokeColor(LINE)
    canvas.line(32, 33, PAGE_W - 32, 33)
    _text(canvas, "© GeoObservatory 2026", 32, 19, 6.4, MUTED)
    _right_text(canvas, "County planning brief", PAGE_W - 32, 19, 6.4, MUTED)
    canvas.save()
    return stream.getvalue()
