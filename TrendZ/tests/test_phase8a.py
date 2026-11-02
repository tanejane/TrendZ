import tempfile
import unittest
from pathlib import Path

import app_backend


class PortfolioBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        old=dict(app_backend.app.config);self.addCleanup(app_backend.app.config.update,old)
        app_backend.app.config.update(TESTING=True,DATA_MODE='real',DATABASE_PATH=str(Path(self.temp.name)/'audit.sqlite3'))
        self.client=app_backend.app.test_client()

    def test_measured_dashboard_excludes_simulated_sections(self):
        text=self.client.get('/').get_data(as_text=True)
        self.assertIn('Beauty trend evidence',text)
        for phrase in ('AI Trend Forecasting','Emerging Trends','Total Reach','Trend Score','/api/early-detection'):
            self.assertNotIn(phrase,text)
        self.assertIn('Provider not configured',text)
        self.assertIn('disabled aria-describedby="assistant-status"',text)

    def test_empty_measured_history_is_not_filled(self):
        response=self.client.get('/api/trends').json
        self.assertTrue(response['trends'])
        self.assertTrue(all(t['data_mode']=='unavailable' for t in response['trends']))
        self.assertTrue(all(t['trend_score'] is None for t in response['trends']))

    def test_measured_watchlist_keeps_core_flow_not_fake_alerts(self):
        text=self.client.get('/watchlist').get_data(as_text=True)
        self.assertIn('data-saved-only="true"',text)
        self.assertNotIn('High Priority Alerts',text)
        self.assertIn('automatic alerts',text)

    def test_legacy_demo_remains_explicit(self):
        app_backend.app.config['DATA_MODE']='demo'
        text=self.client.get('/').get_data(as_text=True)
        self.assertIn('Demo mode: example trends and analytics',text)

    def test_unknown_detail_is_clear_404(self):
        response=self.client.get('/trend-detail/not-configured')
        self.assertEqual(response.status_code,404)
        self.assertIn('No example topic has been substituted',response.get_data(as_text=True))

    def test_measured_rendering_has_no_html_interpolation(self):
        script=(Path(app_backend.BASE_DIR)/'static/js/evidence-dashboard.js').read_text()
        self.assertNotIn('innerHTML',script)
        self.assertNotIn('window.open',script)
        self.assertIn('textContent',script)
        self.assertIn('encodeURIComponent(topic.id)',script)


if __name__=='__main__':unittest.main()
