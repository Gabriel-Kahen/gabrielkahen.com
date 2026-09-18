from types import SimpleNamespace

import camera_server


def request(headers=None, client="127.0.0.1"):
    return SimpleNamespace(headers=headers or {}, client_address=(client, 1234))


def test_camera_allows_site_images_and_rejects_cross_site_embedding():
    allowed = request({
        "Host": "gabepi.tail0cb95e.ts.net:8443",
        "Sec-Fetch-Site": "cross-site",
        "Sec-Fetch-Dest": "image",
        "Referer": "https://gabrielkahen.com/draw/",
    })
    denied = request({**allowed.headers, "Referer": "https://example.com/"})
    assert camera_server.allowed_request(allowed)
    assert not camera_server.allowed_request(denied)
    assert not camera_server.allowed_request(request({"Host": "example.com"}))


def test_camera_allows_site_fetch_for_local_network_access():
    allowed = request({
        "Host": "gabepi.tail0cb95e.ts.net:8443",
        "Sec-Fetch-Site": "cross-site",
        "Sec-Fetch-Dest": "empty",
        "Origin": "https://gabrielkahen.com",
    })
    denied = request({**allowed.headers, "Origin": "https://example.com"})
    assert camera_server.allowed_request(allowed)
    assert not camera_server.allowed_request(denied)


def test_camera_rate_limit_has_a_small_burst():
    camera_server.requests.clear()
    visitor = request(client="203.0.113.1")
    assert not any(camera_server.rate_limited(visitor) for _ in range(16))
    assert camera_server.rate_limited(visitor)
