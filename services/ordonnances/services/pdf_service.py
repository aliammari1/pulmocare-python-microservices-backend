from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
import os

def generate_ordonnance_pdf(ordonnance):
    output_dir = os.path.join(os.getcwd(), 'generated_pdfs')
    os.makedirs(output_dir, exist_ok=True)
    
    filename = f"ordonnance_{ordonnance.patient_id}_{ordonnance.date}.pdf"
    filepath = os.path.join(output_dir, filename)
    
    doc = SimpleDocTemplate(filepath, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    
    # Add header
    header_style = ParagraphStyle(
        'CustomHeader',
        parent=styles['Heading1'],
        fontSize=16,
        spaceAfter=30
    )
    story.append(Paragraph("Ordonnance Médicale", header_style))
    story.append(Spacer(1, 12))
    
    # Add content
    for medicament in ordonnance.medicaments:
        story.append(Paragraph(f"- {medicament['nom']}: {medicament['posologie']}", styles['Normal']))
        story.append(Spacer(1, 6))
    
    doc.build(story)
    return filepath
