"""
NyayaDesk Security & RBAC Tests - Route x Role Authorization Matrix
Systematically asserts HTTP 200, 302, 401, and 403 access control across all 8 roles.
"""

import pytest

ROLES = ['anonymous', 'government', 'registrar', 'judge', 'clerk', 'lawyer', 'litigant', 'police']

def get_client_for_role(role, client_fixtures):
    return client_fixtures[role]

@pytest.fixture
def all_role_clients(client, gov_client, reg_client, judge_client, clerk_client, lawyer_client, litigant_client, police_client):
    return {
        'anonymous': client,
        'government': gov_client,
        'registrar': reg_client,
        'judge': judge_client,
        'clerk': clerk_client,
        'lawyer': lawyer_client,
        'litigant': litigant_client,
        'police': police_client
    }

def test_public_routes_accessible_to_all(all_role_clients):
    """Assert public routes return 200 for anonymous and every authenticated role."""
    public_routes = ['/', '/demo-guide', '/health']
    for role, c in all_role_clients.items():
        for r in public_routes:
            res = c.get(r)
            assert res.status_code == 200, f"Role {role} failed to access public route {r}: status {res.status_code}"


def test_dashboard_rbac_matrix(all_role_clients):
    """
    Assert dashboard endpoints are strictly protected:
    - Target role gets 200
    - Other authenticated roles get 403
    - Anonymous gets 302 redirect to /auth/login or 401
    """
    dashboards = {
        'government': '/dashboards/government',
        'registrar': '/dashboards/registrar',
        'judge': '/dashboards/judge',
        'clerk': '/dashboards/clerk',
        'lawyer': '/dashboards/lawyer',
        'litigant': '/dashboards/litigant',
        'police': '/dashboards/police'
    }

    for target_role, path in dashboards.items():
        for role, c in all_role_clients.items():
            res = c.get(path)
            if role == target_role:
                assert res.status_code == 200, f"Target role {role} was denied access to its own dashboard {path}: {res.status_code}"
            elif role == 'anonymous':
                assert res.status_code in [302, 401], f"Anonymous was not redirected on dashboard {path}: {res.status_code}"
            else:
                assert res.status_code == 403, f"Role {role} breached access into {target_role} dashboard {path}: got {res.status_code} instead of 403"


def test_api_rbac_matrix(all_role_clients):
    """
    Assert REST API endpoints enforce role checks:
    - Authorized roles get 200
    - Unauthorized roles get 403
    - Anonymous gets 401
    """
    api_matrix = [
        ('/api/gov/approvals', ['government']),
        ('/api/registrar/cases', ['registrar']),
        ('/api/judge/cause-list', ['judge']),
        ('/api/clerk/cases', ['clerk', 'registrar', 'judge', 'government']),
        ('/api/lawyer/cases', ['lawyer']),
        ('/api/litigant/cases', ['litigant']),
        ('/api/police/dockets', ['police', 'government', 'judge']),
    ]

    for path, allowed in api_matrix:
        for role, c in all_role_clients.items():
            res = c.get(path)
            if role == 'anonymous':
                assert res.status_code in [401, 302], f"Anonymous allowed on API {path}: {res.status_code}"
            elif role in allowed:
                assert res.status_code == 200, f"Allowed role {role} got {res.status_code} on {path}"
            else:
                assert res.status_code == 403, f"Unauthorized role {role} breached API {path}: got {res.status_code} instead of 403"
