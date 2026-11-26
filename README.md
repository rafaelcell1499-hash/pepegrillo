# ReelForge 2.1

Programa de Windows con interfaz grafica que crea **reels verticales (9:16)** a partir de uno o varios
videos y una cancion. Analiza la musica (BPM, beats, energia, drops) y monta el edit automaticamente:
cortes en los beats, **curvas de velocidad**, zooms con punch, shake, glitch RGB, transiciones de camara,
transiciones suaves, **fuego**, light leaks, efectos tipo arte, looks de color y **texto opcional**.

## Como obtener el .exe (GitHub Actions)

1. Crea un repositorio en GitHub y sube **todo el contenido de esta carpeta**
   (incluida la carpeta oculta `.github`).
2. Ve a la pestana **Actions**. El workflow *Compilar ReelForge (Windows)* se ejecuta solo con cada push
   (o pulsa *Run workflow*).
3. Al terminar (5-10 min), entra en la ejecucion y descarga el artefacto **ReelForge-Windows**.
4. Descomprime el zip y abre `ReelForge\ReelForge.exe`. No hay que instalar nada: FFmpeg va incluido.

Para publicar una release descargable: crea un tag, por ejemplo `v2.0.0`, y el .zip se adjunta solo.

### Compilar en tu PC (opcional)
Instala Python 3.10+ y pon `ffmpeg.exe` y `ffprobe.exe` en la carpeta `bin\`. Ejecuta `build.bat`.
Para probar sin compilar: `run_desde_codigo.bat`.

## Uso

1. **Anade videos** (o imagenes). Cuantos mas, mas variedad. Un solo video largo tambien funciona.
2. **Elige el audio**. Pulsa *Analizar audio* si quieres ver BPM, beats y drops.
3. Elige un **estilo** (pestana *Estilo y ritmo*) y ajusta lo que quieras.
4. *Vista previa rapida* renderiza 6 s en baja resolucion. Si te gusta, *GENERAR REEL*.

Cada generacion usa una **semilla** distinta (se muestra en el registro). Repite la misma semilla para
obtener exactamente el mismo edit, o dejala en 0 para variaciones infinitas con los mismos ajustes.

## Que hace cada parte

| Funcion | Detalle |
|---|---|
| Sincronia con la musica | Deteccion de beats por flujo espectral + programacion dinamica; cortes a fotograma exacto, sin desfase acumulado |
| Cortes inteligentes | Segun la energia: 4 / 2 / 1 / 1/2 beats; mas rapidos tras un drop |
| Curvas de velocidad | Build (lento a rapido), impacto (rapido a lento), hero (lento-rapido-lento), bullet-time, pulso |
| Camara | Zoom punch, push lento, shake, roll, aberracion cromatica, destellos |
| Efectos extra | Estela (ghost trails), zoom blur, pixelado, glitch por franjas, strobe, pulso de color, espejo y caleidoscopio |
| Transiciones de camara | Zoom-through, whip pan, giro (roll), glitch, flash, pixelado, slice, zoom blur, strobe: el final de un clip y el inicio del siguiente se enlazan |
| Transiciones suaves | Mas de 50 de FFmpeg (fundidos, wipes, slides, circulos, radial, pixelize, cortes en franjas...) en zonas tranquilas |
| Bordeado neon | Contorno luminoso con glow que sigue los bordes marcados de la zona central y pulsa con cada golpe (color fijo o ciclico) |
| Overlays procedurales | Fuego, chispas/brasas, humo, lens flare, reflejos que barren la imagen, bokeh, light leaks, polvo de pelicula, lluvia; hasta 2 por corte y "puentes" de fuego/humo/luz entre cortes |
| Arte | Comic, boceto a tinta, posterizado, duotono, termico, glow, negativo, espejo, caleidoscopio |
| Looks | 16: Cine, Noir, Neon, Anime, VHS, Dorado, Helado, Glow, Comic, Boceto, Vintage 35mm, Matrix, Atardecer, Infrarrojo, Pastel... |
| Texto | Titulo inicial animado y palabras por corte al ritmo (opcional) |
| Overlays propios | Mete videos sobre fondo negro en `overlays\` y se mezclan en *screen* |

> **Sobre el bordeado:** no es un recorte con IA (no separa persona/fondo pixel a pixel). Detecta los contornos
> mas marcados y da prioridad a la zona central, asi que funciona mejor con sujetos bien contrastados.

## Consejos

* **Clips de 5-30 s con movimiento** dan mejores resultados que planos estaticos.
* Para un look "Phonk": estilo *Phonk / Agresivo*, audio con bajo fuerte, look Noir.
* Para algo elegante: estilo *Cinematico suave* + *Interpolacion* en camara lenta.
* Si tienes GPU NVIDIA, elige *NVIDIA (NVENC)* en *Salida*: el render final es mucho mas rapido.
* La camara lenta *Interpolacion* es muy lenta; *Blend* es un buen compromiso.

## Problemas frecuentes

* **Windows SmartScreen / antivirus avisa**: es habitual en programas empaquetados con PyInstaller sin firma.
  Pulsa *Mas informacion > Ejecutar de todas formas*.
* **El texto no aparece**: necesita una fuente; se usa Impact/Arial de Windows. Puedes elegir un `.ttf` propio.
* **Un segmento falla con efectos**: ReelForge lo reintenta automaticamente en modo simple y lo avisa en el registro.
* Si el programa no abre, se crea `reelforge_error.log` junto al `.exe`.

## Estructura

```
main.py                  punto de entrada (GUI y --selftest)
reelforge/
  gui.py                 interfaz (customtkinter)
  engine.py              orquestacion del render
  planner.py             decisiones: cortes, curvas, efectos, transiciones
  fx.py                  constructor de filtros FFmpeg
  audio.py               analisis musical (NumPy)
  overlays.py            fuego, humo, chispas, flares, reflejos... (procedurales)
  config.py              ajustes y presets
.github/workflows/build.yml   compilacion automatica en Windows
```

## Licencias
FFmpeg se distribuye aqui en su build GPL de BtbN (https://github.com/BtbN/FFmpeg-Builds). Respeta los
derechos de la musica y los videos que uses.
