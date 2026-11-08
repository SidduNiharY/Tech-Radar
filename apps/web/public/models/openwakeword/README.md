# openWakeWord Client-Side Models

This directory contains onnxruntime-web compatible model files for local, in-browser wake word detection ("Hey Jarvis").

## Models
- `melspectrogram.onnx`: Audio mel-spectrogram feature extractor.
- `embedding_model.onnx`: Audio representation embeddings model.
- `hey_jarvis_v0.1.onnx`: Binary classifier detecting the phrase "Hey Jarvis".

## Licensing & Attribution
- Author: David Scripka (@dscripka)
- License: Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0).
- Permitted Use: Personal, non-commercial research and local assistance.
- SHA-256 Checksums: Registered and verified in `infra/models/wakeword.yaml`.
