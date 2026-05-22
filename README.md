# 🚛 Tablero Operativo de Flota

Dashboard en Streamlit para el seguimiento de demoras, incidencias y kilómetros de flota.

---

## 📋 Estructura del proyecto

```
dashboard/
├── app.py                  # Aplicación principal
├── requirements.txt        # Dependencias Python
├── .streamlit/
│   └── secrets.toml        # Credenciales Google (NO subir a git)
└── README.md
```

---

## 🗂️ Estructura del Google Sheet

El Google Sheet debe tener **exactamente 3 hojas** con estos nombres:

| Nombre de hoja    | Datos                                   |
|-------------------|-----------------------------------------|
| `CargarDescargas` | Reporte de cargas y descargas           |
| `Incidencias`     | Registro de incidencias                 |
| `ICMRanking`      | Ranking ICM / km por chofer             |

### Columnas requeridas por hoja

**CargarDescargas:**
`#, Patente, Alias actual, Conductor, Login del conductor, Login antes del ingreso (hs:mm), Zona, Tipo de zona, Origen, Entró, Entró al dock, Salió del dock, Tiempo en cola (hs:mm), Tiempo en dock (hs:mm), Demora total (hs:mm), Estado, IMEI`

**Incidencias:**
`#, Estado, Severidad, Patente, Alias, IMEI, Categoría, Subcategoría, Chofer, Lugar, Descripción, Retroactiva, Fecha del evento, Cargada por, Fecha de carga`

**ICMRanking:**
`#, Alias, Patente, IMEI, Ev/100km, Eventos, KM, Velocidad, Frenados, Aceleración, Giros, Baches, Fatiga (#), Fatiga (min)`

---

## ⚙️ Configuración paso a paso

### 1. Crear Service Account en Google Cloud

1. Ir a [console.cloud.google.com](https://console.cloud.google.com)
2. Crear un proyecto nuevo (o usar uno existente)
3. Habilitar las APIs:
   - **Google Sheets API**
   - **Google Drive API**
4. Ir a **IAM & Admin → Service Accounts → Crear**
5. Darle un nombre, por ejemplo: `flota-dashboard`
6. En **Claves**, crear una clave nueva → tipo **JSON** → descargar el archivo

### 2. Configurar el archivo secrets.toml

Copiar el contenido del JSON descargado al archivo `.streamlit/secrets.toml` siguiendo el template provisto.

### 3. Compartir el Google Sheet con la Service Account

1. Abrir el Google Sheet
2. Hacer clic en **Compartir**
3. Agregar el email de la Service Account (termina en `@...iam.gserviceaccount.com`)
4. Darle permiso de **Editor** (para que otros puedan editar datos directamente en Sheets)

### 4. Instalar dependencias y correr

```bash
pip install -r requirements.txt
streamlit run app.py
```

---

## 🚀 Deploy en Streamlit Cloud (gratuito)

1. Subir el proyecto a un repositorio de GitHub (**sin el secrets.toml**)
2. Ir a [share.streamlit.io](https://share.streamlit.io) → conectar el repo
3. En **Settings → Secrets**, pegar el contenido del `secrets.toml`
4. Deploy 🎉

---

## 📊 Pestañas del dashboard

| Pestaña | Contenido |
|---------|-----------|
| **Demoras Cargas & Descargas** | Heatmaps día×hora, demora por día de semana, top unidades demoradas, impacto Palmira |
| **Incidencias** | Top unidades con más fallas, categorías, evolución temporal, tabla para taller |
| **Km por Chofer / ICM** | Ranking KM, umbral configurable, alertas unidades bajo ritmo, eventos/100km |

---

## 🔄 Flujo de datos

```
Operador copia datos → Google Sheet (editable)
        ↓
    Streamlit app lee vía API (cada 5 minutos)
        ↓
    Visualizaciones automáticas actualizadas
```

---

## ⚠️ Notas importantes

- Los datos en Google Sheets se cachean **5 minutos**. Usar el botón "🔄 Recargar datos" para forzar actualización.
- En modo demo, los datos se leen directamente de los archivos Excel de ejemplo.
- Los formatos de tiempo `X days HH:MM:SS` son convertidos automáticamente a minutos para los cálculos.
