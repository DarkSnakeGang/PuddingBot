from wall import PatternResult
from wall import stream as ws
from wall.worker import decode_result, encode_result


def test_pattern_input_error():
    assert ws.pattern_input_error("12" * 45) is None
    assert "90 cells" in ws.pattern_input_error("12" * 40)
    assert "two cell values" in ws.pattern_input_error("012" * 30)


def test_merge_keeps_newer_image_under_text_update():
    image = PatternResult(content="gap 5", png=b"png-bytes")
    progress = PatternResult(content="searching…", retain_image=True)
    merged = ws._merge(image, progress)
    assert merged.content == "searching…"
    assert merged.png == b"png-bytes"
    assert merged.retain_image is False
    assert ws._merge(None, progress) is progress


def test_worker_round_trip():
    original = PatternResult(content="Ham Cycle · 14 walls", png=b"\x89PNG\r\n", retain_image=False)
    decoded = decode_result(encode_result(original).encode())
    assert decoded == original
