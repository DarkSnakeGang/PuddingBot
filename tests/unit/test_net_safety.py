import pytest

import net_safety


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://10.0.0.5/x",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://0.0.0.0/",
        "ftp://8.8.8.8/",
        "file:///etc/passwd",
        "http:///nohost",
    ],
)
def test_check_url_rejects_non_public(url):
    with pytest.raises(net_safety.UnsafeURL):
        net_safety.check_url(url)


def test_check_url_allows_public_ip_literal():
    net_safety.check_url("https://8.8.8.8/")


@pytest.mark.parametrize(
    "ip, public",
    [("8.8.8.8", True), ("100.64.0.1", False), ("224.0.0.1", False), ("::ffff:10.0.0.1", False)],
)
def test_ip_classification(ip, public):
    assert net_safety._ip_is_public(ip) is public
