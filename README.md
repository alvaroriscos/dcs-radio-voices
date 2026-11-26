# DCS Radio Voices

Aplicación de escritorio para Windows que convierte el guion `.txt` de una misión de DCS World en
audio de radio realista. Funciona **sin internet** y sin servicios de pago.

## Uso

1. Instala `DCSRadioVoices-Setup-x.y.z.exe` (no pide administrador ni Python).
2. Abre **DCS Radio Voices**, pulsa **Elegir guion…** y elige la **carpeta de salida**.
3. Revisa las pestañas **Voces** (voz, velocidad y tono por hablante) y **Efectos y salida**.
4. Selecciona una línea y pulsa **▶ Previsualizar línea** para escucharla.
5. Pulsa **Generar todo**.

En la carpeta de salida se crean:

| Archivo | Contenido |
|---|---|
| `<guion> - COMPLETO.ogg` | Todas las líneas en orden, con el silencio elegido entre ellas (2,5 s por defecto, exacto a la muestra) |
| `lineas/<HABLANTE> <NNN> <CLAVE> <N>s.ogg` | Un archivo por línea, p. ej. `LEAD 05 ATIS 6s.ogg` |
| `<guion> - manifiesto.csv` | archivo, hablante, número, toma, hilo, tono, efecto, voz, texto, texto locutado, duración, inicio y fin (en segundos y en muestras) dentro del archivo único |

Todos los OGG son Vorbis mono a 44 100 Hz con la misma calidad. `N` en el nombre es la duración real
redondeada hacia arriba. Los ajustes (voces por hablante, efectos, diccionario) se guardan en
`%APPDATA%\DCSRadioVoices\settings.json`.

### Formato del guion

```
== THREAD 02 · Ramp & start-up · Talud · AUX 1 143.200 · S1 · flag RAMP_GO ==
PLAYER 002 (firme, tranquilo) [AIR] ~3s : Talud, radio check.
[02] WING 2 (calm) · 2 s : Two.
PLAYER 078A (firme) [AIR] ~7s : ...      ← toma/rama A
PLAYER 078B (firme) [AIR] ~13s : ...     ← toma/rama B
```

- Solo se locuta el texto que va **después de los dos puntos**. Nunca se leen el número, el hablante,
  el tono, la duración, las etiquetas ni las cabeceras. Tampoco se leen las acotaciones entre paréntesis
  o corchetes dentro del texto.
- Se toleran espacios de más, mayúsculas y minúsculas, guion corto o largo (`· – — |`), líneas vacías,
  comentarios (`#`, `//`, `;`, `--`) y tomas (`078A`/`078B`, `take A`, o la misma línea repetida).
- Etiquetas de efecto: `[AIR]`, `[GROUND]`, `[TOWER]`, `[STRESS]`, `[CLEAN]`.
- Palabra clave del nombre: es automática (ATIS, RADIOCHECK, TAXI, TAKEOFF, CASEVAC…). Para forzarla,
  escribe `{CLAVE}` en la línea.
- Si los números se repiten entre hilos, el número del archivo lleva delante el del hilo (`02-05`).

### Fraseología automática

| Escrito | Se dice |
|---|---|
| `143.200` | one four three decimal two |
| `Angels 20` | angels two zero |
| `FL250` | flight level two five zero |
| `1500 feet` | one thousand five hundred feet |
| `squawk 4219` | squawk four two one niner |
| `Cougar11`, `Cougar 1-1`, `Talud One-One` | Cougar one one |
| `0330Z` | zero three three zero zulu |
| `BRA 090/25` | bra zero niner zero, two five |
| `Grid 37S DM 521 784` | grid three seven sierra, delta mike, five two one, seven eight four |
| `9 o'clock` | nine o'clock |

La pestaña **Pronunciación** tiene un diccionario editable (QNH → «Q N H», Mouawad → «Moo-ah-wad», …)
y un campo para probar textos.

### Efectos de radio

Se eligen solos para cada línea: primero la etiqueta del guion; si no la hay, el efecto por defecto del
hablante; si tampoco, el tipo de hablante y el tono.

- **PLAYER** suena siempre por radio de cabina: banda de unos 300–3400 Hz, compresión, ruido leve y
  clic de micrófono.
- **Pilotos, AWACS y cisternas**: radio de aeronave.
- **ATC**: radio limpia.
- **Personal en tierra**: radio de campo.
- **stressed / urgente / nervioso**: más estática, microcortes, respiración y voz algo más rápida.
- **calm / tranquilo**: radio más limpia.

Cada línea lleva una variación leve y reproducible. Hay un modo **sin efectos**. El efecto se puede
forzar por hablante o por línea.

## Construir el instalador

Lo hace GitHub Actions (`.github/workflows/build.yml`) en una máquina Windows en cada push a `main`. El
flujo:

1. Instala las dependencias.
2. Descarga los modelos.
3. Pasa las pruebas.
4. Empaqueta con PyInstaller.
5. Genera los dos guiones de ejemplo con el `.exe` y verifica los resultados.
6. Abre la ventana en modo autoprueba.
7. Crea el instalador con Inno Setup.
8. Lo instala en silencio y lo vuelve a probar.
9. Lo publica en **Releases**.

Construcción manual en Windows 10/11 (Python 3.12 e Inno Setup 6 instalados):

```bat
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements-build.txt
python build\download_models.py
python -m unittest discover -s tests -p "test_*.py"
pyinstaller build\DCSRadioVoices.spec --noconfirm --distpath dist --workpath build\work
"%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" build\installer.iss
```

El instalador queda en `dist\DCSRadioVoices-Setup-1.0.0.exe`.

Modo consola (incluido): `DCSRadioVoicesCLI.exe guion.txt carpeta_salida [--gap 2.5] [--no-fx]`.

## Licencias

Ver [`LICENSES/TERCEROS.md`](LICENSES/TERCEROS.md). Todas las voces permiten uso personal. La voz
*Ryan* (Piper) es CC BY-NC-SA, es decir, solo para uso no comercial.
