# Stream Dock Lite — N3E_1B05 + Spotify

Controlador al estilo de Elgato Stream Deck, hecho solo para el
**Stream Dock N3E (N3E_1B05)**: 6 teclas con pantalla, 3 botones y 3 perillas.

## Instalación (Windows 10/11)

1. Doble clic en **StreamDockLite-Setup.exe**. No necesitas tener Python: el instalador lo trae.
   - Si Windows muestra «Windows protegió tu PC»: *Más información* → *Ejecutar de todas formas*
     (sale porque el instalador no está firmado digitalmente).
   - No pide permisos de administrador. Se instala en `%LOCALAPPDATA%\Programs\StreamDockLite`.
   - Necesita internet solo durante la instalación (descarga los componentes de USB y Spotify).
   - Crea accesos en el **Escritorio** y el **menú Inicio** (también «Diagnóstico del N3E»).
2. **Cierra por completo el software oficial Stream Dock** (también el icono junto al reloj).
3. Abre **Stream Dock Lite**.

Al cerrar la ventana, la app sigue funcionando **junto al reloj** (icono en la bandeja):
doble clic para abrirla, clic derecho para play/pausa, cambiar canción o salir.

Para desinstalar: *Configuración de Windows → Aplicaciones instaladas → Stream Dock Lite*.

## Actualizaciones y conexión con Claude

- Botón **🔗 Claude** (arriba): actívalo o desactívalo cuando quieras.
  Al activarlo se crea la carpeta de conexión `%LOCALAPPDATA%\StreamDockLite\entrada_claude`.
- Para que Claude pueda dejar actualizaciones ahí, dale acceso a **esa carpeta** en la app de
  escritorio de Claude: botón **+** junto al cuadro de mensaje → **Add folder**.
- Cada actualización que llega muestra versión y notas, y **solo se instala si pulsas «Sí»**.
- Antes de instalar se guarda una copia. **Ajustes → Volver a la versión anterior** la restaura.
- También puedes instalar un .zip a mano: **Ajustes → Actualizar desde archivo…**

## Cómo se usa

- **Biblioteca de acciones** (derecha): arrastra una acción a una tecla, botón o
  perilla. Doble clic = asignarla al control seleccionado.
- **Inspector** (abajo): título, posición del título, colores, icono propio,
  acción al pulsar y al mantener.
- Arrastra una tecla sobre otra para **intercambiarlas**. Clic derecho: copiar,
  pegar, vaciar.
- **Páginas**: cambia de página desde arriba o con la acción «Cambiar de página».

## Apariencia (botón 🎨 arriba)

- **Tema:** oscuro, claro o como Windows · **Color de acento** (azul, verde, morado, rosa…).
  Estos dos se aplican reiniciando la app (un botón lo hace por ti).
- **Fondo:** ninguno · **portada de la canción** (cambia sola con cada tema, con fundido) ·
  **imagen** · **video o GIF** (MP4, MOV, WEBM, MKV, AVI o GIF animado).
- **Efectos:** desenfoque, velo (oscurece en tema oscuro, aclara en el claro), saturación,
  viñeta y movimiento lento. Se ven al momento.
- El fondo se pausa cuando la ventana está oculta junto al reloj, para no gastar procesador.

## Reacción de las teclas y botones

Selecciona una tecla o un botón y, en el inspector, sección **Reacción**:
- **Al pulsar:** onda, destello, hundir, borde de color o chispas (en el N3E y en la vista previa).
- **Sonido:** clic, pop, tic, suave, teclado mecánico o burbuja. Puedes añadir tus propios `.wav`
  en **Carpeta de sonidos**. Los botones sin pantalla también pueden sonar.
- **Con la música:** la tecla reacciona al sonido real de Spotify: latido, borde que brilla,
  barra de nivel o destello en cada golpe.
- **Aplicar a todas** copia la reacción a todas las teclas y botones.
- La tecla de portada («Ahora suena») no lleva efectos de reacción.

## Iconos

- En el inspector de una tecla: **🖼 Iconos…** abre la biblioteca; clic en un icono para ponerlo.
- **Importar iconos / .zip / .rar…**: añade tus iconos (un .rar se abre con el `tar` de
  Windows 11; si falla, descomprímelo y usa **Importar carpeta…**).
- También puedes copiar imágenes a la carpeta `iconos` junto a la app; aparecen solas.

## Spotify

Funciona con la **app de escritorio de Spotify**, sin iniciar sesión:

| Acción | Qué hace |
|---|---|
| Ahora suena | La portada de la canción, con el estilo que elijas; pulsar = play/pausa |
| Play / Pausa | El icono cambia según el estado |
| Siguiente / Anterior | Cambia de canción |
| Aleatorio / Repetir | Se ilumina en verde cuando está activo |
| Progreso | Tiempo y barra de la canción |
| Volumen de Spotify | Sube/baja/silencia **solo Spotify**, no el resto del PC |
| Me gusta | Guarda la canción (necesita conectar la cuenta, ver abajo) |

### Estilos de «Ahora suena»

Selecciona la tecla y, en el inspector, usa **✨ Ver estilos…** (vista previa animada) o los menús:

- **Estilo:** solo portada · título deslizante · barra de progreso · ecualizador animado ·
  disco de vinilo girando · portada que late · paneo lento.
- **Al pausar:** no cambiar · atenuar · blanco y negro · icono de pausa · detener animación.
- **Al cambiar canción:** ninguna · fundido · deslizar · acercar.
- **Recorte:** automático (quita la franja con el logo de Spotify) · manual (% de abajo) · no recortar.

### Teclas de playlists

Arrastra **Playlist / álbum** a una tecla y pega el enlace (en Spotify: *Compartir → Copiar enlace*).
La tecla muestra la portada de la playlist. Al pulsarla, empieza a sonar si conectaste tu cuenta
(Ajustes → Spotify); si no, se abre en Spotify lista para reproducir.

### Protector de pantalla

*Ajustes → Protector de pantalla*: tras unos minutos sin tocar el N3E muestra la **portada gigante
repartida en las 6 teclas**, baja el brillo o apaga las pantallas. Cualquier toque lo despierta.

Perillas por defecto: 1 = volumen de Spotify, 2 = cambiar canción, 3 = volumen del PC.

### «Me gusta» (opcional)

Spotify solo permite guardar canciones mediante su API:

1. Entra a developer.spotify.com/dashboard → *Create app*.
2. Redirect URI: `http://127.0.0.1:8754/callback` · marca *Web API*.
3. Copia el *Client ID* → en la app: **Ajustes → Conectar cuenta**.

Según las reglas de Spotify de 2026, el dueño de esa app debe tener Premium.

## Si ves un fondo o la imagen descentrada

*Ajustes → Pantallas de las teclas* → **Ver patrón**, y mirando el N3E:
- **− / +**: tamaño de 1 en 1 hasta que el marco blanco llegue a los bordes.
- **◀ ▲ ▼ ▶**: mueve la imagen hasta que quede centrada (**●** vuelve al centro).
- **Giro**: si la flecha amarilla no apunta hacia arriba.
- **Borrar el fondo que dejó el software oficial** (activado por defecto).

## Si no detecta el N3E

- Abre **Diagnóstico del N3E** (menú Inicio): dibuja los números 1–6 en las teclas y muestra lo
  que llega al pulsar. Deja un `informe_deteccion.txt`.
- Si las imágenes salen giradas o en blanco: **Ajustes → Protocolo** 3 o 2.

La configuración se guarda en `%APPDATA%\StreamDockLite\`.
