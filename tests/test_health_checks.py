
import pytest
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop
from aiohttp import web
from app.main import handle_healthz

class HealthCheckTestCase(AioHTTPTestCase):
    async def get_application(self):
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
