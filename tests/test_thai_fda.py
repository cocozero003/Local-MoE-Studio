import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from localmoestudio.thai_fda import rule_extract, grounding_context

class ThaiFDATests(unittest.TestCase):
    def test_rule_extraction_is_predecision_only(self):
        q=rule_extract("แผ่นปิดแผล มี chlorhexidine กลไกหลักทางกายภาพ")
        self.assertIn("PHYSICAL",q["pmoa_types_predecision"])
        self.assertEqual(q["candidate_class"],"MEDICAL_DEVICE")
        self.assertNotIn("final_class",q)

    def test_grounding_requires_human_authorization(self):
        result={"query":{"candidate_class":"MEDICAL_DEVICE"},"precedents":[],"human_authorization_required":True}
        prompt=grounding_context(result)
        self.assertIn("current law first",prompt)
        self.assertIn("human authorization",prompt)
        self.assertIn("NOT instructions",prompt)

if __name__=="__main__":unittest.main()
