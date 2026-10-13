"""Live catalog regression tests use mocked Hugging Face responses, no network."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from localmoestudio import model_hub as hub


class CatalogTests(unittest.TestCase):
    def test_expected_families_have_quick_picks(self):
        repos = [repo.lower() for _, repo, _ in hub.CATALOG if repo]
        for name in ('gemma', 'qwen', 'llama', 'mistral', 'deepseek', 'phi', 'gpt-oss'):
            self.assertTrue(any(name in r for r in repos), name)

    def test_family_classification(self):
        for repo, expected in [
            ('unsloth/gemma-3-12b-it-GGUF', 'Gemma'),
            ('Qwen/Qwen3-30B-A3B-GGUF', 'Qwen'),
            ('bartowski/Meta-Llama-3.1-8B-Instruct-GGUF', 'Llama'),
            ('bartowski/mistralai_Mistral-Small-GGUF', 'Mistral'),
            ('unsloth/DeepSeek-R1-Distill-Qwen-14B-GGUF', 'Qwen'),
            ('microsoft/phi-4-gguf', 'Phi'),
            ('unsloth/gpt-oss-20b-GGUF', 'GPT-OSS'),
            ('author/new-architecture-GGUF', 'Other'),
        ]:
            # Distill model can straddle families. Defined priority is intentional.
            self.assertEqual(hub.model_family(repo), expected)

    def test_skip_gated_private_or_non_gguf(self):
        for record in [
            {'id':'user/test-GGUF', 'gated':'manual'},
            {'id':'user/test-GGUF', 'private':True},
            {'id':'user/test-transformers'},
            {'id':'../../bad-GGUF'},
        ]:
            self.assertIsNone(hub.normalize_model(record))
        model = hub.normalize_model({'id':'owner/Gemma-Fresh-GGUF', 'downloads':333,
                                     'lastModified':'2026-10-12T10:00:00Z'})
        self.assertEqual(model['updated'],'2026-10-12')
        self.assertEqual(model['family'],'Gemma')

    def test_search_uses_hf_api_and_does_not_download_weights(self):
        def fake_get(url):
            args=parse_qs(urlparse(url).query)
            self.assertEqual(args['filter'], ['gguf'])
            self.assertEqual(args['search'], ['gemma'])
            self.assertEqual(args['sort'], ['lastModified'])
            self.assertEqual(args['limit'], ['50'])
            return [
                {'id':'publisher/gemma-4-gguf','downloads':4,
                 'lastModified':'2026-10-13T00:00:00Z','tags':['gguf']},
                {'id':'publisher/Private-Gemma-GGUF','private':True},
            ]
        with patch.object(hub,'_get_json',side_effect=fake_get):
            models=hub.search_hub_models('gemma',50)
        self.assertEqual([x['id'] for x in models],['publisher/gemma-4-gguf'])

    def test_search_merge_dedup_newest_first(self):
        def fake_search(q, limit):
            return [
                {'id':'publisher/Gemma-GGUF','family':'Gemma','downloads':10,'updated':'2026-10-13'},
                {'id':'publisher/Qwen-GGUF','family':'Qwen','downloads':40,'updated':'2026-10-10'},
            ] if q == 'gemma' else [
                {'id':'publisher/Gemma-GGUF','family':'Gemma','downloads':10,'updated':'2026-10-13'},
            ]
        with patch.object(hub,'search_hub_models',side_effect=fake_search):
            models,warnings=hub.discover_models(queries=('gemma','qwen'),per_query=10)
        self.assertEqual([x['id'] for x in models],['publisher/Gemma-GGUF','publisher/Qwen-GGUF'])
        self.assertEqual(warnings,[])

    def test_discovery_partial_failure_still_works(self):
        def fake_search(q, limit):
            if q == 'qwen': raise OSError('network interrupted')
            return [{'id':'owner/Gemma-GGUF','family':'Gemma','downloads':20,'updated':'2026-10-13'}]
        with patch.object(hub,'search_hub_models',side_effect=fake_search):
            models,warnings=hub.discover_models(queries=('gemma','qwen'))
        self.assertEqual(len(models),1)
        self.assertEqual(len(warnings),1)

    def test_catalog_offline_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'catalog.json'
            models=[{'id':'unsloth/gemma-3-12b-it-GGUF','family':'Gemma',
                     'downloads':1,'updated':'2026-10-01'}]
            hub.save_catalog_cache(path,models,fetched_at='2026-10-13T09:00:00Z')
            read,date=hub.load_catalog_cache(path)
            self.assertEqual(date,'2026-10-13T09:00:00Z')
            self.assertEqual(read[0]['id'],models[0]['id'])
            path.write_text('broken-json')
            self.assertEqual(hub.load_catalog_cache(path),([],''))

if __name__=='__main__':
    unittest.main()
