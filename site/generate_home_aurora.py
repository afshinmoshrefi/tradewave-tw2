"""Generate the static aurora background used by the TradeWave homepage.

The rendered image preserves the old layered purple/blue/green treatment without
asking the browser to animate, blur, and blend full-viewport layers while scrolling.
"""

from pathlib import Path

import numpy as np
from PIL import Image


WIDTH = 2048
HEIGHT = 1400
OUTPUT_PATH = Path(__file__).resolve().parent / "static" / "home-aurora-static.webp"


def _hex(value):
    value = value.lstrip("#")
    return np.array(
        [int(value[index:index + 2], 16) for index in (0, 2, 4)],
        dtype=np.float32,
    )


def _blend(image, color, amount):
    amount = np.clip(amount, 0.0, 1.0)[..., None]
    return image * (1.0 - amount) + color * amount


def _radial(x, y, center_x, center_y, radius_x, radius_y, softness=2.0):
    distance = np.sqrt(
        ((x - center_x) / radius_x) ** 2
        + ((y - center_y) / radius_y) ** 2
    )
    return np.clip(1.0 - distance, 0.0, 1.0) ** softness


def render():
    x = np.linspace(0.0, 1.0, WIDTH, dtype=np.float32)[None, :]
    y = np.linspace(0.0, 1.0, HEIGHT, dtype=np.float32)[:, None]
    x = np.broadcast_to(x, (HEIGHT, WIDTH))
    y = np.broadcast_to(y, (HEIGHT, WIDTH))

    top = _hex("#0d1526")
    middle = _hex("#0b1220")
    bottom = _hex("#090f1c")
    first_half = np.clip(y / 0.46, 0.0, 1.0)[..., None]
    second_half = np.clip((y - 0.46) / 0.54, 0.0, 1.0)[..., None]
    image = top * (1.0 - first_half) + middle * first_half
    image = image * (1.0 - second_half) + bottom * second_half

    layers = (
        ("#9678ff", 0.32, (0.50, -0.05, 0.58, 0.42, 1.75)),
        ("#6c56ec", 0.18, (0.50, -0.01, 0.44, 0.35, 2.10)),
        ("#6078f0", 0.13, (0.50, -0.10, 0.76, 0.56, 1.85)),
        ("#604ad6", 0.16, (0.02, 0.00, 0.50, 0.52, 1.90)),
        ("#8c6cff", 0.15, (0.98, 0.02, 0.50, 0.52, 1.90)),
        ("#3fb68b", 0.09, (0.08, 0.94, 0.58, 0.52, 2.10)),
        ("#e5687f", 0.06, (0.92, 0.96, 0.48, 0.46, 2.10)),
    )
    for color, opacity, radial_args in layers:
        image = _blend(
            image,
            _hex(color),
            _radial(x, y, *radial_args) * opacity,
        )

    edge_distance = np.sqrt(
        ((x - 0.5) / 0.78) ** 2 + ((y - 0.30) / 0.92) ** 2
    )
    vignette = np.clip((edge_distance - 0.56) / 0.54, 0.0, 1.0) * 0.30
    image *= (1.0 - vignette[..., None])

    rng = np.random.default_rng(20260724)
    grain = rng.normal(0.0, 1.1, image.shape[:2]).astype(np.float32)
    image += grain[..., None]

    image = np.clip(image, 0, 255).astype(np.uint8)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(image, "RGB").save(
        OUTPUT_PATH,
        "WEBP",
        quality=84,
        method=6,
    )
    print("%s (%d bytes)" % (OUTPUT_PATH, OUTPUT_PATH.stat().st_size))


if __name__ == "__main__":
    render()
