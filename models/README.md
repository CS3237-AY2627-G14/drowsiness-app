# Model checkpoint

Included: `drowsiness_mobilenetv4_20261016_013212.pth`, using timm architecture
`mobilenetv4_conv_small.e2400_r224_in1k` and the checkpoint's evaluation transforms.
It classifies `active` and `fatigue` from 224×224 face crops.

SHA-256: `56ea281ee83a3f754218199aeaa2eb3422fe2d57da0ad2a399b6bd02e2bf4e6e`.

Select a compatible checkpoint with `DROWSINESS_MODEL_PATH` in the root `.env`
and restart the API. No download is needed; other `.pth` files are ignored by Git.
