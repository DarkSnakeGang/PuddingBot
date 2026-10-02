import io

from PIL import Image

from cogs import image_caption as ic

CAPTION = "ceasefire means the firing ceases"


def test_caption_bar_matches_esmbot_layout():
    # esmBot renders this caption on a 360px-wide GIF as a 114px bar (2 lines)
    bar = ic._build_caption_bar(360, CAPTION)
    assert bar.size == (360, 114)
    luma = bar.convert("L")
    assert len(set(luma.getdata())) > 2  # antialiased, not thresholded


def test_gif_caption_keeps_frames_timing_and_gray_text():
    frames = [Image.new("RGB", (120, 80), (200, 30 * i, 40)) for i in range(4)]
    buf = io.BytesIO()
    frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:], duration=[40, 50, 40, 60], loop=0)
    data, ext = ic.caption_image(buf.getvalue(), CAPTION)
    out = Image.open(io.BytesIO(data))
    assert ext == "gif" and out.n_frames == 4
    durations = []
    for i in range(out.n_frames):
        out.seek(i)
        durations.append(out.info["duration"])
    assert durations == [40, 50, 40, 60]
    out.seek(0)
    bar_height = out.height - 80
    bar_colors = {c for _, c in out.convert("RGB").crop((0, 0, 120, bar_height)).getcolors(10000)}
    assert bar_colors <= set(ic.GRAY_RAMP) and len(bar_colors) > 2


def test_static_image_caption_is_png():
    buf = io.BytesIO()
    Image.new("RGB", (300, 200), "blue").save(buf, format="PNG")
    data, ext = ic.caption_image(buf.getvalue(), "hi")
    out = Image.open(io.BytesIO(data))
    assert ext == "png" and out.width == 300 and out.height > 200
