from extto_torznab.upstream import sign_magnet_request


def test_hmac_golden_vector() -> None:
    # SHA256("torrent_id|timestamp|searchPageToken"), from the verified PoC scheme.
    assert (
        sign_magnet_request("16276717", 1787944372, "31db34d4de129bc16fb0a000743a3efc")
        == "42b9934ff09526400aa90b2c8da81f71efbfd22126b170f3633ba73285f4c91e"
    )
