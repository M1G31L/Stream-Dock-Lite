# Cómo hacer cambios o mejoras

Stream Dock Lite **no está terminado**: funciona, pero quedan partes por probar y muchas ideas por
hacer. El código es libre (licencia [MIT](LICENSE)): **puedes modificarlo, mejorarlo y adaptarlo a tu
gusto**, para ti o para compartirlo.

## Qué falta o está sin probar

Sé consciente de esto antes de usarlo o de cambiarlo:

- **Probado con un N3E de una sola marca.** El dispositivo se vende con distintas marcas; si el tuyo
  dibuja las imágenes movidas o de otro tamaño, calíbralo (*Ajustes → Pantallas de las teclas*).
- **Las imágenes de esta documentación son ilustraciones**, generadas con el propio código de dibujo de
  la app, no capturas reales de Windows.
- **Partes que dependen de Windows** (sonidos, nivel de audio de Spotify, icono junto al reloj, fondos
  de video) se desarrollaron sin poder probarlas en todos los equipos. Si algo falla, el *Registro* de la
  app (abajo a la derecha) suele decir por qué.
- **El instalador no tiene firma digital**, por eso Windows muestra «Windows protegió tu PC».
- **El protocolo USB no es oficial**: el fabricante no lo publica. Una actualización de firmware del
  dispositivo podría cambiar algo.
- **Solo el N3E (`N3E_1B05`)**. Otros modelos usan otros códigos de teclas y tamaños de pantalla.

## Ideas pendientes

Libres para quien quiera hacerlas:

- [ ] Carpetas de teclas (una tecla abre un grupo y otra vuelve), como en Elgato.
- [ ] Doble toque en una tecla para una segunda acción.
- [ ] Letra de la canción sincronizada en una tecla.
- [ ] Próximas canciones de Spotify en las teclas, pulsar para saltar a una.
- [ ] Aviso en una tecla al recibir mensajes de Discord o WhatsApp.
- [ ] Temporizador o Pomodoro con cuenta atrás en la tecla.
- [ ] Brillo automático según la hora.
- [ ] Atajos de teclado globales para cambiar de página o perfil.
- [ ] Estadísticas de escucha (tiempo escuchado, artistas más escuchados).
- [ ] Luces RGB del PC sincronizadas con el color de la portada.
- [ ] Perfiles automáticos según la app abierta (juegos, OBS, Discord).
- [ ] Integración con OBS y Discord (escenas, silenciar micrófono).
- [ ] Soporte para otros modelos de Stream Dock.
- [ ] Traducción de la interfaz a otros idiomas.

## Cómo empezar

1. **Descarga el código:** botón verde **Code → Download ZIP**, o con git:
   ```
   git clone <url de este repositorio>
   ```
   Si tienes cuenta de GitHub, pulsa **Fork** para tener tu propia copia en la que guardar tus cambios.
2. **Instala Python 3.11 o más reciente** (python.org) en Windows.
3. **Instala las dependencias y abre la app desde el código:**
   ```
   py -3.12 -m pip install -r StreamDockLite/requirements.txt
   py -3.12 StreamDockLite/app.py
   ```
   Cierra antes el software oficial Stream Dock y la versión instalada de Stream Dock Lite.
4. **Haz tus cambios** y vuelve a abrir la app para probarlos.

## Dónde está cada cosa

| Quiero cambiar… | Archivo |
|---|---|
| La ventana, el inspector, los menús, los ajustes | `StreamDockLite/app.py` |
| Cómo se dibujan las teclas (iconos, estilos, animaciones) | `StreamDockLite/render.py` |
| Los efectos al pulsar o con la música | `StreamDockLite/reactions.py` |
| Los sonidos | `StreamDockLite/sounds.py` (o deja tus `.wav` en la carpeta de sonidos) |
| La comunicación USB con el N3E (imágenes, botones, perillas) | `StreamDockLite/dock.py` |
| Spotify (portada, controles, volumen, API web) | `StreamDockLite/spotify.py`, `playlists.py` |
| Las acciones del sistema (abrir apps, atajos, texto) | `StreamDockLite/actions.py` |
| Temas y colores | `StreamDockLite/theme.py` |
| Fondos de la ventana | `StreamDockLite/background.py` |
| Las actualizaciones y copias de seguridad | `StreamDockLite/updater.py` |
| El instalador `.exe` | `installer/` (en Go) |

**Ejemplo: añadir una acción nueva.** En `app.py`, añade una línea al diccionario `TYPES` (aparecerá en
la lista de acciones de la derecha) y escribe lo que hace en `run_action()` de `actions.py`
(o en `run()` de `app.py` si necesita la ventana de la app). Para darle un icono propio, añádelo en
`STATIC_GLYPH` de `render.py`.

## Publicar tus cambios

- **Para ti:** compila tu propio instalador con `./installer/build.sh` (ver el README) o usa la app
  desde el código.
- **Para todos:** si hiciste un *fork*, abre un **Pull request** hacia este repositorio explicando qué
  cambia y cómo lo probaste. Incluye una captura si cambia algo visible.
- **Si encuentras un fallo** pero no sabes arreglarlo, abre un **Issue** con lo que pasó, lo que
  esperabas y el último mensaje del *Registro* de la app.

Al proponer cambios, mantén la app en español y no incluyas datos personales (nombres, rutas de tu
usuario, capturas de tu escritorio) en el código ni en las imágenes.
