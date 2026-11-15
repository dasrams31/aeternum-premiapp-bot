"""Struk pembelian (receipt) Aeternum: teks + gambar struk.

Format meniru struk toko referensi (perintah user 16 Nov 2026):
teks "STRUK PEMBELIAN" dengan detail pembelian + ID invoice Aeternum,
plus gambar struk berisi info yang sama. Dipakai
broadcast_transaction_success ke channel Aeternum, grup Peka, dan DM admin.

Gambar: struk kertas ala Peka — kertas putih bergerigi (sobekan) dengan
bayangan lembut di atas krem #F5F1E8, takik samping ala tiket, pelat nama
kuning Peka #FFD60A "AETERNUM WEBSPACE & PremiApp Bot", isi monospace
(DejaVu Sans Mono), garis putus-putus, stempel "PEMBAYARAN BERHASIL",
TOTAL tebal, barcode invoice + QR asli ke t.me/aeternum_premibot,
ucapan terima kasih, dan pita kuning "BELI LAGI DI t.me/aeternum_premibot".
Bila render gagal, broadcast tetap jalan dengan teks saja — alur
pembayaran tidak pernah rusak gara-gara struk.
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

BOT_LINK = "https://t.me/aeternum_premibot"


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


def _make_qr(size: int):
    """QR asli ke bot (qrcode sudah terpasang di venv). None bila gagal."""
    try:
        import qrcode

        img = qrcode.make(BOT_LINK)
        return img.resize((size, size), 0).convert("RGB")
    except Exception as e:
        logger.warning(f"Gagal buat QR struk: {e}")
        return None


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

    Kertas putih bergerigi + bayangan lembut di atas krem, takik samping,
    pelat nama kuning Peka, isi monospace dengan garis putus-putus,
    stempel "PEMBAYARAN BERHASIL", TOTAL tebal, barcode invoice + QR asli
    ke bot, ucapan terima kasih, pita kuning ajakan beli lagi.
    """
    from PIL import Image, ImageDraw, ImageFilter

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
    shadow_color = (203, 192, 165)

    f_name = _load_font(FONT_BOLD, 52)
    f_name2 = _load_font(FONT_BOLD, 36)
    f_title = _load_font(FONT_MONO_BOLD, 32)
    f_date = _load_font(FONT_MONO, 28)
    f_ok = _load_font(FONT_MONO_BOLD, 32)
    f_label = _load_font(FONT_MONO, 30)
    f_value = _load_font(FONT_MONO_BOLD, 30)
    f_total_label = _load_font(FONT_MONO_BOLD, 40)
    f_total_value = _load_font(FONT_MONO_BOLD, 46)
    f_foot = _load_font(FONT_MONO, 26)
    f_foot_bold = _load_font(FONT_MONO_BOLD, 28)
    f_code_num = _load_font(FONT_MONO, 26)
    f_cta = _load_font(FONT_MONO_BOLD, 26)

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

    plate_h = 26 + _text_h(pdraw, "AETERNUM WEBSPACE", f_name) + 10
    plate_h += _text_h(pdraw, "& PremiApp Bot", f_name2) + 26
    title_h = _text_h(pdraw, "STRUK PEMBELIAN", f_title)
    date_h = _text_h(pdraw, date_str, f_date)
    pill_h = 64
    total_h = max(
        _text_h(pdraw, "TOTAL", f_total_label),
        _text_h(pdraw, total, f_total_value),
    )
    qr_size = 168
    code_h = qr_size
    code_num_h = _text_h(pdraw, invoice, f_code_num)
    foot_h = _text_h(pdraw, "Terima kasih telah berbelanja di", f_foot)
    foot_h += 8 + _text_h(pdraw, "Aeternum Webspace & PremiApp Bot", f_foot_bold)
    cta_h = 64

    top_margin = 30
    tooth_depth = 18
    top_pad = 46
    bottom_pad = 46
    content_h = (
        top_pad
        + plate_h + 34
        + title_h + 6 + date_h + 26
        + 4 + 26
        + pill_h + 26
        + 4 + 26
        + rows_h + 26
        + 4 + 22
        + total_h + 26
        + 4 + 30
        + code_h + 10 + code_num_h + 30
        + foot_h + 30
        + cta_h
        + bottom_pad
    )
    height = top_margin + tooth_depth + content_h + tooth_depth + top_margin
    y_top = top_margin + tooth_depth
    y_bottom = y_top + content_h

    img = Image.new("RGB", (width, height), cream)
    # Bayangan lembut di bawah kertas (offset + blur).
    shadow = Image.new("RGB", (width, height), cream)
    sdraw = ImageDraw.Draw(shadow)
    sdraw.polygon(
        [
            (x + 12, y + 14)
            for (x, y) in _zigzag_points(
                paper_x0, paper_x1, y_top, y_bottom, depth=tooth_depth
            )
        ],
        fill=shadow_color,
    )
    img.paste(shadow.filter(ImageFilter.GaussianBlur(16)), (0, 0))
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
    draw.text(((width - w1) / 2, y + 26), name1, font=f_name, fill=ink)
    name2 = "& PremiApp Bot"
    w2 = draw.textlength(name2, font=f_name2)
    draw.text(
        ((width - w2) / 2, y + 26 + _text_h(draw, name1, f_name) + 10),
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

    # Stempel "PEMBAYARAN BERHASIL": pil garis ganda hijau.
    ok_text = "PEMBAYARAN BERHASIL"
    ok_w = draw.textlength(ok_text, font=f_ok)
    pill_w = int(ok_w + 72)
    pill_x0 = (width - pill_w) // 2
    draw.rounded_rectangle(
        [pill_x0, y, pill_x0 + pill_w, y + pill_h],
        radius=32,
        outline=green,
        width=3,
    )
    draw.rounded_rectangle(
        [pill_x0 + 7, y + 7, pill_x0 + pill_w - 7, y + pill_h - 7],
        radius=26,
        outline=green,
        width=1,
    )
    draw.text(
        ((width - ok_w) / 2, y + (pill_h - _text_h(draw, ok_text, f_ok)) // 2),
        ok_text,
        font=f_ok,
        fill=green,
    )
    y += pill_h + 26

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
    notch_y = y + 2
    y += 4 + 22

    draw.text((paper_x0 + pad, y), "TOTAL", font=f_total_label, fill=ink)
    total_w = draw.textlength(total, font=f_total_value)
    draw.text((value_x - total_w, y), total, font=f_total_value, fill=ink)
    y += total_h + 26

    _dashed_line(draw, paper_x0 + pad, paper_x1 - pad, y + 2, dash)
    y += 4 + 30

    # Barcode kiri + QR asli kanan.
    mid_x = width // 2
    left_cx = (paper_x0 + pad + mid_x - 20) // 2
    right_cx = (mid_x + 20 + paper_x1 - pad) // 2
    barcode_w = 360
    _barcode(
        draw, left_cx - barcode_w // 2, y + (qr_size - 72) // 2,
        barcode_w, 72, invoice,
    )
    qr_img = _make_qr(qr_size)
    if qr_img is not None:
        img.paste(qr_img, (right_cx - qr_size // 2, y))
    y += code_h + 10
    bw = draw.textlength(invoice, font=f_code_num)
    draw.text((left_cx - bw / 2, y), invoice, font=f_code_num, fill=dim)
    scan_txt = "Scan untuk buka bot"
    sw = draw.textlength(scan_txt, font=f_code_num)
    draw.text((right_cx - sw / 2, y), scan_txt, font=f_code_num, fill=dim)
    y += code_num_h + 30

    # Footer.
    thanks = "Terima kasih telah berbelanja di"
    fw = draw.textlength(thanks, font=f_foot)
    draw.text(((width - fw) / 2, y), thanks, font=f_foot, fill=dim)
    y += _text_h(draw, thanks, f_foot) + 8
    store = "Aeternum Webspace & PremiApp Bot"
    sw2 = draw.textlength(store, font=f_foot_bold)
    draw.text(((width - sw2) / 2, y), store, font=f_foot_bold, fill=ink)
    y += _text_h(draw, store, f_foot_bold) + 30

    # Pita kuning ajakan beli lagi.
    cta_text = "BELI LAGI DI t.me/aeternum_premibot"
    draw.rounded_rectangle(
        [plate_x0, y, plate_x1, y + cta_h], radius=18, fill=yellow
    )
    cw = draw.textlength(cta_text, font=f_cta)
    draw.text(
        ((width - cw) / 2, y + (cta_h - _text_h(draw, cta_text, f_cta)) // 2),
        cta_text,
        font=f_cta,
        fill=ink,
    )

    # Takik samping di garis putus sebelum TOTAL (ala tiket).
    notch_r = 26
    for cx in (paper_x0, paper_x1):
        draw.ellipse(
            [cx - notch_r, notch_y - notch_r, cx + notch_r, notch_y + notch_r],
            fill=cream,
        )

    out = io.BytesIO()
    img.save(out, format="JPEG", quality=92)
    return out.getvalue()
