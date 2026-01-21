import os
import tempfile
from datetime import datetime

import pdfkit

from services.logger_service import logger_service


class ReportGenerator:
    """Service for generating PDF reports"""

    def __init__(self):
        self.temp_dir = tempfile.gettempdir()

    def generate_pdf(self, report):
        """Generate PDF from report data"""
        try:
            report_id = report["_id"]

            # Generate HTML content
            html_content = self._generate_html(report)

            # Create output path
            output_path = os.path.join(self.temp_dir, f"report_{report_id}.pdf")

            # Generate PDF using pdfkit (wrapper for wkhtmltopdf)
            pdfkit.from_string(html_content, output_path)

            logger_service.info(f"Generated PDF report for {report_id}")
            return output_path
        except Exception as e:
            logger_service.error(f"Error generating PDF: {e!s}")
            raise

    def _generate_html(self, report):
        """Generate HTML template for the report"""
        title = report.get("title", "Untitled Report")
        content = report.get("content", "")
        patient_name = report.get("patient_name", "Unknown")
        doctor_name = report.get("doctor_name", "Unknown")
        created_at = report.get("created_at", datetime.utcnow().isoformat())

        # Format date if it's not already a string
        if not isinstance(created_at, str):
            created_at = created_at.isoformat()

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>{title}</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    margin: 40px;
                    line-height: 1.6;
                }}
                .header {{
                    text-align: center;
                    margin-bottom: 30px;
                }}
                .report-title {{
                    font-size: 24px;
                    font-weight: bold;
                    margin-bottom: 10px;
                }}
                .report-meta {{
                    display: flex;
                    justify-content: space-between;
                    margin-bottom: 20px;
                    border-top: 1px solid #ccc;
                    border-bottom: 1px solid #ccc;
                    padding: 10px 0;
                }}
                .content {{
                    margin-bottom: 30px;
                }}
                .footer {{
                    margin-top: 50px;
                    font-size: 12px;
                    text-align: center;
                    color: #666;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <div class="report-title">{title}</div>
                <div>Medical Report</div>
            </div>
            
            <div class="report-meta">
                <div><strong>Patient:</strong> {patient_name}</div>
                <div><strong>Doctor:</strong> {doctor_name}</div>
                <div><strong>Date:</strong> {created_at[:10]}</div>
            </div>
            
            <div class="content">
                {content}
            </div>
            
            <div class="footer">
                <p>This is an official medical report. Report ID: {report["_id"]}</p>
                <p>Generated on {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")}</p>
            </div>
        </body>
        </html>
        """

        return html
