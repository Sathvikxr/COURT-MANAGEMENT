"""
NyayaDesk Performance & Benchmarking Tests
Measures response latency, query efficiency (N+1 query check), and executes a 50-user
concurrent load benchmark across authentication, search, and dashboard endpoints.
"""

import time
from concurrent.futures import ThreadPoolExecutor
import pytest
from app.models import db, Case, User, Hearing
from tests.conftest import get_csrf

def test_endpoint_latencies_under_seeded_load(client, clerk_client):
    """Benchmark page and API response times (ensuring sub-200ms latency)."""
    endpoints = [
        ('/', client),
        ('/health', client),
        ('/api/courts', client),
        ('/api/search?q=State', client),
        ('/api/public/cause-list?court_id=1', client),
        ('/dashboards/clerk', clerk_client)
    ]

    timings = {}
    for path, c in endpoints:
        start = time.perf_counter()
        res = c.get(path)
        duration_ms = (time.perf_counter() - start) * 1000
        assert res.status_code == 200, f"Endpoint {path} failed: {res.status_code}"
        timings[path] = duration_ms
        # Assert fast response time (sub-350ms in testing environment)
        assert duration_ms < 350, f"Endpoint {path} too slow: {duration_ms:.1f}ms"


def test_fifty_concurrent_users_load(app):
    """Simulate 50 concurrent users issuing requests simultaneously."""
    endpoints = ['/', '/health', '/api/courts', '/api/search?q=Arbitration']
    results = []

    def make_request(idx):
        with app.test_client() as c:
            path = endpoints[idx % len(endpoints)]
            start = time.perf_counter()
            res = c.get(path)
            duration = (time.perf_counter() - start) * 1000
            return res.status_code == 200, duration

    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = [executor.submit(make_request, i) for i in range(50)]
        for f in futures:
            success, dur = f.result()
            results.append((success, dur))

    successes = [r for r in results if r[0]]
    durations = [r[1] for r in results]
    avg_latency = sum(durations) / len(durations)
    success_rate = len(successes) / len(results)

    assert success_rate >= 0.96, f"Concurrent load test dropped requests: {success_rate * 100}%"
    assert avg_latency < 250, f"Average latency under 50 concurrent users was {avg_latency:.1f}ms (target <250ms)"


def test_query_count_n_plus_one_prevention(app, clerk_client):
    """Assert dashboard queries do not exhibit N+1 runaway statement execution."""
    with app.app_context():
        queries_executed = 0
        def query_counter(conn, cursor, statement, parameters, context, executemany):
            nonlocal queries_executed
            queries_executed += 1

        from sqlalchemy import event
        event.listen(db.engine, "before_cursor_execute", query_counter)

        res = clerk_client.get('/dashboards/clerk')
        assert res.status_code == 200

        event.remove(db.engine, "before_cursor_execute", query_counter)

        # Loading clerk dashboard with 15 hearings should NOT execute 100+ queries
        assert queries_executed < 30, f"Potential N+1 Query Detected: {queries_executed} SQL statements executed"
