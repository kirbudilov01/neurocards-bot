
import pytest
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop
from aiohttp import web
from unittest.mock import patch

class HealthCheckTestCase(AioHTTPTestCase):
    @patch('app.db.create_client')
    async def get_application(self, mock_create_client):
        from app.main import handle_healthz
        app = web.Application()
        app.router.add_get('/', handle_healthz)
        app.router.add_get('/healthz', handle_healthz)
        return app

    @unittest_run_loop
    async def test_health_check_root(self):
        resp = await self.client.request("GET", "/")
        assert resp.status == 200
        text = await resp.text()
        assert text == "ok"

    @unittest_run_loop
    async def test_health_check_healthz(self):
        resp = await self.client.request("GET", "/healthz")
        assert resp.status == 200
        text = await resp.text()
        assert text == "ok"
