import unittest
import os
import json
import shutil
from services.correction_service import CorrectionService, DATA_DIR

class TestLearningLoop(unittest.TestCase):
    def setUp(self):
        # Create data dir if it doesn't exist (it should be created by service, but test setup runs before)
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)

        # Use a temporary file for testing
        self.original_file = os.path.join(DATA_DIR, "corrections.json")
        self.backup_file = os.path.join(DATA_DIR, "corrections_backup.json")
        
        if os.path.exists(self.original_file):
            shutil.copy(self.original_file, self.backup_file)
            
        # Reset corrections for test
        with open(self.original_file, 'w') as f:
            json.dump([], f)
            
        self.service = CorrectionService()
        
    def tearDown(self):
        # Restore original corrections
        if os.path.exists(self.backup_file):
            shutil.move(self.backup_file, self.original_file)

    def test_save_and_retrieve_correction(self):
        raw_text = "Pos 5 Passfeder DIN6885 C45+C Form AS B=20 H=12 L=100 M6"
        fingerprint_context = "This is a Würth order with Liefertermin."
        
        correct_json = {
            "form": "AS",
            "dimensions": {"width": 20, "height": 12, "length": 100},
            "features": [{"feature_type": "thread", "spec": "M6"}]
        }
        
        # 1. Save Correction
        self.service.save_correction(
            raw_text_snippet=raw_text,
            correct_json=correct_json,
            full_text_context=fingerprint_context
        )
        
        # 2. Verify it's in the few-shot context for a similar document
        new_doc_text = "New Würth document..."
        context = self.service.get_few_shot_context(new_doc_text)
        
        print(f"\nGenerated Context:\n{context}")
        
        self.assertIn("LEARNED CORRECTIONS", context)
        self.assertIn("Pos 5 Passfeder", context)
        self.assertIn("M6", context)
        self.assertIn("AS", context)

    def test_fingerprint_filtering(self):
        # Save a Würth correction
        self.service.save_correction(
            raw_text_snippet="Würth Item",
            correct_json={"foo": "bar"},
            full_text_context="Würth"
        )
        
        # Save a Nosta correction
        self.service.save_correction(
            raw_text_snippet="Nosta Item",
            correct_json={"baz": "qux"},
            full_text_context="Nosta"
        )
        
        # Check context for a Nosta document -> Should only see Nosta correction
        context = self.service.get_few_shot_context("This is a Nosta document.")
        self.assertIn("Nosta Item", context)
        self.assertNotIn("Würth Item", context)

if __name__ == '__main__':
    unittest.main()
