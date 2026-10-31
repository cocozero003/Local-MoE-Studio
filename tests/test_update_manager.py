import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from localmoestudio.update_manager import install_data_pack, rollback_data, validate_data_root


def make_pack(version):
    files={
        "retrieval_index.csv":"case_id,product_case_id,year\nC1,P1,2026\n",
        "predecision_features.csv":"case_id,agenda_predecision,details_predecision\nC1,a,b\n",
        "cases.csv":"case_id,product_case_id,retrieval_eligible\nC1,P1,1\n",
        "precedent_decisions_sanitized.csv":"case_id,decision_status,final_class_auto_silver\nC1,PROVISIONAL_SINGLE_CLASS,DRUG\n",
        "model_config_v316.json":json.dumps({"hybrid_score":{"text_weight":0.95,"structured_weight":0.05},"structured_field_weights":{}}),
        "artifacts/case_order.csv":"case_id,product_case_id,year,global_order\nC1,P1,2026,1\n",
        "artifacts/tfidf_vectorizer.joblib":"x"*256,
        "artifacts/tfidf_matrix.npz":"y"*256,
        "MANIFEST.json":json.dumps({"version":version}),
    }
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w",zipfile.ZIP_DEFLATED) as z:
        for name,value in files.items():z.writestr("pack/"+name,value)
    return buf.getvalue()


class UpdateManagerTests(unittest.TestCase):
    def test_install_and_rollback_data_pack(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/"thai_fda_precedent"
            r1=install_data_pack(make_pack("v1"),"v1.zip",data_dir=root)
            self.assertEqual(r1["data_version"],"v1")
            r2=install_data_pack(make_pack("v2"),"v2.zip",data_dir=root)
            self.assertEqual(r2["data_version"],"v2")
            self.assertTrue(r2["backup_available"])
            r3=rollback_data(root)
            self.assertEqual(r3["data_version"],"v1")

    def test_rejects_zip_traversal(self):
        buf=io.BytesIO()
        with zipfile.ZipFile(buf,"w") as z:z.writestr("../escape.txt","bad")
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                install_data_pack(buf.getvalue(),"bad.zip",data_dir=Path(td)/"data")

    def test_validate_headers(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            with zipfile.ZipFile(io.BytesIO(make_pack("v1"))) as z:z.extractall(root)
            result=validate_data_root(root/"pack")
            self.assertTrue(result["ok"])
            self.assertEqual(result["version"],"v1")


if __name__=="__main__":unittest.main()
