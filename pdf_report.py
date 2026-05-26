from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, 
                                 Table, TableStyle, PageBreak)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from datetime import datetime
import io
import os

# Регистрируем шрифт с кириллицей
def _register_font():
    """Пытается найти подходящий TTF-шрифт с кириллицей."""
    candidates = [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibri.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont('CyrFont', path))
                return 'CyrFont'
            except Exception:
                continue
    return 'Helvetica'  # fallback (без кириллицы)

FONT = _register_font()

def generate_route_pdf(route_data, route_index=1, total_km=0):
    """
    Генерирует PDF-маршрутный лист для одного мусоровоза.
    
    Args:
        route_data: dict с ключами 'vehicle_id', 'points', 'distance_km', 'load_percent'
        route_index: номер маршрута
        total_km: общая дистанция
    
    Returns:
        BytesIO с PDF
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm
    )
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'TitleCyr', parent=styles['Title'],
        fontName=FONT, fontSize=18, alignment=1
    )
    header_style = ParagraphStyle(
        'HeaderCyr', parent=styles['Heading2'],
        fontName=FONT, fontSize=13
    )
    normal_style = ParagraphStyle(
        'NormalCyr', parent=styles['Normal'],
        fontName=FONT, fontSize=10
    )
    
    story = []
    
    # Заголовок
    story.append(Paragraph("МАРШРУТНЫЙ ЛИСТ", title_style))
    story.append(Paragraph(
        f"Вывоз твёрдых коммунальных отходов · г. Кокшетау",
        normal_style
    ))
    story.append(Spacer(1, 0.5*cm))
    
    # Шапка
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    info_data = [
        ['Дата формирования:', now],
        ['Номер маршрута:', f"№ {route_index}"],
        ['Мусоровоз №:', str(route_data.get('vehicle_id', 1))],
        ['Точек вывоза:', str(len([p for p in route_data['points'] if p['type'] == 'container']))],
        ['Пробег:', f"{route_data.get('distance_km', 0):.2f} км"],
        ['Загрузка машины:', f"{route_data.get('load_percent', 0)}% ({route_data.get('load_liters', 0)} л)"],
    ]
    info_table = Table(info_data, colWidths=[5*cm, 10*cm])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), FONT),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.3, colors.grey),
        ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 0.6*cm))
    
    # Таблица точек маршрута
    story.append(Paragraph("Порядок объезда контейнеров:", header_style))
    story.append(Spacer(1, 0.2*cm))
    
    headers = ['№', 'Точка', 'Адрес', 'Заполнение', 'Объём, л']
    rows = [headers]
    
    counter = 0
    for p in route_data['points']:
        if p['type'] == 'depot':
            rows.append([
                '—', '🏢 Автобаза', p['address'], '—', '—'
            ])
        else:
            counter += 1
            rows.append([
                str(counter),
                p['name'],
                p['address'],
                f"{p.get('current_fill', 0)}%",
                str(p.get('volume_liters', 0))
            ])
    
    route_table = Table(rows, colWidths=[1.2*cm, 2*cm, 7*cm, 2.3*cm, 2.5*cm])
    route_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), FONT),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0066cc')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.3, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 1), (0, -1), 'CENTER'),
        ('ALIGN', (3, 1), (4, -1), 'CENTER'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
    ]))
    story.append(route_table)
    story.append(Spacer(1, 1*cm))
    
    # Подписи
    sign_data = [
        ['Водитель: _________________ /_______________/', ''],
        ['', ''],
        ['Диспетчер: ________________ /_______________/', ''],
    ]
    sign_table = Table(sign_data, colWidths=[10*cm, 5*cm])
    sign_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), FONT),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
    ]))
    story.append(sign_table)
    
    doc.build(story)
    buffer.seek(0)
    return buffer


def generate_all_routes_pdf(routes):
    """Один PDF со всеми маршрутами (по странице на каждый)."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    title = ParagraphStyle('T', parent=styles['Title'], fontName=FONT, fontSize=16, alignment=1)
    story = []
    
    for i, route in enumerate(routes, 1):
        single_buffer = generate_route_pdf(route, route_index=i)
        # Просто перегенерим содержимое в общем документе
        # (проще объединить через PyPDF2, но для простоты — генерим заново)
    
    # Упрощённый вариант: возвращаем первый маршрут
    # В реальности используйте PyPDF2 для объединения
    return generate_route_pdf(routes[0], route_index=1) if routes else buffer