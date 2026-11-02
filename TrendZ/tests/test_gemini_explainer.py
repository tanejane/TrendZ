"""Mocked Gemini adapter tests; no model-quality claims or live API usage."""
import os
import unittest
from unittest.mock import patch

import app_backend
from services.gemini_provider import GeminiUnavailable, compact_evidence, explain


class FakeModel:
    def generate_content(self, model, contents):
        assert model == 'gemini-3.5-flash-lite'
        assert 'MEASURED_EVIDENCE_JSON' in contents
        return type('Reply', (), {'text': 'Provisional momentum; inspect source evidence.'})()


class FakeClient:
    models = FakeModel()


class ExplainerTests(unittest.TestCase):
    def setUp(self):
        self.client = app_backend.app.test_client()
        self.old_mode = app_backend.app.config['DATA_MODE']
        app_backend.app.config['DATA_MODE'] = 'real'
        self.addCleanup(lambda: app_backend.app.config.update(DATA_MODE=self.old_mode))
        self.data = {'topic_id': 'known', 'question': 'What is supported?'}

    def test_disabled_without_opt_in(self):
        with patch.dict(os.environ, {'TRENDZ_ASSISTANT_ENABLED': 'false'}):
            r = self.client.post('/api/assistant/explain', json=self.data)
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json['code'], 'assistant_disabled')

    def test_request_validation_before_source_access(self):
        with patch.dict(os.environ, {'TRENDZ_ASSISTANT_ENABLED': 'true'}):
            r = self.client.post('/api/assistant/explain', json={'topic_id':'x', 'question':'a', 'extra':'b'})
            self.assertEqual(r.status_code, 400)
            r = self.client.post('/api/assistant/explain', json={'topic_id':'x', 'question':'a'*501})
            self.assertEqual(r.status_code, 400)

    def test_no_public_remote_calls(self):
        with patch.dict(os.environ, {'TRENDZ_ASSISTANT_ENABLED': 'true'}):
            r = self.client.post('/api/assistant/explain', json=self.data, environ_overrides={'REMOTE_ADDR':'8.8.8.8'})
        self.assertEqual(r.status_code, 403)

    def test_no_fake_fallback_when_unavailable(self):
        with patch.dict(os.environ, {'TRENDZ_ASSISTANT_ENABLED': 'true'}):
            r = self.client.post('/api/assistant/explain', json={'topic_id': '__not_a_configured_topic__', 'question':'what?'})
        self.assertEqual(r.status_code, 404)

    def test_provider_receives_bounded_real_evidence(self):
        evidence = {'topic_id': 'known', 'query_id':'canonical','query':'lip tint','market':'MY',
                    'data_mode':'real', 'dimensions': {'demand_momentum':{'state':'provisional','components':{'growth':42},'source':['google_trends']}}}
        result = compact_evidence(evidence)
        self.assertEqual(result['dimensions']['demand_momentum']['state'], 'provisional')
        self.assertIn('Provisional', explain('What is supported?', result, model='gemini-3.5-flash-lite', client=FakeClient()))
        with self.assertRaises(ValueError):
            explain('question', {**result,'data_mode':'demo'}, client=FakeClient())

    def test_gemini_error_has_no_key_leak(self):
        class BadClient:
            class models:
                @staticmethod
                def generate_content(**kwargs):
                    raise RuntimeError('secret-password-from-provider')
        with self.assertRaisesRegex(GeminiUnavailable, 'Gemini request failed') as context:
            explain('What is supported?', {'data_mode':'real'}, client=BadClient())
        self.assertNotIn('secret-password', str(context.exception))


if __name__ == '__main__':
    unittest.main()
