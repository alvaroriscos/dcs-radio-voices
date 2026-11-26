# Licencias de voces y librerías incluidas

La aplicación es para **uso personal**. Todas las piezas incluidas permiten ese uso.
Licencias comprobadas en los metadatos de cada paquete o en la ficha (MODEL_CARD) de cada voz.

## Voces (modelos)

| Voz / modelo | Licencia | Notas |
|---|---|---|
| Kokoro-82M v1.0 (28 voces en inglés US/GB) | Apache 2.0 | hexgrad/Kokoro-82M; ONNX de thewh1teagle/kokoro-onnx |
| Piper en_US-john-medium | Dominio público | Grabaciones de LibriVox |
| Piper en_US-bryce-medium | Dominio público | |
| Piper en_US-joe-medium | CC0 | OHF-Voice/voice-datasets |
| Piper en_GB-northern_english_male-medium | CC BY-SA 4.0 | |
| Piper en_US-ryan-medium | CC BY-NC-SA 4.0 | **Solo uso no comercial** (válido para uso personal) |
| Piper en_US-libritts_r-medium (multi-hablante) | CC BY 4.0 | Conjunto LibriTTS-R |

Las fichas originales (MODEL_CARD) de las voces Piper están en `models/piper/`.

## Librerías

| Componente | Licencia |
|---|---|
| kokoro-onnx 0.6.1 | MIT (ver kokoro-onnx-MIT.txt) |
| piper-tts 1.8.0 (OHF-Voice/piper1-gpl) | GPL-3.0-or-later |
| espeak-ng (incluido en espeakng-loader y en piper-tts) | GPL-3.0 |
| phonemizer 3.6.0 | GPL-3.0 |
| onnxruntime 1.32.0 | MIT |
| numpy 2.5.5 | BSD-3-Clause (y otras permisivas) |
| scipy 1.18.1 | BSD-3-Clause |
| soundfile 0.14.0 / libsndfile, libogg, libvorbis | BSD-3-Clause / LGPL-2.1 / BSD |
| PySide6-Essentials 6.12.0 (Qt 6) | LGPL-3.0 |
| PyInstaller (cargador) | GPL-2.0 con excepción para el cargador |
| Inno Setup (instalador) | Licencia propia de Inno Setup, gratuita |

Como incluye componentes GPL-3.0 (piper-tts, espeak-ng, phonemizer), el conjunto se distribuye bajo
GPL-3.0-or-later (ver `LICENSE`). Para uso personal no hay ninguna obligación adicional.
