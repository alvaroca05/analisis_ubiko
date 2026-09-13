# Plataforma de Análisis de Carga GPS UBIKO para Cuerpos Técnicos de Fútbol

> **Trabajo de Fin de Grado (TFG) - Grado en Ingeniería Informática**  
> **Universidad de Córdoba (UCO)**  
> **Stack:** 100% Python (Streamlit, SQLAlchemy, SQLite, Pandas, NumPy, Plotly)

---

## ⚽ Descripción y Contexto del Proyecto

En el fútbol contemporáneo de alto rendimiento, la gestión de la carga externa a través de sistemas de posicionamiento global (GPS como **UBIKO**) es fundamental para:
1. **Optimizar el rendimiento físico y táctico** de los futbolistas según el modelo de juego del entrenador.
2. **Prevenir lesiones musculares y sobrecargas articulares** controlando los picos desproporcionados de fatiga.
3. **Evaluar el cumplimiento táctico** del microciclo estructurado frente a los objetivos planificados por el cuerpo técnico.

Esta solución integra en un entorno unificado y sin dependencias externas la persistencia de datos relacional (SQLite con SQLAlchemy), el procesamiento matemático de series temporales de fatiga mediante **EWMA (Exponentially Weighted Moving Average)**, la normalización por demarcaciones tácticas mediante **Z-scores**, y una interfaz visual interactiva de última generación construida íntegramente en **Streamlit**.

---

## 🧠 Fundamentos Científicos y Metodológicos

### 1. Modelo ACWR con EWMA (Williams et al., 2017; Gabbett, 2016)
El cálculo tradicional de medias móviles simples (*Rolling Averages*) presenta importantes sesgos ("efecto escalón", ignora el decaimiento de la fatiga con el paso de los días). Por ello, este sistema implementa el modelo **EWMA**:

$$\text{Carga}_{\text{EWMA}, t} = \text{Carga}_t \times \lambda + \text{Carga}_{\text{EWMA}, t-1} \times (1 - \lambda)$$

Donde $\lambda = \frac{2}{N + 1}$:
* **Carga Aguda (Fatiga acumulada):** Ventana de $N = 7$ días ($\lambda = 0.25$).
* **Carga Crónica (Fitness / Aptitud física base):** Ventana de $N = 28$ días ($\lambda \approx 0.069$).
* **Ratio ACWR:** $\text{ACWR} = \frac{\text{Carga Aguda}_{\text{EWMA}}}{\text{Carga Crónica}_{\text{EWMA}}}$.

**Zonas del Semáforo Fisiológico:**
- `ACWR < 0.80`: **Subentrenamiento** (Azul) - Riesgo de desacondicionamiento físico.
- `0.80 ≤ ACWR ≤ 1.30`: **"Sweet Spot"** (Verde) - Rango seguro de adaptación óptima y menor riesgo lesional.
- `1.30 < ACWR ≤ 1.50`: **Precaución / Fatiga** (Amarillo) - Vigilancia de síntomas musculares.
- `ACWR > 1.50`: **Peligro / Sobrecarga** (Rojo) - Riesgo exponencial de rotura fibrilar o sobrecarga.

### 2. Microciclo Estructurado y Periodización Táctica
- **MD-4 (Tensión y Fuerza):** Tareas en espacios reducidos, duelos, alta densidad de aceleraciones y desaceleraciones.
- **MD-3 (Duración y Espacios Amplios):** Máximo volumen de distancia total (DT) y carrera a alta velocidad (HSR >19.8 km/h).
- **MD-2 (Velocidad y Táctica):** Estimulación de la velocidad punta ($V_{\text{max}}$), baja duración general.
- **MD-1 (Activación y Balón Parado):** Mínimo volumen para llegar en frescura neuromuscular al partido.
- **MD (Competición / Match Day):** Carga máxima de referencia de los 90 minutos de juego.

### 3. Z-Scores Posicionales
Normalización del rendimiento individual dentro del subconjunto de jugadores de su misma demarcación táctica (*Centrales, Laterales, Mediocentros, Extremos, Delanteros*):

$$Z = \frac{x_i - \mu_{\text{demarcación}}}{\sigma_{\text{demarcación}}}$$

Permite aislar si una desviación se debe a la exigencia propia del puesto o a un comportamiento atípico individual.

---

## 📁 Estructura del Proyecto

```
analisis_ubiko/
├── data/
│   ├── ubiko_db.sqlite3               # Base de datos local SQLite (autocreada)
│   └── samples/
│       └── ejemplo_sesion_ubiko.csv   # Plantilla estándar de exportación GPS
├── src/
│   ├── __init__.py
│   ├── config.py                      # Constantes, parámetros EWMA y rutas
│   ├── database/
│   │   ├── __init__.py
│   │   ├── connection.py              # Motor y sesiones con SQLAlchemy
│   │   └── models.py                  # Modelos ORM: Player, Session, Metric, Target
│   ├── services/
│   │   ├── __init__.py
│   │   ├── analytics.py               # Algoritmos: ACWR EWMA, Z-Scores, % Cumplimiento
│   │   ├── importer.py                # Parser inteligente CSV/Excel de UBIKO
│   │   ├── scraper.py                 # Ingesta remota automatizada (Requests/Playwright)
│   │   └── report_generator.py        # Generador de informe ejecutivo en lenguaje natural
│   └── utils/
│       ├── __init__.py
│       └── helpers.py                 # Gráficos interactivos Plotly y badges HTML
├── seed_data.py                       # Generador de plantilla real y semanas de microciclos
├── ubiko_sync.py                      # Sincronizador automático y desatendido con UBIKO Web
├── app.py                             # Aplicación interactiva Streamlit (Dashboard)
├── requirements.txt                   # Dependencias de Python fijadas
├── .env.example                       # Plantilla de credenciales UBIKO
└── README.md                          # Documentación del proyecto
```

---

## 🚀 Guía de Instalación y Ejecución Rápida

### 1. Activar el Entorno Virtual
Abre tu terminal de PowerShell en la carpeta raíz del proyecto (`analisis_ubiko`):

```powershell
# Si no está activo aún tu entorno virtual:
.\venv\Scripts\Activate.ps1
```

*(Si PowerShell bloquea la ejecución de scripts por política de seguridad, ejecuta previamente: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`)*.

### 2. Instalar las Dependencias
Con el entorno virtual activado:
```powershell
pip install -r requirements.txt
```

### 3. Poblar la Base de Datos con Datos Realistas
Ejecuta el script de siembra para inicializar la base de datos SQLite con 24 futbolistas reales y 6 semanas de sesiones completas:
```powershell
python seed_data.py
```

### 4. Iniciar la Plataforma Web Interactiva
Ejecuta el siguiente comando para abrir el dashboard en tu navegador:
```powershell
streamlit run app.py
```

La aplicación se iniciará de forma inmediata en `http://localhost:8501`.

---

## 🖥️ Módulos de la Aplicación Streamlit

1. **📊 Panel de Sesión & Semáforo:**
   - Resumen de métricas de la última sesión (Distancia Total, HSR, HMLD, AC.E).
   - Tabla interactiva con semáforo por jugador según su estado de fatiga.
   - Filtros por demarcación y comparativa gráfica de Real vs. Planificado.
   - Detección de desviaciones tácticas con gráficos de Z-Score.

2. **📈 Evolución Longitudinal & ACWR:**
   - Selector de jugador individual.
   - Gráficos interactivos de Plotly con las curvas de Carga Aguda (7d), Carga Crónica (28d) y la banda del *Sweet Spot* (0.8 - 1.3).
   - Histórico completo de sesiones y perfil de velocidad del atleta.

3. **📝 Informe Táctico Ejecutivo:**
   - Redacción automática en lenguaje natural dirigida al cuerpo técnico.
   - Alertas inmediatas de sobrecarga (Zona Roja) y recomendaciones de tareas compensatorias para suplentes.
   - Recomendaciones metodológicas para la siguiente sesión según el día de la semana.
   - Botón de descarga instantánea del reporte en `.txt`.

4. **📥 Ingesta de Datos GPS (UBIKO):**
   - Subida de ficheros `.xlsx` o `.csv` descargados del chaleco UBIKO.
   - Mapeo automático de columnas con normalización inteligente.
   - Inserción transaccional segura en la base de datos SQLite.

5. **⚙️ Objetivos de Carga Fisiológica:**
   - Matriz de consulta de los objetivos planificados por el preparador físico según demarcación y día de microciclo.
