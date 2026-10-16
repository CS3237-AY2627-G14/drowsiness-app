# Detector fixtures

`portrait.jpg` is MediaPipe's public test portrait:
https://storage.googleapis.com/mediapipe-assets/portrait.jpg

Inference tests fit the entire image into 1280×720 with padding, then encode JPEG.
They exercise real face detection, EAR landmarks and the pinned CNN checkpoint.
No-face and malformed-image cases are generated in memory.
