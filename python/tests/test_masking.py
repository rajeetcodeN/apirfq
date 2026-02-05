import unittest
import re
import sys
import os

# Add parent directory to path so we can import services
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.masking import RegexMasker, extract_document_header

class TestMaskingService(unittest.TestCase):
    def setUp(self):
        self.masker = RegexMasker()

    def test_extract_header_rfqIT(self):
        text = "Anfrage Nr. 12345678 from 2023-10-27"
        header = extract_document_header(text)
        self.assertEqual(header.rfq_number, "12345678")
        self.assertEqual(header.document_date, "2023-10-27")

    def test_extract_header_customer(self):
        text = "F. REYHER Nchfg. GmbH & Co. KG"
        header = extract_document_header(text)
        # Regex might extract "F. REYHER" or similar depending on exact match logic
        self.assertTrue("REYHER" in header.customer_name)

    def test_blocklist_nosta(self):
        # Ensure Nosta is explicitly blocked/recognized
        text = "Order from Nosta GmbH regarding parts."
        masked, token_map = self.masker.mask(text)
        
        # Should be replaced by {{COMPANY_1}} etc.
        self.assertNotIn("Nosta GmbH", masked)
        # Check for presence of masked token
        self.assertTrue("{{COMPANY_" in masked or "{{COMPANY}}" in masked)

    def test_german_phone(self):
        text = "Call us at 09074/42117 today."
        masked, token_map = self.masker.mask(text)
        self.assertNotIn("09074/42117", masked)
        self.assertTrue("{{PHONE}}" in masked)

    def test_email_and_fax(self):
        text = "Contact: test.user@company.com and Fax: +49 89 123456."
        masked, token_map = self.masker.mask(text)
        
        # Check Email
        # Should be {{EMAIL_1}} or similar
        self.assertTrue(re.search(r"{{EMAIL_\d+}}", masked), f"Email not masked in: {masked}")
        self.assertNotIn("test.user@company.com", masked)
        
        # Check Fax (Labeled pattern)
        # Should preserve 'Fax: ' and mask the number
        self.assertTrue("Fax:" in masked)
        self.assertNotIn("+49 89 123456", masked)
        self.assertTrue("{{PHONE}}" in masked)

if __name__ == '__main__':
    unittest.main()
