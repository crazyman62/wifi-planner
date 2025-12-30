from reportlab.lib.pagesizes import letter, landscape
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet
from datetime import datetime
import os

class PDFReport:
    def __init__(self, filepath):
        self.filepath = filepath
        self.styles = getSampleStyleSheet()
        self.elements = []

    def generate_report(self, project_name, floor_name, map_image_path, access_points, min_dbm, max_dbm):
        doc = SimpleDocTemplate(self.filepath, pagesize=landscape(letter),
                                rightMargin=30, leftMargin=30,
                                topMargin=30, bottomMargin=30)

        # Title Page
        self._create_title_page(project_name, floor_name)
        self.elements.append(PageBreak())

        # Map Page
        self._create_map_page(map_image_path, min_dbm, max_dbm)
        self.elements.append(PageBreak())

        # BOM Page
        self._create_bom_page(access_points)

        doc.build(self.elements)

    def _create_title_page(self, project_name, floor_name):
        title_style = self.styles['Title']
        title_style.fontSize = 24
        title_style.leading = 30

        normal_style = self.styles['Normal']
        normal_style.fontSize = 14
        normal_style.alignment = 1 # Center

        self.elements.append(Spacer(1, 100))
        self.elements.append(Paragraph("WiFi Predictive Site Survey", title_style))
        self.elements.append(Spacer(1, 20))
        self.elements.append(Paragraph(f"Project: {project_name}", normal_style))
        self.elements.append(Paragraph(f"Floor: {floor_name}", normal_style))
        self.elements.append(Spacer(1, 10))
        self.elements.append(Paragraph(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}", normal_style))

    def _create_map_page(self, map_image_path, min_dbm, max_dbm):
        self.elements.append(Paragraph("Signal Heatmap", self.styles['Heading2']))
        self.elements.append(Spacer(1, 10))

        # Add Map Image
        # Resize to fit width if needed, but SimpleDocTemplate handles some wrapping.
        # Let's check aspect ratio.
        # Max width for landscape letter is ~10 inches = 720 pts.
        if os.path.exists(map_image_path):
            img = Image(map_image_path)
            # Simple scaling logic
            max_width = 700
            max_height = 450

            # Calculate aspect ratio
            img_width = img.drawWidth
            img_height = img.drawHeight

            ratio = min(max_width/img_width, max_height/img_height)

            img.drawWidth = img_width * ratio
            img.drawHeight = img_height * ratio

            self.elements.append(img)

        self.elements.append(Spacer(1, 20))

        # Legend
        self.elements.append(Paragraph(f"Signal Strength Legend: {min_dbm} dBm (Red) to {max_dbm} dBm (Blue)", self.styles['Normal']))
        # We could draw a gradient bar here, but simple text is fine for Phase 1.

    def _create_bom_page(self, access_points):
        self.elements.append(Paragraph("Access Point List", self.styles['Heading2']))
        self.elements.append(Spacer(1, 20))

        # List all APs with names
        data = [['Name', 'Model']]
        # Sort by name
        sorted_aps = sorted(access_points, key=lambda x: x.get('name', ''))

        for ap in sorted_aps:
            name = ap.get('name', 'N/A')
            model = ap.get('model', 'Unknown')
            data.append([name, model])

        table = Table(data, colWidths=[150, 250])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))

        self.elements.append(table)
