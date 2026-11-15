"""Struk pembelian (receipt) Aeternum: teks + gambar kartu struk.

Format meniru struk toko referensi (perintah user 16 Nov 2026):
teks "STRUK PEMBELIAN" dengan detail pembelian + ID invoice Aeternum,
plus gambar kartu struk berisi info yang sama. Dipakai
broadcast_transaction_success ke channel Aeternum, grup Peka, dan DM admin.

Gambar dibuat dengan PIL (font DejaVu, tersedia di server). Bila render
gagal, broadcast tetap jalan dengan teks saja — alur pembayaran tidak
pernah rusak gara-gara struk.
"""

import io
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

WIB = timezone(timedelta(hours=7))

FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


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


def render_receipt_image(
    product_name: str,
    amount: float,
    invoice_id: Optional[str] = None,
    buyer_username: Optional[str] = None,
    buyer_first_name: Optional[str] = None,
    payment_method: Optional[str] = None,
    paid_at: Optional[datetime] = None,
) -> bytes:
    """Gambar kartu struk (JPEG) meniru kartu struk referensi.

    Tema kuning + krem Peka (perintah user 16 Nov 2026): header kuning
    Peka #FFD60A "AETERNUM / STRUK PEMBELIAN" + tanggal, kartu putih di
    atas krem #F5F1E8, pill hijau "PEMBAYARAN BERHASIL", baris Order ID /
    Produk / Jumlah / Pembeli / Metode / Waktu, garis tebal, TOTAL, lalu
    ucapan terima kasih.
    """
    from PIL import Image, ImageDraw

    width = 1080
    margin = 28
    card_x0, card_x1 = margin, width - margin
    pad = 56

    yellow = (255, 214, 10)  # Peka yellow #FFD60A
    bg = (245, 241, 232)  # Peka cream #F5F1E8
    white = (255, 255, 255)
    ink = (13, 17, 23)
    grey = (90, 86, 72)  # cream dim #5A5648
    light_grey = (90, 86, 72)
    hairline = (232, 226, 210)
    green_bg = (220, 252, 231)
    green_text = (21, 128, 61)

    f_store = _load_font(FONT_BOLD, 58)
    f_sub = _load_font(FONT_REGULAR, 28)
    f_date = _load_font(FONT_REGULAR, 28)
    f_pill = _load_font(FONT_BOLD, 30)
    f_label = _load_font(FONT_REGULAR, 32)
    f_value = _load_font(FONT_BOLD, 34)
    f_total_label = _load_font(FONT_BOLD, 40)
    f_total_value = _load_font(FONT_BOLD, 58)
    f_foot = _load_font(FONT_REGULAR, 28)
    f_foot_small = _load_font(FONT_REGULAR, 26)

    date_str = format_receipt_time(paid_at)
    invoice = invoice_id or "Manual"
    buyer = buyer_display(buyer_username, buyer_first_name)
    method = format_method(payment_method)
    qty = f"1x @ {_rupiah(amount)}"
    total = _rupiah(amount)

    # Ukur dulu (produk bisa membungkus 2 baris) supaya tinggi pas.
    probe = Image.new("RGB", (10, 10))
    probe_draw = ImageDraw.Draw(probe)
    value_w = 640
    product_lines = _wrap_text(probe_draw, product_name, f_value, value_w)
    rows = [
        ("Order ID", [invoice]),
        ("Produk", product_lines),
        ("Jumlah", [qty]),
        ("Pembeli", [buyer]),
        ("Metode", [method]),
        ("Waktu", [date_str]),
    ]
    line_h = 46
    row_gap = 26
    rows_h = 0
    for _label, lines in rows:
        rows_h += len(lines) * line_h + row_gap
    rows_h -= row_gap  # gap terakhir tidak perlu

    header_h = 190
    body_top = header_h + 48
    pill_h = 64
    total_h = 96
    foot_h = 110
    height = (
        body_top + pill_h + 40 + rows_h + 36 + 3 + total_h + 40 + foot_h + 48
    )

    img = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(img)

    # Kartu putih sudut membulat.
    draw.rounded_rectangle(
        [card_x0, 0, card_x1, height - margin], radius=44, fill=white
    )
    # Header kuning (menutupi sudut atas kartu).
    draw.rounded_rectangle(
        [card_x0, 0, card_x1, header_h], radius=44, fill=yellow
    )
    draw.rectangle([card_x0, header_h - 44, card_x1, header_h], fill=yellow)

    draw.text((card_x0 + pad, 40), "AETERNUM", font=f_store, fill=ink)
    draw.text(
        (card_x0 + pad, 116), "STRUK PEMBELIAN", font=f_sub, fill=(74, 66, 0)
    )
    date_w = draw.textlength(date_str, font=f_date)
    draw.text(
        (card_x1 - pad - date_w, 52), date_str, font=f_date, fill=ink
    )

    y = body_top
    # Pill hijau.
    pill_text = "PEMBAYARAN BERHASIL"
    pill_w = draw.textlength(pill_text, font=f_pill) + 72
    draw.rounded_rectangle(
        [card_x0 + pad, y, card_x0 + pad + pill_w, y + pill_h],
        radius=32,
        fill=green_bg,
    )
    draw.text(
        (card_x0 + pad + 36, y + 16), pill_text, font=f_pill, fill=green_text
    )
    y += pill_h + 40

    # Baris-baris struk.
    value_x = card_x1 - pad
    for idx, (label, lines) in enumerate(rows):
        draw.text((card_x0 + pad, y), label, font=f_label, fill=grey)
        for li, line in enumerate(lines):
            lw = draw.textlength(line, font=f_value)
            draw.text(
                (value_x - lw, y + li * line_h), line, font=f_value, fill=ink
            )
        y += len(lines) * line_h + row_gap
        if idx < len(rows) - 1:
            draw.line(
                [(card_x0 + pad, y - 13), (card_x1 - pad, y - 13)],
                fill=hairline,
                width=2,
            )

    # Garis tebal + TOTAL.
    y += 36 - row_gap
    draw.line(
        [(card_x0 + pad, y), (card_x1 - pad, y)], fill=ink, width=3
    )
    y += 24
    draw.text((card_x0 + pad, y + 8), "TOTAL", font=f_total_label, fill=ink)
    total_w = draw.textlength(total, font=f_total_value)
    draw.text((value_x - total_w, y), total, font=f_total_value, fill=ink)
    y += total_h + 40

    # Footer.
    thanks = "Terima kasih telah berbelanja di Aeternum"
    tw = draw.textlength(thanks, font=f_foot)
    draw.text(((width - tw) / 2, y), thanks, font=f_foot, fill=light_grey)
    iw = draw.textlength(invoice, font=f_foot_small)
    draw.text(
        ((width - iw) / 2, y + 44), invoice, font=f_foot_small, fill=(163, 158, 141)
    )

    out = io.BytesIO()
    img.save(out, format="JPEG", quality=92)
    return out.getvalue()
