import os
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

class PdfService:
    def __init__(self, db):
        self.db = db
        self.pdf_dir = os.path.join(os.path.dirname(__file__), 'pdfs')
        os.makedirs(self.pdf_dir, exist_ok=True)

    def save_pdf(self, medecin_id, pdf_bytes, ordonnance_id):
        filename = f"ordonnance_{ordonnance_id}_{medecin_id}.pdf"
        filepath = os.path.join(self.pdf_dir, filename)
        
        # Save PDF file
        with open(filepath, 'wb') as f:
            f.write(pdf_bytes)
        
        # Save reference in database
        self.db.pdf_files.insert_one({
            "filename": filename,
            "medecin_id": medecin_id,
            "ordonnance_id": ordonnance_id,
            "path": filepath
        })
        
        return filename

    def get_pdf(self, filename):
        try:
            filepath = os.path.join(self.pdf_dir, filename)
            with open(filepath, 'rb') as f:
                return f.read()
        except:
            return None
