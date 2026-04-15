#!/usr/bin/env python3
"""
PDF Anonymization Tool for Investment Transaction Notes

Generates anonymized HL-style contract note PDFs that:
- Remove personal information (name, address)
- Use small randomized quantities (1-100 range)
- Preserve dates, prices, tickers, currencies
- Maintain parser compatibility
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch, mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.lib import colors
from reportlab.pdfgen import canvas
import random
import string
from datetime import datetime


class HLContractNoteGenerator:
    """Generate Hargreaves Lansdown style contract notes with anonymized data."""

    def __init__(self):
        self.anon_name = "Mr John Doe"
        self.anon_address = ["123 Test Street", "London", "SW1A 1AA"]
        self.hl_address = ["One College Square South", "Anchor Road", "Bristol", "BS1 5HL"]

    def generate_contract_number(self, original_prefix='B'):
        """Generate fake contract number matching HL pattern: B12345678-12345678"""
        # Keep original prefix (B for buy, S for sell)
        num1 = ''.join(random.choices(string.digits, k=9))
        num2 = ''.join(random.choices(string.digits, k=8))
        return f"{original_prefix}{num1}-{num2}"

    def generate_contract_note(self, transaction_data, output_path):
        """
        Generate an anonymized HL contract note PDF.

        Args:
            transaction_data: Dict with keys:
                - transaction_type: 'purchase' or 'disposal'
                - stock_name: Company name
                - ticker: Stock ticker (for reference, not printed on PDF)
                - isin: ISIN code
                - num_shares: Number of shares (anonymized quantity)
                - price: Price per share
                - currency: Currency code (CAD, USD, EUR, GBP, etc.)
                - exchange_rate: FX rate if non-GBP
                - price_in_pence: Price in pence (for GBP stocks)
                - total_amount: Total consideration (GBP)
                - dealing_charge: Dealing fee
                - fx_charge: FX charge (if applicable)
                - total_charges: Total charges
                - transaction_date: datetime object
                - settlement_date: datetime object (optional)
                - account_type: 'ISA', 'Taxable', etc.
                - additional_info: Dict with optional fields like 'venue', 'broker'
            output_path: Path to save the PDF
        """
        # Create PDF with A4 page size
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas as pdf_canvas

        c = pdf_canvas.Canvas(output_path, pagesize=A4)
        width, height = A4

        # Margins
        left_margin = 50
        right_margin = width - 50
        top_margin = height - 40

        y = top_margin

        # Helper function to draw text
        def draw_text(text, x, y_pos, font="Helvetica", size=9, align="left"):
            c.setFont(font, size)
            if align == "right":
                c.drawRightString(x, y_pos, text)
            elif align == "center":
                c.drawCentredString(x, y_pos, text)
            else:
                c.drawString(x, y_pos, text)
            return y_pos - (size + 2)

        # Header - HL company info (small text at top)
        c.setFont("Helvetica", 7)
        c.drawString(left_margin, y, "Hargreaves Lansdown is a trading name of Hargreaves Lansdown Asset Management Limited. Authorised")
        y -= 9
        c.drawString(left_margin, y, "and regulated by the Financial Conduct Authority, No. 115248 Company registered in England and Wales")
        y -= 9
        c.drawString(left_margin, y, "No. 01896481. A member firm of the London Stock Exchange. A Wholly Owned Subsidiary of Hargreaves")
        y -= 9
        c.drawString(left_margin, y, "Lansdown Plc.")
        y -= 20

        # HL Address (left side) and Title (center-right)
        c.setFont("Helvetica", 9)
        hl_y = y
        for line in self.hl_address:
            c.drawString(left_margin, hl_y, line)
            hl_y -= 12

        # Contract Note title (larger, bold)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(left_margin + 200, y, "Contract Note")
        y = hl_y - 20

        # Customer details (left) and contact info (right)
        customer_y = y
        c.setFont("Helvetica", 9)
        c.drawString(left_margin, customer_y, self.anon_name)
        customer_y -= 12
        for line in self.anon_address:
            c.drawString(left_margin, customer_y, line)
            customer_y -= 12

        # Contact numbers (right side)
        contact_y = y
        c.drawString(left_margin + 300, contact_y, "Share Dealing:")
        contact_y -= 12
        c.drawString(left_margin + 300, contact_y, "(0117) 980 9800")
        contact_y -= 12
        c.drawString(left_margin + 300, contact_y, "Fund Dealing:")
        contact_y -= 12
        c.drawString(left_margin + 300, contact_y, "(0117) 980 9807")
        contact_y -= 12
        c.drawString(left_margin + 300, contact_y, "Helpdesk:")
        contact_y -= 12
        c.drawString(left_margin + 300, contact_y, "(0117) 900 9000")
        contact_y -= 12
        c.drawString(left_margin + 300, contact_y, "www.hl.co.uk")

        y = min(customer_y, contact_y) - 20

        # Date, Time, Contract Number
        trans_date = transaction_data['transaction_date']
        date_str = trans_date.strftime('%d/%m/%Y')
        time_str = trans_date.strftime('%H:%M')

        # Generate fake contract number
        contract_prefix = 'S' if transaction_data['transaction_type'] == 'disposal' else 'B'
        contract_number = self.generate_contract_number(contract_prefix)

        c.setFont("Helvetica", 9)
        c.drawString(left_margin, y, "A/C Designation :")
        y -= 12
        c.drawString(left_margin, y, f"Date {date_str}")
        c.drawString(left_margin + 100, y, f"Time {time_str}")
        c.drawString(left_margin + 200, y, f"Contract Note No. {contract_number}")
        y -= 10
        c.setFont("Helvetica", 7)
        c.drawString(left_margin + 200, y, "(To be quoted in all correspondence)")
        y -= 20

        # Transaction type (BOUGHT/SOLD) - large and bold
        trans_type_display = "**BOUGHT**" if transaction_data['transaction_type'] == 'purchase' else "**SOLD**"
        c.setFont("Helvetica-Bold", 14)
        c.drawString(left_margin + 180, y, trans_type_display)
        y -= 25

        c.setFont("Helvetica", 9)
        instruction_text = "We have today on your instructions"
        c.drawString(left_margin, y, instruction_text)
        c.drawString(left_margin + 200, y, "the security detailed below.")
        y -= 20

        # IMPORTANT box
        c.setFont("Helvetica-Bold", 11)
        c.setFillColorRGB(0.8, 0, 0)  # Red
        c.drawString(left_margin, y, "IMPORTANT")
        c.setFillColorRGB(0, 0, 0)  # Back to black
        y -= 12
        c.setFont("Helvetica", 8)
        c.drawString(left_margin + 100, y, "Please check all details are correct.")
        y -= 10
        c.drawString(left_margin + 100, y, "You should advise us of any discrepancy immediately")
        y -= 20

        # Table headers
        c.setFont("Helvetica-Bold", 9)
        c.drawString(left_margin, y, "Quantity")
        c.drawString(left_margin + 100, y, "Security")
        c.drawString(left_margin + 350, y, "Price")
        c.drawString(left_margin + 450, y, "Consideration")
        y -= 15

        # Security details
        c.setFont("Helvetica", 9)

        # ISIN and optional STOCK CODE (match original PDF format)
        isin_line = transaction_data['isin']
        if transaction_data.get('stock_code'):
            # Include STOCK CODE if original had it
            isin_line += f" STOCK CODE: {transaction_data['stock_code']}"
        c.drawString(left_margin + 100, y, isin_line)
        y -= 12

        # Stock name
        c.drawString(left_margin + 100, y, transaction_data['stock_name'])
        y -= 12

        # Check if this is a UK fund/stock (GBP currency, no exchange rate)
        currency = transaction_data['currency']
        exchange_rate = transaction_data.get('exchange_rate')
        is_uk_fund = (currency == 'GBP' and (exchange_rate is None or exchange_rate == 1.0))

        if is_uk_fund:
            # UK fund format: quantity price(pence) consideration all on one line
            quantity = transaction_data['num_shares']
            price_pence = transaction_data['price'] * 100  # Convert to pence
            consideration = transaction_data['total_amount']

            # Format: "30,001.20 166.660000 50,000.00"
            quantity_str = f"{quantity:,.2f}"
            price_str = f"{price_pence:.6f}"
            consideration_str = f"{consideration:,.2f}"

            uk_line = f"{quantity_str} {price_str} {consideration_str}"
            c.drawString(left_margin + 100, y, uk_line)
            y -= 12

            # Fund class info if available
            if 'stock_type' in transaction_data:
                c.drawString(left_margin + 100, y, transaction_data['stock_type'])
                y -= 12

        else:
            # Foreign currency format (existing logic)
            # Quantity on separate line
            quantity_str = f"{transaction_data['num_shares']:.2f}" if transaction_data['num_shares'] % 1 else f"{int(transaction_data['num_shares'])}.00"
            c.drawString(left_margin, y, quantity_str)

            # Additional stock info (e.g., "Common Stock")
            if 'stock_type' in transaction_data:
                c.drawString(left_margin + 100, y, transaction_data['stock_type'])
            y -= 15

            # Price details
            if currency not in ['GBP', 'GBp']:
                # Foreign currency - show original price, exchange rate, pence price
                c.drawString(left_margin + 100, y, f"Price ({currency})")
                c.drawString(left_margin + 350, y, f"{transaction_data['price']:.2f}")
                y -= 12

                c.drawString(left_margin + 100, y, "Exchange rate")
                c.drawString(left_margin + 350, y, f"{transaction_data['exchange_rate']:.4f}")
                y -= 12

                # Calculate price in pence
                price_pence = transaction_data['price'] * transaction_data['exchange_rate'] * 100
                c.drawString(left_margin + 100, y, "Price (pence)")
                c.drawString(left_margin + 350, y, f"{price_pence:.4f}")
                y -= 12
            elif currency == 'GBp':
                # UK stock in pence
                c.drawString(left_margin + 100, y, "Price (pence)")
                c.drawString(left_margin + 350, y, f"{transaction_data['price']:.2f}")
                y -= 12

            # Consideration (total value)
            c.drawString(left_margin + 450, y + 12, f"GBP {transaction_data['total_amount']:.2f}")

        # Additional execution info
        if 'additional_info' in transaction_data:
            info = transaction_data['additional_info']
            if 'order_type' in info:
                c.drawString(left_margin + 100, y, info['order_type'])
                y -= 12
            if 'venue' in info:
                c.drawString(left_margin + 100, y, f"Venue of Execution: {info['venue']}")
                y -= 12
            if 'broker' in info:
                c.drawString(left_margin + 100, y, f"Broker: {info['broker']}")
                y -= 12

        y -= 10

        # Charges section (skip if None - UK funds don't have separate charges)
        dealing_charge = transaction_data.get('dealing_charge')
        if dealing_charge is not None:
            c.drawString(left_margin + 100, y, "Dealing charge")
            c.drawString(left_margin + 450, y, f"{dealing_charge:.2f}")
            y -= 12

        fx_charge = transaction_data.get('fx_charge')
        if fx_charge is not None and fx_charge > 0:
            c.drawString(left_margin + 100, y, "FX Charge")
            c.drawString(left_margin + 450, y, f"{fx_charge:.2f}")
            y -= 12

        total_charges = transaction_data.get('total_charges')
        if total_charges is not None:
            c.setFont("Helvetica-Bold", 9)
            c.drawString(left_margin + 100, y, "Total Charges")
            c.drawString(left_margin + 450, y, f"{total_charges:.2f}")
            y -= 20

        # Account and settlement
        c.setFont("Helvetica", 9)
        c.drawString(left_margin, y, "These shares/units have been dealt using the following account:")
        y -= 15

        account_type = transaction_data.get('account_type', 'HL Stocks & Shares ISA')
        settlement_date = transaction_data.get('settlement_date')
        if settlement_date:
            settlement_str = settlement_date.strftime('%d/%m/%Y')
        else:
            # Calculate T+2 for stocks
            from datetime import timedelta
            settlement_str = (trans_date + timedelta(days=4)).strftime('%d/%m/%Y')

        # Total amount including charges (UK funds don't have separate charges)
        total_charges = transaction_data.get('total_charges')
        if total_charges is not None:
            total_with_charges = transaction_data['total_amount'] + total_charges
        else:
            total_with_charges = transaction_data['total_amount']

        c.setFont("Helvetica-Bold", 9)
        c.drawString(left_margin, y, account_type)
        c.drawString(left_margin + 300, y, f"Settlement Date: {settlement_str}")
        c.drawString(left_margin + 480, y, f"{total_with_charges:.2f}")
        y -= 30

        # Footer
        c.setFont("Helvetica", 7)
        c.drawString(left_margin, y, "E and OE")
        y -= 15
        c.drawString(left_margin, y, "Note:")
        y -= 10
        c.drawString(left_margin, y, "Retain this document as a record of your investment.")
        y -= 10
        c.drawString(left_margin, y, "Always quote your client number and contract note number in correspondence.")
        y -= 10
        c.drawString(left_margin, y, "This contract is subject to our normal terms and conditions of business and may also be subject to the rules of the London Stock Exchange.")
        y -= 10
        c.drawString(left_margin, y, "Details of any commission shared with third parties is available upon request.")

        # Save PDF
        c.save()
        print(f"Generated PDF: {output_path}")


if __name__ == "__main__":
    # Example usage
    generator = HLContractNoteGenerator()

    # Sample transaction data
    sample_data = {
        'transaction_type': 'purchase',
        'stock_name': 'Celestica Inc',
        'ticker': 'CLS.TO',
        'isin': 'CA15101Q1081',
        'currency': 'CAD',
        'num_shares': 35,  # Anonymized (was 289)
        'price': 59.51,
        'exchange_rate': 0.5797,
        'total_amount': 1209.77,  # Scaled from original
        'dealing_charge': 11.95,
        'fx_charge': 10.58,  # Scaled from original
        'total_charges': 22.53,  # Scaled from original
        'transaction_date': datetime(2024, 3, 15, 18, 58),
        'account_type': 'HL Stocks & Shares ISA',
        'stock_type': 'Common Stock',
        'additional_info': {
            'order_type': 'Market Order',
            'venue': 'Off exchange',
            'broker': 'Canaccord Capital'
        }
    }

    output_path = 'scratch/anon_poc_B734680723_BOUGHT_Celestica_Inc.pdf'
    generator.generate_contract_note(sample_data, output_path)
    print(f"\nGenerated anonymized PDF: {output_path}")
    print("\nTo test parser:")
    print(f"  python3 -c \"from pdf_parser import parse_stock_transaction_pdf; print(parse_stock_transaction_pdf('{output_path}'))\"")
