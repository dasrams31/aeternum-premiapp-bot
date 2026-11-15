"""Struk pembelian (receipt) Aeternum: teks + gambar struk.

Format meniru struk toko referensi (perintah user 16 Nov 2026):
teks "STRUK PEMBELIAN" dengan detail pembelian + ID invoice Aeternum,
plus gambar struk berisi info yang sama. Dipakai
broadcast_transaction_success ke channel Aeternum, grup Peka, dan DM admin.

Gambar: struk kertas ala Peka — kertas putih bergerigi (sobekan) di atas
krem #F5F1E8, pelat nama kuning Peka #FFD60A "AETERNUM WEBSPACE &
PremiApp Bot", isi monospace (DejaVu Sans Mono), garis putus-putus,
barcode invoice, ucapan terima kasih. Bila render gagal, broadcast
tetap jalan dengan teks saja — alur pembayaran tidak pernah rusak
gara-gara struk.
"""

import io
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

WIB = timezone(timedelta(hours=7))

FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
FONT_MONO_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"


def format_method(payment_method: Optional[str]) -> str:
    """QRIS / BALANCE dari DB -> label tampil di struk."""
    method = (payment_method or "").strip().upper()
    if method == "BALANCE":
        return "Saldo"
    if method:
        return method
    return "QRIS"


def format_receipt_time(dt: Optional[datetime]) -> str:
    """Waktu struk gaya referensi: 15/11/2026, 16.57 (WIB)."""
    if dt is None:
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(WIB).strftime("%d/%m/%Y, %H.%M")


def buyer_display(buyer_username: Optional[str], buyer_first_name: Optional[str]) -> str:
    if buyer_username:
        return f"@{buyer_username}"
    return buyer_first_name or "-"


def _rupiah(price) -> str:
    return f"Rp {float(price):,.0f}".replace(",", ".")


def build_receipt_text(
    product_name: str,
    amount: float,
    invoice_id: Optional[str] = None,
    buyer_username: Optional[str] = None,
    buyer_first_name: Optional[str] = None,
    payment_method: Optional[str] = None,
    paid_at: Optional[datetime] = None,
) -> str:
    """Teks struk, meniru blok teks struk referensi (tanpa HTML)."""
    return (
        "🧾 STRUK PEMBELIAN\n"
        f"Produk: {product_name}\n"
        "Jumlah: 1x\n"
        f"Order: {invoice_id or 'Manual'}\n"
        f"Total: {_rupiah(amount)}\n"
        f"Pembeli: {buyer_display(buyer_username, buyer_first_name)}\n"
        f"Metode: {format_method(payment_method)}\n"
        f"Waktu: {format_receipt_time(paid_at)}\n"
        "\n"
        "✅ Pembayaran diterima"
    )


def _load_font(path: str, size: int):
    from PIL import ImageFont

    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _wrap_text(draw, text: str, font, max_width: int):
    """Bungkus teks ke beberapa baris agar muat dalam max_width."""
    words = str(text).split()
    lines, current = [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or ["-"]


def _text_h(draw, text: str, font) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[3] - bbox[1]


def _dashed_line(draw, x0: int, x1: int, y: int, color, width: int = 3):
    x = x0
    while x < x1:
        seg = min(16, x1 - x)
        draw.line([(x, y), (x + seg, y)], fill=color, width=width)
        x += 16 + 12


def _zigzag_points(x0: int, x1: int, y_top: int, y_bottom: int, tooth: int = 30, depth: int = 18):
    """Titik poligon kertas: gerigi di tepi atas dan bawah."""
    pts = []
    x = x0
    up = True
    while x < x1:
        pts.append((x, y_top - depth if up else y_top))
        x += tooth
        up = not up
    pts.append((x1, y_top))
    pts.append((x1, y_bottom))
    x = x1
    down = True
    while x > x0:
        pts.append((x, y_bottom + depth if down else y_bottom))
        x -= tooth
        down = not down
    pts.append((x0, y_bottom))
    return pts


def _barcode(draw, x0: int, y0: int, width: int, height: int, code: str):
    """Barcode dekoratif deterministik dari string invoice."""
    x = x0
    i = 0
    while x < x0 + width - 8:
        ch = code[i % len(code)]
        bar_w = 2 + (ord(ch) % 4) * 2
        gap_w = 2 + (ord(ch) % 3) * 2
        draw.rectangle([x, y0, x + bar_w, y0 + height], fill=(13, 17, 23))
        x += bar_w + gap_w
        i += 1


def render_receipt_image(
    product_name: str,
    amount: float,
    invoice_id: Optional[str] = None,
    buyer_username: Optional[str] = None,
    buyer_first_name: Optional[str] = None,
    payment_method: Optional[str] = None,
    paid_at: Optional[datetime] = None,
) -> bytes:
    """Gambar struk kertas ala Peka (JPEG).

    Kertas putih bergerigi di atas krem, pelat nama kuning Peka
    "AETERNUM WEBSPACE & PremiApp Bot", isi monospace dengan garis
    putus-putus, TOTAL tebal, barcode invoice, ucapan terima kasih.
    """
    from PIL import Image, ImageDraw

    width = 1080
    paper_x0, paper_x1 = 90, 990
    pad = 64

    cream = (245, 241, 232)  # Peka cream #F5F1E8
    paper = (255, 255, 255)
    yellow = (255, 214, 10)  # Peka yellow #FFD60A
    ink = (13, 17, 23)
    dim = (90, 86, 72)  # cream dim #5A5648
    dash = (180, 172, 150)
    green = (21, 128, 61)

    f_name = _load_font(FONT_BOLD, 52)
    f_name2 = _load_font(FONT_BOLD, 36)
    f_title = _load_font(FONT_MONO_BOLD, 32)
    f_date = _load_font(FONT_MONO, 28)
    f_ok = _load_font(FONT_MONO_BOLD, 34)
    f_label = _load_font(FONT_MONO, 30)
    f_value = _load_font(FONT_MONO_BOLD, 30)
    f_total_label = _load_font(FONT_MONO_BOLD, 40)
    f_total_value = _load_font(FONT_MONO_BOLD, 46)
    f_foot = _load_font(FONT_MONO, 26)
    f_foot_bold = _load_font(FONT_MONO_BOLD, 28)
    f_barcode_num = _load_font(FONT_MONO, 28)

    date_str = format_receipt_time(paid_at)
    invoice = invoice_id or "Manual"
    buyer = buyer_display(buyer_username, buyer_first_name)
    method = format_method(payment_method)
    qty = f"1x @ {_rupiah(amount)}"
    total = _rupiah(amount)

    probe = Image.new("RGB", (10, 10))
    pdraw = ImageDraw.Draw(probe)
    value_w = 620
    product_lines = _wrap_text(pdraw, product_name, f_value, value_w)
    rows = [
        ("Order ID", [invoice]),
        ("Produk", product_lines),
        ("Jumlah", [qty]),
        ("Pembeli", [buyer]),
        ("Metode", [method]),
        ("Waktu", [date_str]),
    ]
    row_line_h = 44
    row_gap = 24
    rows_h = sum(len(lines) * row_line_h for _, lines in rows)
    rows_h += row_gap * (len(rows) - 1)

    # Tinggi tiap seksi (diukur dari font, supaya pas).
    plate_h = 30 + _text_h(pdraw, "AETERNUM WEBSPACE", f_name) + 10
    plate_h += _text_h(pdraw, "& PremiApp Bot", f_name2) + 30
    title_h = _text_h(pdraw, "STRUK PEMBELIAN", f_title)
    date_h = _text_h(pdraw, date_str, f_date)
    ok_h = _text_h(pdraw, "PEMBAYARAN BERHASIL", f_ok)
    total_h = max(
        _text_h(pdraw, "TOTAL", f_total_label),
        _text_h(pdraw, total, f_total_value),
    )
    barcode_h = 84
    barcode_num_h = _text_h(pdraw, invoice, f_barcode_num)
    foot_h = _text_h(pdraw, "Terima kasih telah berbelanja di", f_foot)
    foot_h += 8 + _text_h(pdraw, "Aeternum Webspace & PremiApp Bot", f_foot_bold)

    top_margin = 30
    tooth_depth = 18
    top_pad = 46
    bottom_pad = 46
    content_h = (
        top_pad
        + plate_h + 34
        + title_h + 6 + date_h + 26
        + 4 + 26
        + ok_h + 26
        + 4 + 26
        + rows_h + 26
        + 4 + 22
        + total_h + 26
        + 4 + 30
        + barcode_h + 10 + barcode_num_h + 30
        + foot_h
        + bottom_pad
    )
    height = top_margin + tooth_depth + content_h + tooth_depth + top_margin
    y_top = top_margin + tooth_depth
    y_bottom = y_top + content_h

    img = Image.new("RGB", (width, height), cream)
    draw = ImageDraw.Draw(img)

    # Kertas putih bergerigi.
    draw.polygon(
        _zigzag_points(paper_x0, paper_x1, y_top, y_bottom, depth=tooth_depth),
        fill=paper,
    )

    y = y_top + top_pad
    # Pelat nama kuning.
    plate_x0, plate_x1 = paper_x0 + 56, paper_x1 - 56
    draw.rounded_rectangle(
        [plate_x0, y, plate_x1, y + plate_h], radius=26, fill=yellow
    )
    name1 = "AETERNUM WEBSPACE"
    w1 = draw.textlength(name1, font=f_name)
    draw.text(
        ((width - w1) / 2, y + 30), name1, font=f_name, fill=ink
    )
    name2 = "& PremiApp Bot"
    w2 = draw.textlength(name2, font=f_name2)
    draw.text(
        ((width - w2) / 2, y + 30 + _text_h(draw, name1, f_name) + 10),
        name2,
        font=f_name2,
        fill=ink,
    )
    y += plate_h + 34

    # Judul + tanggal, rata tengah.
    title = "STRUK PEMBELIAN"
    tw = draw.textlength(title, font=f_title)
    draw.text(((width - tw) / 2, y), title, font=f_title, fill=ink)
    y += title_h + 6
    dw = draw.textlength(date_str, font=f_date)
    draw.text(((width - dw) / 2, y), date_str, font=f_date, fill=dim)
    y += date_h + 26

    _dashed_line(draw, paper_x0 + pad, paper_x1 - pad, y + 2, dash)
    y += 4 + 26

    ok_text = "PEMBAYARAN BERHASIL"
    ow = draw.textlength(ok_text, font=f_ok)
    draw.text(((width - ow) / 2, y), ok_text, font=f_ok, fill=green)
    y += ok_h + 26

    _dashed_line(draw, paper_x0 + pad, paper_x1 - pad, y + 2, dash)
    y += 4 + 26

    # Baris-baris struk: label kiri, nilai kanan.
    value_x = paper_x1 - pad
    for idx, (label, lines) in enumerate(rows):
        draw.text((paper_x0 + pad, y), label, font=f_label, fill=dim)
        for li, line in enumerate(lines):
            lw = draw.textlength(line, font=f_value)
            draw.text(
                (value_x - lw, y + li * row_line_h), line, font=f_value, fill=ink
            )
        y += len(lines) * row_line_h
        if idx < len(rows) - 1:
            y += row_gap

    y += 26
    _dashed_line(draw, paper_x0 + pad, paper_x1 - pad, y + 2, dash)
    y += 4 + 22

    draw.text((paper_x0 + pad, y), "TOTAL", font=f_total_label, fill=ink)
    total_w = draw.textlength(total, font=f_total_value)
    draw.text((value_x - total_w, y), total, font=f_total_value, fill=ink)
    y += total_h + 26

    _dashed_line(draw, paper_x0 + pad, paper_x1 - pad, y + 2, dash)
    y += 4 + 30

    # Barcode + nomor invoice.
    barcode_w = 560
    _barcode(draw, (width - barcode_w) // 2, y, barcode_w, barcode_h, invoice)
    y += barcode_h + 10
    bw = draw.textlength(invoice, font=f_barcode_num)
    draw.text(((width - bw) / 2, y), invoice, font=f_barcode_num, fill=dim)
    y += barcode_num_h + 30

    # Footer.
    thanks = "Terima kasih telah berbelanja di"
    fw = draw.textlength(thanks, font=f_foot)
    draw.text(((width - fw) / 2, y), thanks, font=f_foot, fill=dim)
    y += _text_h(draw, thanks, f_foot) + 8
    store = "Aeternum Webspace & PremiApp Bot"
    sw = draw.textlength(store, font=f_foot_bold)
    draw.text(((width - sw) / 2, y), store, font=f_foot_bold, fill=ink)

    out = io.BytesIO()
    img.save(out, format="JPEG", quality=92)
    return out.getvalue()
