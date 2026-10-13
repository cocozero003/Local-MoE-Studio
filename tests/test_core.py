import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1] / "src"))
from localmoestudio.sessions import SessionStore
from localmoestudio.profiles import PROFILES, infer_profile, recommendation, apply_profile
from localmoestudio.engine_installer import choose_release_assets
from localmoestudio.model_hub import validate_repo

class FakeVar:
    def __init__(self): self.value = None
    def set(self, x): self.value=x

class AppTests(unittest.TestCase):
    def test_sessions(self):
        with tempfile.TemporaryDirectory() as d:
            store=SessionStore(d); sid=store.create()
            store.append_pair(sid,'ภาษาไทย','ตอบภาษาไทย')
            self.assertEqual(store.read(sid)['messages'][1]['content'],'ตอบภาษาไทย')
            self.assertEqual(len(store.list_all()),1)
            store.delete(sid); self.assertEqual(store.list_all(),[])
    def test_path_validation(self):
        with tempfile.TemporaryDirectory() as d:
            store=SessionStore(d)
            with self.assertRaises(ValueError):store.read('../bad')
    def test_profiles(self):
        vars={k:FakeVar() for k in PROFILES['Large MoE (low VRAM)']}
        apply_profile(vars,'Large MoE (low VRAM)')
        self.assertEqual(vars['moe'].value,'all')
        self.assertEqual(infer_profile('Qwen3-30B-A3B-Q4_K_S.gguf'),'Large MoE (low VRAM)')
        self.assertIn('system RAM',recommendation('Qwen3-30B-A3B.gguf',17*1024**3,'all'))
    def test_hf_validation(self):
        self.assertEqual(validate_repo('Qwen/Qwen3-30B-A3B-GGUF'),'Qwen/Qwen3-30B-A3B-GGUF')
        for bad in ['../etc','a//b','http://example.com','a/b/c']:
            with self.assertRaises(ValueError):validate_repo(bad)
    def test_release_selector(self):
        releases=[{'tag_name':'b9999','draft':False,'prerelease':False,'assets':[
            {'name':'llama-b9999-bin-win-cuda-12.4-x64.zip'},
            {'name':'cudart-llama-b9999-bin-win-cuda-12.4-x64.zip'},
            {'name':'llama-b9999-bin-win-cpu-x64.zip'}]}]
        tag,assets=choose_release_assets(releases,'cuda12')
        self.assertEqual(tag,'b9999'); self.assertEqual(len(assets),2)
        self.assertEqual(len(choose_release_assets(releases,'cpu')[1]),1)

if __name__=='__main__':unittest.main()
