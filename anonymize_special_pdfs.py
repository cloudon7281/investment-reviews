#!/usr/bin/env python3
"""
Anonymize special case PDFs (Subdivision, Conversion, Merger)
These are simpler letter-format PDFs with different layouts than contract notes.
"""

import os
import sys
from pathlib import Path
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class SpecialCaseAnonymizer:
    """Anonymize subdivision, conversion, and merger PDFs."""

    def __init__(self):
        self.anon_name = "Mr John Doe"
        self.anon_client_ref = "12345678"
        self.hl_address = ["One College Square South", "Anchor Road", "Bristol", "BS1 5HL"]

    def anonymize_subdivision_pdf(self, input_data, output_path):
        """
        Generate anonymized subdivision letter PDF.

        input_data: dict with keys:
            - stock_name: "Sezzle Inc"
            - date: "09 Apr 2025"
            - original_shares: 56
            - new_shares: 336
            - ratio: "1 share into 6 new shares"
            - subdivision_date: "28 March 2025"
            - account_update_date: "4 April 2025"
            - account_type: "Stocks & Shares ISA"
        """
        c = canvas.Canvas(output_path, pagesize=A4)
        width, height = A4
        left_margin = 50
        y = height - 50

        # Helper function
        def draw_text(text, y_pos, font="Helvetica", size=10, bold=False):
            c.setFont(f"{font}{'-Bold' if bold else ''}", size)
            c.drawString(left_margin, y_pos, text)
            return y_pos - (size + 4)

        # Title
        y = draw_text(f"{input_data['stock_name']} - Subdivision {input_data['date']}", y, size=14, bold=True)
        y -= 10
        y = draw_text(f"Client Reference: {self.anon_client_ref}", y)
        y -= 20

        # Salutation
        y = draw_text(f"Dear {self.anon_name}", y)
        y -= 20

        # Subject
        y = draw_text(f"{input_data['stock_name']} - Subdivision", y, bold=True)
        y -= 20

        # Main body
        y = draw_text(f"{input_data['stock_name']} has subdivided its share capital. Under the terms of the subdivision every {input_data['ratio']}", y)
        y = draw_text(f"as at the close of business on {input_data['subdivision_date']}.", y)
        y -= 20

        y = draw_text("How has this affected my account?", y, bold=True)
        y -= 10

        y = draw_text(f"Your {input_data['account_type']} was updated on {input_data['account_update_date']} on the following basis:", y)
        y -= 10

        y = draw_text(f"Original holding of {input_data['stock_name']} shares: {input_data['original_shares']} shares", y)
        y = draw_text(f"New {input_data['stock_name']} shares you have received (in place of your original holding): {input_data['new_shares']} shares", y)
        y -= 20

        # Footer
        y = draw_text("This correspondence is for your information only and no action is required. Should you have any queries relating to this", y, size=9)
        y = draw_text("matter please contact us.", y, size=9)
        y -= 15
        y = draw_text("If your circumstances mean you'd like some extra support, or you have specific accessibility needs, there are lots of ways we can help.", y, size=8)
        y = draw_text("Visit www.hl.co.uk/support or call us on 0117 900 9000 to find out more.", y, size=8)
        y -= 20

        y = draw_text("Yours sincerely", y)
        y -= 10
        y = draw_text("Corporate Actions Team", y)
        y = draw_text("Hargreaves Lansdown", y)

        c.save()
        print(f"Generated: {output_path}")

    def anonymize_merger_pdf(self, input_data, output_path):
        """
        Generate anonymized merger letter PDF.

        input_data: dict with keys:
            - stock_name: "Everbridge Inc"
            - date: "18 Jul 2024"
            - acquirer: "Thoma Bravo"
            - price_per_share_usd: 35.00
            - exchange_rate: 0.77224311
            - price_per_share_gbp: 27.028508
            - original_shares: 77
            - total_proceeds: 2081.20
            - settlement_date: "10 July 2024"
            - cutoff_date: "3 July 2024"
            - account_type: "Stocks & Shares ISA"
        """
        c = canvas.Canvas(output_path, pagesize=A4)
        width, height = A4
        left_margin = 50
        y = height - 50

        def draw_text(text, y_pos, font="Helvetica", size=10, bold=False):
            c.setFont(f"{font}{'-Bold' if bold else ''}", size)
            c.drawString(left_margin, y_pos, text)
            return y_pos - (size + 4)

        # Title
        y = draw_text(f"{input_data['stock_name']} - Merger {input_data['date']}", y, size=14, bold=True)
        y -= 10
        y = draw_text(f"Reference: {self.anon_client_ref}", y)
        y -= 20

        y = draw_text(f"Dear {self.anon_name}", y)
        y -= 20

        y = draw_text(f"{input_data['stock_name']} - Merger", y, bold=True)
        y -= 20

        y = draw_text("What has happened?", y, bold=True)
        y -= 10
        y = draw_text(f"{input_data['stock_name']} recently announced that it had agreed terms on an acquisition of the company by {input_data['acquirer']}.", y)
        y = draw_text(f"The acquisition has been implemented by way of merger agreement and has resulted in USD{input_data['price_per_share_usd']:.2f} in place of each {input_data['stock_name']} share", y)
        y = draw_text(f"held at the close of business on {input_data['cutoff_date']}.", y)
        y -= 20

        y = draw_text("How has my portfolio been affected?", y, bold=True)
        y -= 10
        y = draw_text(f"The merger proceeds have now been paid. Please note that the cash was received in US Dollars and was converted to Pound Sterling on", y)
        y = draw_text(f"the day of receipt, with USD1.00 being equal to {input_data['exchange_rate']*100:.6f}p. As a result, you have received a Sterling payment of £{input_data['price_per_share_gbp']:.6f} per share.", y)
        y -= 10

        y = draw_text(f"Your {input_data['account_type']} was updated on {input_data['settlement_date']} on the following basis:", y)
        y -= 10
        y = draw_text(f"Original holding of {input_data['stock_name']} shares, now removed from your account: {input_data['original_shares']} shares", y)
        y = draw_text(f"Resulting proceeds credited to your {input_data['account_type']}: £ {input_data['total_proceeds']:.2f}", y)
        y -= 20

        y = draw_text("Do I need to take any action?", y, bold=True)
        y -= 10
        y = draw_text("No. The merger has completed; this message is for information purposes only. Should you wish to reinvest this cash in further stocks /", y)
        y = draw_text("funds of your choice, you may reinvest the proceeds online. Should you have any queries please do not hesitate to contact us.", y)
        y -= 20

        y = draw_text("Yours sincerely", y)
        y -= 10
        y = draw_text("Corporate Actions Team", y)
        y = draw_text("Hargreaves Lansdown", y)

        c.save()
        print(f"Generated: {output_path}")

    def anonymize_conversion_pdf_letter(self, input_data, output_path):
        """
        Generate anonymized conversion letter PDF.

        input_data: dict with keys:
            - fund_name: "JPMorgan Emerging Markets"
            - date: "06 Mar 2025"
            - old_class: "Class B - Accumulation (GBP)"
            - new_class: "Class C - Accumulation (GBP)"
            - conversion_ratio: 0.34243734
            - old_units: 472.701
            - new_units: 161.887
            - update_date: "20 February 2025"
            - account_type: "Fund & Share Account"
        """
        c = canvas.Canvas(output_path, pagesize=A4)
        width, height = A4
        left_margin = 50
        y = height - 50

        def draw_text(text, y_pos, font="Helvetica", size=10, bold=False):
            c.setFont(f"{font}{'-Bold' if bold else ''}", size)
            c.drawString(left_margin, y_pos, text)
            return y_pos - (size + 4)

        # Title
        y = draw_text(f"{input_data['fund_name']} - Unit Class Conversion {input_data['date']}", y, size=14, bold=True)
        y -= 10
        y = draw_text(f"Client Reference: {self.anon_client_ref}", y)
        y -= 20

        y = draw_text(f"Dear {self.anon_name}", y)
        y -= 20

        y = draw_text(f"{input_data['fund_name']} \u2013 Unit Class Conversion", y, bold=True)
        y -= 20

        y = draw_text(f"We have converted your holding of {input_data['fund_name']} units into a newer equivalent unit class with a lower ongoing charge. This", y)
        y = draw_text("ensures you hold the cheapest version of the fund currently available through HL.", y)
        y -= 10

        y = draw_text(f"As a result, all {input_data['old_class']} units of {input_data['fund_name']} have been converted into the {input_data['new_class']}", y)
        y = draw_text(f"unit class. You have received {input_data['conversion_ratio']:.8f} {input_data['new_class']} units for each {input_data['old_class']} unit", y)
        y = draw_text("converted.", y)
        y -= 20

        y = draw_text("How has my account been affected?", y, bold=True)
        y -= 10
        y = draw_text(f"Your {input_data['account_type']} was updated on {input_data['update_date']} on the following basis:", y)
        y -= 10

        y = draw_text(f"Number of {input_data['fund_name']}{input_data['old_class']} units {input_data['old_units']:.3f} units", y)
        y = draw_text("originally held:", y)
        y -= 10
        y = draw_text(f"Number of new {input_data['fund_name']}{input_data['new_class']} {input_data['new_units']:.3f} units", y)
        y = draw_text("units credited, in place of your original holding:", y)
        y -= 20

        y = draw_text("This correspondence is for your information only and no action is required. Should you have any queries relating to this matter please", y, size=9)
        y = draw_text("contact us.", y, size=9)
        y -= 20

        y = draw_text("Yours sincerely", y)
        y -= 10
        y = draw_text("Corporate Actions Team", y)
        y = draw_text("Hargreaves Lansdown", y)

        c.save()
        print(f"Generated: {output_path}")


def main():
    """Generate anonymized special case PDFs."""
    anonymizer = SpecialCaseAnonymizer()

    # 1. Sezzle Subdivision
    sezzle_data = {
        'stock_name': 'Sezzle Inc',
        'date': '09 Apr 2025',
        'original_shares': 96532,  # Anonymized (was 56) - matches buy transaction
        'new_shares': 579192,  # 96532 * 6
        'ratio': '1 share into 6 new shares',
        'subdivision_date': '28 March 2025',
        'account_update_date': '4 April 2025',
        'account_type': 'Stocks & Shares ISA'
    }
    anonymizer.anonymize_subdivision_pdf(
        sezzle_data,
        'anonymised_test_data/ISA/2025/Subdivision/sezzle+inc+-+subdivision.pdf'
    )

    # 2. Everbridge Merger
    everbridge_data = {
        'stock_name': 'Everbridge Inc',
        'date': '18 Jul 2024',
        'acquirer': 'Thoma Bravo',
        'price_per_share_usd': 35.00,
        'exchange_rate': 0.77224311,
        'price_per_share_gbp': 27.028508,
        'original_shares': 4175,  # Anonymized (was 77) - matches buy transaction
        'total_proceeds': round(4175 * 27.028508, 2),
        'settlement_date': '10 July 2024',
        'cutoff_date': '3 July 2024',
        'account_type': 'Stocks & Shares ISA'
    }
    anonymizer.anonymize_merger_pdf(
        everbridge_data,
        'anonymised_test_data/Taxable/2025/Merger/everbridge+inc+-+merger.pdf'
    )

    # 3. JPMorgan Conversion
    jpmorgan_data = {
        'fund_name': 'JPMorgan Emerging Markets',
        'date': '06 Mar 2025',
        'old_class': 'Class B - Accumulation (GBP)',
        'new_class': 'Class C - Accumulation (GBP)',
        'conversion_ratio': 0.34243734,
        'old_units': 30615,  # Anonymized (was ~472.701)
        'new_units': round(30615 * 0.34243734, 3),
        'update_date': '20 February 2025',
        'account_type': 'Fund & Share Account'
    }
    anonymizer.anonymize_conversion_pdf_letter(
        jpmorgan_data,
        'anonymised_test_data/Taxable/2025/Conversion/jpmorgan+-+unit+class+conversion+.pdf'
    )

    print("\nNote: Contract note PDFs (B/S prefix) in Conversion/Merger/Subdivision directories")
    print("are handled by the regular batch_anonymize.py script")


if __name__ == "__main__":
    main()
