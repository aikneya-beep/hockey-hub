from app_v56 import app


def test_v56_core_routes_registered():
    paths = {getattr(route, "path", None) for route in app.routes}
    expected = {
        "/",
        "/big-hockey",
        "/my-hockey",
        "/my-hockey/environment",
        "/my-hockey/closet",
        "/my-hockey/memory",
        "/login",
    }
    assert expected <= paths
