
import math                          
import sys                          
import time                          
from collections import deque        # lista doble eficiente para la ventana de muestras

import pygame                        


# Aqui esta la configuracion general de programa

PUERTO = None             # none opara autodetectar el arduino
BAUDIOS = 9600            
ANCHO, ALTO = 1200, 800   
MAX_DISTANCE_CM = 140     # alcance maximo que se muestra en cm. Conviene que coincida con el
                          # alcance real del sensor: el firmware usa TIMEOUT_US igual a 8000,
                          # que da unos 137 cm. Mostrar mas dibujaria anillos sin datos.

# Parametros que se usan para trackear las cosas
GATE_CM   = 45.0          # una deteccion a menos de esta distancia (cm) de un objeto se toma como el mismo objeto
MAX_TRACK_CM_S = 14.0     # ensancha el gate segun el tiempo sin ver al objeto, para casarlo entre pasadas
EXPIRY_S  = 20.0          # un objeto se borra si no se vuelve a ver en este tiempo (segundos)
GAP_AVIST_S = 0.6         # hueco de tiempo que separa un avistamiento del siguiente.
VEL_WIN_S = 20.0          # ventana en segundos de avistamientos para estimar velocidad y aceleracion
MIN_VEL_CM_S = 1.5        # por debajo de esto no se dibuja parabola, el objeto se considera quieto
MAX_ACC_CM_S2 = 60.0      # tope de aceleracion (cm por segundo al cuadrado) para que la parabola no se dispare

# Parametros de la prediccion.
PRED_S    = 1.0           # cuantos segundos hacia el futuro se dibuja la parabola
PRED_PASOS = 24           # en cuantos pedacitos se parte la curva predicha (mas pasos, mas suave)


VERDE = (98, 245, 31)        # verde del radar
VERDE_LINEA = (30, 250, 60)  # verde de la linea de barrido
NEGRO = (0, 0, 0)            # fondo
BLANCO = (255, 255, 255)    

# Paleta para distinguir objetos. Cuando se acaban los colores se vuelve a empezar.
PALETA = [
    (255, 80, 80), (80, 180, 255), (255, 210, 60),
    (200, 100, 255), (60, 255, 180), (255, 140, 40),
]


# Conexion serial con el Arduino

puerto_serial = None      # aqui se va a guardar el objeto del puerto una vez abierto
buffer_serial = ""        # texto que va llegando y todavia no se ha terminado de procesar

import serial                       # libreria pyserial para hablar con el Arduino
import serial.tools.list_ports      # parte de pyserial que lista los puertos disponibles


def detectar_puerto():
    # Busca automaticamente cual de los puertos del sistema es el Arduino.
    puertos = list(serial.tools.list_ports.comports())   # todos los puertos serie del sistema
    claves = ("arduino", "ch340", "cp210", "ftdi", "usb serial", "wch", "acm")  # nombres tipicos de chips Arduino
    for p in puertos:                                    # revisa puerto por puerto
        texto = f"{p.description} {p.manufacturer} {p.device}".lower()   # junta sus datos en minusculas
        if (p.vid == 0x2341) or any(k in texto for k in claves):  # 0x2341 es el id de fabricante de Arduino
            return p.device                              # si coincide, devuelve la ruta de ese puerto
    if puertos:                                          # si no hubo coincidencia pero hay puertos
        return puertos[0].device                         # devuelve el primero como ultimo recurso
    return None                                          # si no hay ningun puerto, devuelve None


puerto = PUERTO or detectar_puerto()   # usa el puerto fijado a mano, o si no lo autodetecta
if puerto is None:                     # si no se encontro ningun puerto
    print("No se encontro puerto serial. Conecta el Arduino.")  # avisa
    sys.exit(1)                        # y cierra el programa
try:
    puerto_serial = serial.Serial(puerto, BAUDIOS, timeout=0)   # abre el puerto sin bloquear la lectura
    print(f"Conectado a {puerto} a {BAUDIOS} baudios.")         # confirma la conexion
except serial.SerialException:         # si el puerto existe pero no se pudo abrir
    print(f"No se pudo abrir {puerto}. Cierra el Serial Monitor del IDE si esta abierto.")
    sys.exit(1)                        # y cierra el programa


# Arranque de pygame y geometria del radar

pygame.init()                                            # inicializa pygame
pantalla = pygame.display.set_mode((ANCHO, ALTO))        # crea la ventana del tamano definido
pygame.display.set_caption("Radar seguimiento de varios objetos")  # titulo de la ventana
fuente_chica = pygame.font.SysFont("monospace", 20)               # fuente para textos chicos
fuente_media = pygame.font.SysFont("monospace", 24, bold=True)    # fuente mediana
fuente_grande = pygame.font.SysFont("monospace", 34, bold=True)   # fuente para titulos
reloj = pygame.time.Clock()                              # reloj para limitar los cuadros por segundo

fade = pygame.Surface((ANCHO, ALTO))   # capa negra semitransparente que se pinta encima cada cuadro
fade.set_alpha(8)                      # transparencia muy baja: deja una estela tenue de lo anterior
fade.fill(NEGRO)                       # esa capa es de color negro

CX = ANCHO // 2                        # coordenada x del centro del radar (mitad del ancho)
CY = int(ALTO - ALTO * 0.074)          # coordenada y del centro, casi al fondo de la ventana
R_OUTER = (ANCHO - ANCHO * 0.0625) / 2 # radio del arco mas grande del radar en pixeles
ESCALA = R_OUTER / MAX_DISTANCE_CM     # cuantos pixeles equivalen a un centimetro


def polar_a_cm(ang_grados, dist_cm):
    """Convierte la lectura del radar (angulo y distancia) a coordenadas del mundo
    en cm, con la y hacia arriba. Aqui se aplica x igual a r por coseno y y igual a
    r por seno, la conversion de polar a cartesiana que pide el enunciado."""
    rad = math.radians(ang_grados)     # pasa el angulo de grados a radianes
    return (dist_cm * math.cos(rad), dist_cm * math.sin(rad))   # devuelve (x, y) en cm


def cm_a_pantalla(x_cm, y_cm):
    """Pasa una posicion del mundo en cm a pixeles de la pantalla, tomando el centro
    del radar como origen. La y se invierte porque en pantalla crece hacia abajo."""
    return (int(CX + x_cm * ESCALA), int(CY - y_cm * ESCALA))


def punto_polar(ang_grados, radio_px):
    """Dado un angulo y un radio ya en pixeles, devuelve el punto en pantalla.
    Sirve para dibujar las cosas del radar (lineas, marcas) sin pasar por cm."""
    rad = math.radians(ang_grados)     # angulo a radianes
    return (int(CX + radio_px * math.cos(rad)), int(CY - radio_px * math.sin(rad)))


# Clase que representa cada objeto que el radar sigue

class Objeto:
    _contador = 0                      # contador compartido por todos los objetos, para dar ids unicos

    def __init__(self, x_cm, y_cm, t):
        Objeto._contador += 1          # sube el contador con cada objeto nuevo
        self.id = Objeto._contador     # id propio de este objeto
        self.color = PALETA[(self.id - 1) % len(PALETA)]   # le toca un color de la paleta ciclando
        self.muestras = deque()        # centroides ya cerrados (cx, cy, t), la ventana que rueda
        self._bin = []                 # detecciones del avistamiento en curso (x, y, t)
        self.px, self.py = x_cm, y_cm  # posicion que se muestra en pantalla (centroide del avistamiento)
        self.ultimo = t                # instante de la ultima deteccion vista
        self.vel = (0.0, 0.0)          # velocidad en cm por segundo (componentes x, y)
        self.acel = (0.0, 0.0)         # aceleracion en cm por segundo al cuadrado
        self.agregar_deteccion(x_cm, y_cm, t)   # mete ya la primera deteccion

    def rapidez(self):                 # magnitud de la velocidad (el modulo del vector)
        return math.hypot(*self.vel)   # raiz de vx al cuadrado mas vy al cuadrado

    def _cerrar_bin(self):
        """Junta todas las detecciones del avistamiento en curso en un solo
        centroide, lo mete en la ventana que rueda y ahi recien mueve (salta) el
        punto que se muestra. El punto no se desliza con el barrido: se queda fijo
        hasta el proximo avistamiento."""
        if not self._bin:              # si no hay nada acumulado, no hace nada
            return
        n = len(self._bin)             # cuantas detecciones tiene el avistamiento
        cx = sum(p[0] for p in self._bin) / n   # promedio de las x (centroide en x)
        cy = sum(p[1] for p in self._bin) / n   # promedio de las y (centroide en y)
        ct = sum(p[2] for p in self._bin) / n   # promedio de los tiempos (instante medio)
        self.muestras.append((cx, cy, ct))      # guarda ese centroide en la ventana
        self._bin = []                          # vacia el avistamiento para empezar otro
        self.px, self.py = cx, cy               # el punto mostrado salta a esa posicion, una vez por avistamiento
        while len(self.muestras) > 2 and ct - self.muestras[0][2] > VEL_WIN_S:  # bota lo mas viejo
            self.muestras.popleft()             # mantiene la ventana dentro de VEL_WIN_S segundos

    def agregar_deteccion(self, x_cm, y_cm, t):
        """Agrega una deteccion al objeto. Si hubo un hueco de tiempo mayor a
        GAP_AVIST_S desde la ultima, se trata de un avistamiento nuevo: cierra el
        anterior (lo que mueve el punto) y abre otro. Durante el avistamiento el
        punto mostrado queda fijo, no se arrastra con el barrido del servo."""
        if self._bin and t - self.ultimo > GAP_AVIST_S:  # si paso un hueco, el avistamiento de antes termino
            self._cerrar_bin()                            # lo cierra y fija su centroide
        self._bin.append((x_cm, y_cm, t))                 # acumula esta deteccion en el avistamiento actual
        self.ultimo = t                                   # actualiza el instante de la ultima vista
        self._estimar_movimiento()                        # recalcula velocidad y aceleracion

    def cerrar_si_inactivo(self, t):
        """Si el haz ya dejo atras al objeto (paso un hueco sin detecciones mayor a
        GAP_AVIST_S), cierra el avistamiento en curso para fijar su centroide cuanto
        antes, sin tener que esperar a que llegue el proximo avistamiento."""
        if self._bin and t - self.ultimo > GAP_AVIST_S:
            self._cerrar_bin()

    def referencia(self, t):
        """Posicion que se usa para decidir si una deteccion nueva es de este objeto.
        Predice desde la posicion actual usando la velocidad, asi lo casa aunque se
        haya movido entre una vista y la otra."""
        dt = t - self.ultimo                              # tiempo transcurrido desde la ultima vista
        return (self.px + self.vel[0] * dt, self.py + self.vel[1] * dt)  # posicion estimada ahora

    def _puntos(self):
        """Devuelve los centroides de la ventana mas el centroide del avistamiento
        que esta en curso (el mas reciente), para tener la serie de posiciones."""
        pts = list(self.muestras)      # copia de los centroides ya cerrados
        if self._bin:                  # si hay un avistamiento abierto
            n = len(self._bin)         # cantidad de detecciones en el
            pts.append((sum(p[0] for p in self._bin) / n,   # agrega su centroide en x
                        sum(p[1] for p in self._bin) / n,   # su centroide en y
                        sum(p[2] for p in self._bin) / n))  # y su instante medio
        return pts

    def _estimar_movimiento(self):
        """Calcula la velocidad actual como el delta entre el avistamiento anterior
        y el actual (velocidad igual a distancia sobre tiempo, como pide el
        enunciado). La aceleracion compara esa velocidad con la del par de
        avistamientos previo."""
        pts = self._puntos()           # serie de posiciones con tiempo
        if len(pts) < 2:               # con menos de dos posiciones no hay velocidad
            self.vel = (0.0, 0.0)
            self.acel = (0.0, 0.0)
            return
        x1, y1, t1 = pts[-2]           # avistamiento anterior (posicion y tiempo)
        x2, y2, t2 = pts[-1]           # avistamiento actual
        dt = t2 - t1                   # tiempo entre los dos
        if dt <= 1e-6:                 # si el tiempo es casi cero, evita dividir entre cero
            return
        self.vel = ((x2 - x1) / dt, (y2 - y1) / dt)   # velocidad igual al cambio de posicion sobre el tiempo

        if len(pts) >= 3:              # para aceleracion hacen falta al menos tres posiciones
            x0, y0, t0 = pts[-3]       # el avistamiento de antes del anterior
            dta = t1 - t0              # tiempo entre ese y el anterior
            if dta > 1e-6:             # de nuevo evita dividir entre cero
                v_prev = ((x1 - x0) / dta, (y1 - y0) / dta)   # velocidad de ese par previo
                dtv = (dt + dta) / 2   # tiempo medio entre las dos velocidades
                ax = max(-MAX_ACC_CM_S2, min(MAX_ACC_CM_S2, (self.vel[0] - v_prev[0]) / dtv))  # acel en x, recortada al tope
                ay = max(-MAX_ACC_CM_S2, min(MAX_ACC_CM_S2, (self.vel[1] - v_prev[1]) / dtv))  # acel en y, recortada al tope
                self.acel = (ax, ay)
            else:
                self.acel = (0.0, 0.0)
        else:
            self.acel = (0.0, 0.0)     # sin tres posiciones, la aceleracion se deja en cero

    def predecir(self, dt):
        """Devuelve la posicion futura en cm dentro de dt segundos, con la formula
        de cinematica: posicion mas velocidad por tiempo mas un medio de la
        aceleracion por el tiempo al cuadrado. Esa es la parabola."""
        vx, vy = self.vel              # componentes de velocidad
        ax, ay = self.acel             # componentes de aceleracion
        px = self.px + vx * dt + 0.5 * ax * dt * dt   # x futura
        py = self.py + vy * dt + 0.5 * ay * dt * dt   # y futura
        return (px, py)


objetos = []   # lista con todos los objetos que el radar esta siguiendo en este momento


def registrar(ang, dist):
    """Toma una deteccion (angulo, distancia), la asocia al objeto mas cercano que
    este dentro del gate, o crea un objeto nuevo si ninguno cuadra."""
    x, y, ahora = *polar_a_cm(ang, dist), time.time()   # pasa a cm y guarda el instante actual
    mejor, mejor_d = None, None         # mejor candidato encontrado y su distancia
    for o in objetos:                   # revisa cada objeto existente
        rx, ry = o.referencia(ahora)    # posicion estimada del objeto en este instante
        d = math.hypot(x - rx, y - ry)  # distancia entre la deteccion y esa estimacion
        # El gate es adaptativo: se ensancha segun el tiempo que lleva sin verse el
        # objeto, asi una deteccion de la pasada siguiente todavia cuadra con su
        # track aunque se haya movido. Esto es clave antes de tener buena velocidad.
        gate = GATE_CM + MAX_TRACK_CM_S * min(ahora - o.ultimo, EXPIRY_S)
        if d < gate and (mejor_d is None or d < mejor_d):  # si entra al gate y es el mas cercano hasta ahora
            mejor, mejor_d = o, d        # se queda como mejor candidato
    if mejor is not None:                # si hubo un objeto que cuadra
        mejor.agregar_deteccion(x, y, ahora)   # le suma la deteccion
    else:                                # si ninguno cuadro
        objetos.append(Objeto(x, y, ahora))    # crea un objeto nuevo


def cerrar_inactivos():
    """Fija el centroide de los avistamientos cuyo haz ya paso, sin esperar al
    proximo avistamiento, para que el punto salte a su posicion y quede fijo."""
    t = time.time()                     # instante actual
    for o in objetos:                   # para cada objeto
        o.cerrar_si_inactivo(t)         # cierra su avistamiento si ya esta inactivo


def caducar():
    """Borra los objetos que no se han vuelto a ver en EXPIRY_S segundos."""
    ahora = time.time()                 # instante actual
    objetos[:] = [o for o in objetos if ahora - o.ultimo < EXPIRY_S]  # deja solo los vistos hace poco


# Lectura del puerto serial

angulo = 90      # ultimo angulo recibido del Arduino (arranca en 90, mirando al frente)
distancia = 0    # ultima distancia recibida en cm


def leer_serial():
    """Lee lo que mando el Arduino, arma los paquetes de la forma angulo,distancia.
    y registra cada deteccion valida."""
    global angulo, distancia, buffer_serial   # estas variables se modifican aqui adentro
    try:
        datos = puerto_serial.read(64).decode("utf-8", errors="ignore")  # lee hasta 64 bytes y los pasa a texto
    except serial.SerialException:      # si el puerto fallo (por ejemplo se desconecto)
        return                          # simplemente no hace nada este cuadro
    buffer_serial += datos              # pega lo nuevo a lo que quedaba pendiente
    while "." in buffer_serial:         # mientras haya un paquete completo (terminado en punto)
        paquete, buffer_serial = buffer_serial.split(".", 1)  # separa el primer paquete del resto
        if "," in paquete:              # un paquete valido lleva una coma entre angulo y distancia
            partes = paquete.split(",") # parte el texto en angulo y distancia
            try:
                angulo = int(partes[0]) # convierte el angulo a entero
                distancia = int(partes[1])   # convierte la distancia a entero
            except (ValueError, IndexError):  # si vino basura o incompleto
                continue                # ignora ese paquete y sigue con el siguiente
            if 2 <= distancia < MAX_DISTANCE_CM:   # solo si la distancia esta en rango util
                registrar(angulo, distancia)       # registra la deteccion


# Funciones de dibujo

def dibujar_radar(surf):
    """Dibuja la parte fija del radar: los arcos concentricos y las lineas guia."""
    for f in (1.0, 0.75, 0.5, 0.25):    # cuatro arcos a distintas fracciones del radio
        r = R_OUTER * f                 # radio de este arco
        rect = pygame.Rect(CX - r, CY - r, r * 2, r * 2)   # caja que envuelve al circulo
        pygame.draw.arc(surf, VERDE, rect, 0, math.pi, 2)  # dibuja medio circulo (de 0 a pi radianes)
    pygame.draw.line(surf, VERDE, (0, CY), (ANCHO, CY), 2) # linea horizontal de la base
    for ang in [30, 60, 90, 120, 150]:  # lineas radiales como guia de angulos
        pygame.draw.line(surf, VERDE, (CX, CY), punto_polar(ang, ANCHO / 2), 2)


def dibujar_barrido(surf):
    """Dibuja la linea verde que gira con el servo (el haz del radar)."""
    largo = ALTO - ALTO * 0.12          # largo de la linea de barrido
    pygame.draw.line(surf, VERDE_LINEA, (CX, CY), punto_polar(angulo, largo), 9)  # va del centro hacia el angulo actual


def dibujar_objetos(surf):
    """Dibuja cada objeto: su prediccion futura, su punto y su etiqueta."""
    ahora = time.time()                 # instante actual, para el desvanecido
    for o in objetos:                   # recorre todos los objetos
        px, py = cm_a_pantalla(o.px, o.py)   # pasa la posicion del objeto a pixeles

        # Posicion futura. Si el objeto se mueve, dibuja la parabola hasta un
        # marcador final. Si esta casi quieto, el futuro es la misma posicion
        # actual, asi que solo se pone un marcador en el sitio.
        if o.rapidez() >= MIN_VEL_CM_S:   # si se mueve mas que el minimo
            pts = [(px, py)]            # la curva arranca en el objeto
            for i in range(1, PRED_PASOS + 1):   # va calculando puntos hacia el futuro
                t = PRED_S * i / PRED_PASOS      # fraccion de tiempo de este paso
                fx, fy = o.predecir(t)           # posicion predicha en ese instante
                if fy < 0:              # si la prediccion baja por debajo de la base del radar, corta ahi
                    break
                r = math.hypot(fx, fy)           # distancia de ese punto al centro
                if r > MAX_DISTANCE_CM:          # si se pasa del borde del radar
                    fx, fy = fx * MAX_DISTANCE_CM / r, fy * MAX_DISTANCE_CM / r  # lo pega justo al borde
                    pts.append(cm_a_pantalla(fx, fy))   # agrega ese ultimo punto sobre el anillo
                    break              # y termina la parabola ahi, sin salirse del radar
                pts.append(cm_a_pantalla(fx, fy))   # agrega el punto en pixeles
            if len(pts) >= 2:          # solo dibuja si hay al menos dos puntos
                pygame.draw.lines(surf, o.color, False, pts, 2)   # une todos los puntos de la parabola
                pygame.draw.circle(surf, o.color, pts[-1], 7, 2)  # marcador hueco al final de la prediccion
        else:                           # si esta quieto
            pygame.draw.circle(surf, o.color, (px, py), 14, 1)  # anillo hueco en el punto (futuro igual a presente)

        # Punto solido del objeto. Se hace mas tenue a medida que se acerca a caducar.
        edad = ahora - o.ultimo         # cuanto hace que no se ve
        alpha = 255 if edad < EXPIRY_S * 0.6 else int(255 * (1 - edad / EXPIRY_S) / 0.4)  # opacidad segun la edad
        alpha = max(40, min(255, alpha))   # la mantiene entre 40 y 255
        s = pygame.Surface((20, 20), pygame.SRCALPHA)   # superficie chica con canal de transparencia
        pygame.draw.circle(s, (*o.color, alpha), (10, 10), 9)   # dibuja el circulo del objeto con esa opacidad
        surf.blit(s, (px - 10, py - 10))   # lo pega centrado en la posicion del objeto

        # Etiqueta con el id del objeto y su rapidez en metros por segundo.
        etiqueta = f"#{o.id}  {o.rapidez() / 100:.2f} m/s"   # divide entre 100 para pasar de cm/s a m/s
        surf.blit(fuente_chica.render(etiqueta, True, o.color), (px + 12, py - 10))  # la dibuja al lado del punto


def dibujar_texto(surf):
    """Dibuja la franja de informacion de abajo y las marcas de distancia y angulo."""
    pygame.draw.rect(surf, NEGRO, (0, int(ALTO - ALTO * 0.0648), ANCHO, ALTO))  # tapa la parte de abajo con negro
    for frac in (0.25, 0.5, 0.75, 1.0):    # cuatro marcas de distancia
        valor = int(MAX_DISTANCE_CM * frac)   # cuantos cm representa cada anillo
        img = fuente_chica.render(f"{valor}cm", True, VERDE)   # texto con ese valor
        surf.blit(img, (CX + R_OUTER * frac - 30, ALTO - ALTO * 0.0833))  # lo ubica sobre el anillo

    y = int(ALTO - ALTO * 0.045)           # altura de la linea de textos grandes
    surf.blit(fuente_grande.render("Radar seguimiento", True, VERDE), (20, y))           # titulo
    surf.blit(fuente_grande.render(f"Angulo: {angulo}", True, VERDE), (int(ANCHO * 0.52), y))    # angulo actual
    surf.blit(fuente_grande.render(f"Objetos: {len(objetos)}", True, VERDE), (int(ANCHO * 0.78), y))  # cantidad de objetos

    for ang in [30, 60, 90, 120, 150]:     # numeritos de los angulos guia
        pos = punto_polar(ang, ANCHO / 2 - 60)   # posicion de cada numero
        surf.blit(fuente_chica.render(f"{ang}", True, VERDE), pos)   # lo dibuja


# Bucle principal del programa

pantalla.fill(NEGRO)                    # pinta toda la pantalla de negro al arrancar
corriendo = True                        # bandera que mantiene vivo el bucle
while corriendo:                        # se repite cuadro a cuadro hasta cerrar
    for evento in pygame.event.get():   # revisa los eventos (teclado, mouse, cerrar)
        if evento.type == pygame.QUIT:  # si se cierra la ventana
            corriendo = False           # termina el bucle
        elif evento.type == pygame.KEYDOWN and evento.key == pygame.K_ESCAPE:  # o si se aprieta Escape
            corriendo = False           # tambien termina

    leer_serial()                       # lee lo que mando el Arduino y registra detecciones
    cerrar_inactivos()                  # fija los puntos cuyos avistamientos ya terminaron
    caducar()                           # borra los objetos que ya no se ven

    pantalla.blit(fade, (0, 0))         # pinta la capa tenue encima para dejar estela
    dibujar_radar(pantalla)             # dibuja los arcos y guias
    dibujar_barrido(pantalla)           # dibuja la linea del haz
    dibujar_objetos(pantalla)           # dibuja los objetos con sus predicciones
    dibujar_texto(pantalla)             # dibuja los textos de info

    pygame.display.flip()               # muestra en pantalla todo lo dibujado este cuadro
    reloj.tick(60)                      # espera lo necesario para no pasar de 60 cuadros por segundo

if puerto_serial is not None:           # al salir del bucle, si el puerto estaba abierto
    puerto_serial.close()               # lo cierra
pygame.quit()                           # cierra pygame y libera la ventana
