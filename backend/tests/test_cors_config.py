from app.main import DEFAULT_CORS_ORIGINS, _parse_cors_origins


def test_parse_cors_origins_keeps_local_defaults() -> None:
    assert _parse_cors_origins(None) == list(DEFAULT_CORS_ORIGINS)


def test_parse_cors_origins_adds_deployed_frontend_once() -> None:
    origin = "https://frontend-two-woad-59.vercel.app"

    origins = _parse_cors_origins(
        f" {origin}/, http://127.0.0.1:5173, {origin} "
    )

    assert origins == [*DEFAULT_CORS_ORIGINS, origin]
