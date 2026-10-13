"""Local desktop chat history retrieval, bounded and cross-account-safe."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from localmoestudio.chat_memory import (
    is_history_query, is_question_list_query, format_question_list,
    recall_context, archive_rows,
)

class Store:
    records = {
        'a': {'id': 'a', 'updated': '2026-10-11T12:00:00Z',
              'title': 'MoE models', 'messages': [
                  {'role':'user','content':'Which MoE can run with 6 GB VRAM?'},
                  {'role':'assistant','content':'Qwen3 30B-A3B may use RAM offload.'},
                  {'role':'user','content':'How fast is Qwen3 on this PC?'},
                  {'role':'assistant','content':'Measure tokens per second.'}]},
        'b': {'id': 'b', 'updated': '2026-10-10T12:00:00Z',
              'title': 'Herbal KG', 'messages': [
                  {'role':'user','content':'How can I build a herbal knowledge graph?'},
                  {'role':'assistant','content':'Use provenance and SHACL.'}]},
        'empty': {'id':'empty','updated':'2026-10-12T12:00:00Z',
                  'title':'New chat','messages':[]},
    }
    def list_all(self):
        return sorted(({k:v[k] for k in ('id','title','updated')}
                       for v in self.records.values()),
                      key=lambda x: x['updated'], reverse=True)
    def read(self,sid):
        return self.records[sid]

class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.store=Store()
    def test_screenshot_prompt_is_answered_locally(self):
        self.assertTrue(is_question_list_query(
            'from the chat history, list what i ask'))
    def test_normal_question_never_auto_retrieves(self):
        self.assertFalse(is_history_query('How does MoE offloading work?'))
        self.assertFalse(is_question_list_query('Give me a chat history database design'))
    def test_thai_history_request(self):
        self.assertTrue(is_question_list_query('จากประวัติแชท ฉันเคยถามอะไรบ้าง'))
    def test_lists_real_questions_only(self):
        answer,count=format_question_list(self.store)
        self.assertEqual(count,3)
        self.assertIn('How fast is Qwen3',answer)
        self.assertNotIn('Measure tokens per second',answer)
    def test_reports_truncated_inventory(self):
        answer,total=format_question_list(self.store,limit=1)
        self.assertEqual(total,3)
        self.assertIn('showing 1 of 3',answer)
    def test_topic_retrieval(self):
        value=recall_context(self.store,'Tell me what you said about Qwen3 in previous chats',max_results=1)
        self.assertIn('Qwen3',value)
        self.assertNotIn('herbal knowledge graph',value)
        self.assertIn('INCOMPLETE',value)
    def test_excludes_active_session(self):
        value=recall_context(self.store,'previous chat about Qwen3',exclude_session='a')
        self.assertNotIn('6 GB VRAM',value)
    def test_explicit_memory_only(self):
        self.assertEqual(recall_context(self.store,'Explain MoE Qwen3'),'')
    def test_context_bounded(self):
        self.assertLessEqual(len(recall_context(
            self.store,'previous chat about Qwen3',max_chars=500)),500)
    def test_no_saved_records(self):
        self.store.records={}
        answer,n=format_question_list(self.store)
        self.assertEqual(n,0)
        self.assertIn('No saved questions',answer)
    def test_helper_no_team_hub_references(self):
        self.assertEqual(len(archive_rows(self.store)),3)

if __name__=='__main__':
    unittest.main()
