from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _compute_weights(headers: list[str], rows: list[list[str]]) -> list[float]:
    sample_rows = rows[:60]
    weights: list[float] = []
    for col_idx, header in enumerate(headers):
        max_len = len(header)
        for row in sample_rows:
            if col_idx >= len(row):
                continue
            text = row[col_idx] or ""
            lines = text.split("\n")
            line_max = max((len(line) for line in lines), default=0)
            max_len = max(max_len, min(line_max, 52))
        weights.append(max(8.0, float(max_len)))
    return weights


def _normalize_widths(weights: list[float], target: float) -> list[float]:
    total = sum(weights) or 1.0
    return [target * (weight / total) for weight in weights]


def _pick_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in ("arial.ttf", "segoeui.ttf", "tahoma.ttf"):
        try:
            return ImageFont.truetype(name, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, width: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if draw.textlength(candidate, font=font) <= width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _draw_cell_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    x: int,
    y: int,
    w: int,
    h: int,
    font: ImageFont.ImageFont,
    color: tuple[int, int, int],
) -> None:
    padding = 8
    max_width = max(22, w - (padding * 2))
    lines: list[str] = []
    for block in (text or "").split("\n"):
        lines.extend(_wrap_text(draw, block, font, max_width))
    if not lines:
        lines = [""]

    line_height = 14
    max_lines = max(1, (h - (padding * 2)) // line_height)
    for idx, line in enumerate(lines[:max_lines]):
        draw.text((x + padding, y + padding + (idx * line_height)), line, fill=color, font=font)


def build_table_pdf_bytes(
    title: str,
    subtitle: str,
    headers: list[str],
    rows: list[list[str]],
) -> bytes:
    if not headers:
        raise ValueError("Debe existir al menos una columna para exportar")

    buffer = BytesIO()
    page_w, _ = landscape(A4)
    left_margin = 18
    right_margin = 18
    top_margin = 20
    bottom_margin = 20

    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=left_margin,
        rightMargin=right_margin,
        topMargin=top_margin,
        bottomMargin=bottom_margin,
    )

    styles = getSampleStyleSheet()
    cell_style = ParagraphStyle(
        "TableCell",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
    )

    table_data: list[list[Paragraph]] = [[Paragraph(f"<b>{header}</b>", cell_style) for header in headers]]
    for row in rows:
        table_data.append([Paragraph((value or "-").replace("\n", "<br/>"), cell_style) for value in row])

    weights = _compute_weights(headers, rows)
    available = page_w - left_margin - right_margin
    col_widths = _normalize_widths(weights, available)

    table = Table(table_data, repeatRows=1, colWidths=col_widths)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f766e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d0d7de")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fbfd")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )

    content = [
        Paragraph(title, styles["Title"]),
        Paragraph(subtitle, styles["Heading4"]),
        Spacer(1, 8),
        table,
    ]
    doc.build(content)
    return buffer.getvalue()


def build_table_png_bytes(
    title: str,
    subtitle: str,
    headers: list[str],
    rows: list[list[str]],
    max_rows: int = 120,
) -> bytes:
    if not headers:
        raise ValueError("Debe existir al menos una columna para exportar")

    clipped_rows = list(rows)
    if len(clipped_rows) > max_rows:
        omitted = len(clipped_rows) - max_rows + 1
        clipped_rows = clipped_rows[: max_rows - 1]
        clipped_rows.append([f"... {omitted} filas omitidas"] + [""] * (len(headers) - 1))

    weights = _compute_weights(headers, clipped_rows)
    raw_widths = [max(120, int(weight * 12)) for weight in weights]
    total_raw = sum(raw_widths)
    max_total = 3400
    if total_raw > max_total:
        ratio = max_total / total_raw
        col_widths = [max(90, int(width * ratio)) for width in raw_widths]
    else:
        col_widths = raw_widths

    margin = 24
    title_h = 86
    header_h = 44
    row_h = 94 if len(headers) > 8 else 112
    width = (margin * 2) + sum(col_widths)
    height = (margin * 2) + title_h + header_h + (len(clipped_rows) * row_h)

    image = Image.new("RGB", (width, height), color=(250, 252, 253))
    draw = ImageDraw.Draw(image)
    font_title = _pick_font(28)
    font_header = _pick_font(16)
    font_cell = _pick_font(14)

    draw.rectangle((0, 0, width, 58), fill=(15, 118, 110))
    draw.text((margin, 14), title, fill=(255, 255, 255), font=font_title)
    draw.text((margin, 64), subtitle, fill=(20, 27, 35), font=font_header)

    x = margin
    y = margin + title_h
    for idx, header in enumerate(headers):
        w = col_widths[idx]
        draw.rectangle((x, y, x + w, y + header_h), fill=(15, 118, 110), outline=(223, 230, 236))
        draw.text((x + 8, y + 12), header, fill=(255, 255, 255), font=font_header)
        x += w

    for row_idx, row in enumerate(clipped_rows):
        x = margin
        y = margin + title_h + header_h + (row_idx * row_h)
        row_bg = (255, 255, 255) if row_idx % 2 == 0 else (245, 249, 252)
        for col_idx, value in enumerate(row):
            w = col_widths[col_idx]
            draw.rectangle((x, y, x + w, y + row_h), fill=row_bg, outline=(223, 230, 236))
            _draw_cell_text(draw, value or "", x, y, w, row_h, font_cell, (17, 24, 39))
            x += w

    out = BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()

