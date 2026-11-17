import random

import numpy as np
from PIL import Image, ImageDraw

from p2p.data_gen.scans import _add_stamp, _degrade_image


def _page_with_ink() -> Image.Image:
    img = Image.new("RGB", (800, 600), (255, 255, 255))
    ImageDraw.Draw(img).rectangle((400, 40, 780, 200), fill=(200, 200, 200))
    return img


def test_specks_keep_clear_of_ink():
    img = Image.new("RGB", (600, 400), (255, 255, 255))
    ImageDraw.Draw(img).rectangle((200, 150, 400, 250), fill=(200, 200, 200))
    params = {
        "contrast": 1.0,
        "rotation_deg": 0.0,
        "dpi": 144,
        "specks": 300,
        "stamp": False,
        "blur_radius": 0.0,
        "noise_sigma": 0.0,
    }
    out = np.asarray(_degrade_image(img, params, random.Random(1), np.random.default_rng(1)))
    changed = (out != np.asarray(img)).any(axis=2)
    assert changed.any()  # specks were drawn at all
    m = 16
    ring = np.zeros_like(changed)
    ring[150 - m : 251 + m, 200 - m : 401 + m] = True
    ring[150:251, 200:401] = False  # a flat interior has no ink edge to misread
    assert not (changed & ring).any()


def test_stamp_does_not_cover_ink():
    src = np.asarray(_page_with_ink()).copy()
    for seed in range(20):
        out = np.asarray(_add_stamp(_page_with_ink(), random.Random(seed), 2.0))
        assert (out[40:201, 400:781] == src[40:201, 400:781]).all()
