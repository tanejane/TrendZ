import tempfile
import unittest
from pathlib import Path

import app_backend


class DetailTemplateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        old = dict(app_backend.app.config)
        self.addCleanup(app_backend.app.config.update,old)
        app_backend.app.config.update(TESTING=True,DATABASE_PATH=str(Path(self.temp.name)/'ui.sqlite3'))
        self.client = app_backend.app.test_client()

    def test_section_present_once_in_demo_and_real(self):
        for mode in ('demo','real'):
            app_backend.app.config['DATA_MODE']=mode
            response = self.client.get('/trend-detail/glass-skin')
            self.assertEqual(response.status_code,200)
            text = response.get_data(as_text=True)
            self.assertEqual(text.count('data-intelligence-topic="glass-skin"'),1)
            self.assertIn('Available means supported at the current evidence scope, not validated market truth.',text)
            self.assertIn('/static/js/intelligence.js',text)
            self.assertIn('/static/css/intelligence.css',text)
            self.assertIn('Back to Dashboard',text)

    def test_measured_actions_remain(self):
        app_backend.app.config['DATA_MODE']='real'
        text = self.client.get('/trend-detail/glass-skin').get_data(as_text=True)
        self.assertIn('href="/roi-insights"',text)
        self.assertIn('Source provenance',text)
        self.assertIn('Review structured evidence',text)

    def test_demo_commercial_sections_use_scenarios(self):
        app_backend.app.config['DATA_MODE']='demo'
        text = self.client.get('/trend-detail/glass-skin').get_data(as_text=True)
        self.assertIn('Business Assumptions',text)
        self.assertIn('Assumption-based Campaign Economics',text)
        self.assertNotIn('Predicted ROI',text)
        self.assertIn('Structured Evidence',text)
        self.assertNotIn('askAI(',text)
