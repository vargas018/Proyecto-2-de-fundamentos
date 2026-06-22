

#include <Servo.h>   // libreria para controlar el servomotor

// Pines segun como esta armado el circuito.
const int trigPin  = 10;   // pin que dispara el pulso del sensor ultrasonico
const int echoPin  = 11;   // pin que recibe el eco de regreso
const int servoPin = 12;   // pin de senal del servo
const int ledPin   = 13;   // LED rojo de alerta (el pin 13 trae tambien el LED de la placa)

// Ajustes de la medicion.
const unsigned long TIMEOUT_US = 8000UL; // espera maxima del eco en microsegundos, da unos 1.3 m de alcance
const int  MUESTRAS   = 3;     // cuantas lecturas se toman por grado, se devuelve la mediana
const int  GAP_PING   = 2;     // milisegundos de pausa entre una lectura y otra
const int  SETTLE_MS  = 20;    // espera tras mover el servo antes de medir, para que se asiente
const int  PERIODO_MS = 55;    // tiempo fijo que dura cada grado, haya o no objeto, para una cadencia pareja
// PERIODO_MS conviene que sea mayor o igual al peor caso de medicion: asentamiento
// 20, mas tres pulsos sin eco que suman unos 24, mas las pausas unos 4, mas el
// envio serial unos 6, en total cerca de 54 ms. Subirlo hace el barrido mas lento
// pero igual de constante.

Servo myServo;   // objeto que representa al servo

void setup() {
  pinMode(trigPin, OUTPUT);     // el trig manda senal, es salida
  pinMode(echoPin, INPUT);      // el echo recibe senal, es entrada
  pinMode(ledPin, OUTPUT);      // el LED es salida
  digitalWrite(trigPin, LOW);   // deja el trig en reposo (apagado)
  Serial.begin(9600);           // abre el puerto serial a 9600 baudios
  myServo.attach(servoPin);     // asocia el servo a su pin
}

void loop() {
  for (int a = 0; a <= 180; a++) barrer(a);   // barrido de ida, de 0 a 180 grados
  for (int a = 180; a > 0;  a--) barrer(a);   // barrido de vuelta, de 180 a 0 grados
}

// Mueve el servo al angulo dado, mide y manda por serial el texto angulo,distancia.
void barrer(int angulo) {
  unsigned long inicio = millis();   // marca el instante en que empieza este grado
  myServo.write(angulo);             // mueve el servo a ese angulo
  delay(SETTLE_MS);                  // espera a que el servo llegue antes de medir, para no leer en movimiento
  int distancia = medirDistancia();  // toma la distancia en cm
  Serial.print(angulo);              // manda el angulo
  Serial.print(",");                 // separador entre angulo y distancia
  Serial.print(distancia);           // manda la distancia
  Serial.print(".");                 // punto que marca el fin del paquete
  digitalWrite(ledPin, !digitalRead(ledPin));  // invierte el LED, asi parpadea con el barrido

  // Rellena el tiempo que sobro hasta completar PERIODO_MS exacto, asi cada grado
  // dura siempre lo mismo haya o no objeto.
  while (millis() - inicio < PERIODO_MS) { /* espera activa */ }
}

// Hace una sola medicion con el sensor y devuelve la distancia en cm. Da 0 si no hubo eco.
int unaMedida() {
  digitalWrite(trigPin, LOW);          // asegura el trig apagado
  delayMicroseconds(3);                // pausa corta
  digitalWrite(trigPin, HIGH);         // enciende el trig
  delayMicroseconds(10);               // pulso de disparo de 10 microsegundos, como dice la hoja de datos
  digitalWrite(trigPin, LOW);          // apaga el trig

  unsigned long dur = pulseIn(echoPin, HIGH, TIMEOUT_US);  // mide cuanto tarda en volver el eco
  if (dur == 0) return 0;              // si no volvio nada, no hay objeto
  return (int)(dur * 0.0343 / 2.0);    // pasa el tiempo de ida y vuelta a centimetros
}

// Toma varias lecturas y devuelve la mediana de las validas. El sensor pierde ecos
// de vez en cuando, asi que repetir evita reportar nada cuando si hay objeto.
// Solo devuelve 0 si todas las lecturas fallaron.
int medirDistancia() {
  int v[MUESTRAS];   // arreglo donde se guardan las lecturas con eco
  int n = 0;         // cuantas lecturas validas se llevan
  for (int i = 0; i < MUESTRAS; i++) {   // toma MUESTRAS lecturas
    int d = unaMedida();                 // una medicion
    if (d > 0) v[n++] = d;               // si tuvo eco, la guarda y sube el contador
    if (i < MUESTRAS - 1) delay(GAP_PING);   // pausa entre lecturas, menos despues de la ultima
  }
  if (n == 0) return 0;                  // si ninguna tuvo eco, de verdad no hay objeto

  // Ordena las n lecturas validas con insertion sort, para sacar la mediana.
  for (int i = 1; i < n; i++) {          // recorre desde la segunda
    int key = v[i];                      // valor que se va a ubicar
    int j = i - 1;                       // indice del de la izquierda
    while (j >= 0 && v[j] > key) { v[j + 1] = v[j]; j--; }  // corre los mayores a la derecha
    v[j + 1] = key;                      // coloca el valor en su lugar
  }
  return v[n / 2];                       // devuelve el del medio, la mediana, que descarta los picos
}
