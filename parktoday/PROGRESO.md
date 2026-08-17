# ParkToday - Progreso del proyecto

## Idea
App tipo Waze para aparcamiento en España. Los usuarios reportan plazas disponibles.
Necesitamos una capa base con TODOS los sitios legales donde aparcar: zonas azules, verdes, SER, ORA, parkings públicos/privados, plazas en superficie, etc.

## Datos recopilados

### 1. OpenStreetMap - amenity=parking (COMPLETADO)
- **163.000 parkings** en toda España (sin Portugal)
- Fichero: `parkings_osm_espana.csv` (13 MB) + `.geojson` (36 MB, no en git)
- Campos: osm_id, nombre, lat, lon, tipo, capacidad, acceso, de_pago, operador, horario, etc.
- Tipos: surface (76K), street_side (55K), underground (4K), multi-storey (820)
- Calidad: 26% con info de pago, 10% con capacidad, 5% con nombre
- Script: `extraer_osm_parking.py`
- Descargado en 4 cuadrantes + Canarias via Overpass API

### 2. OpenStreetMap - tags extra (PENDIENTE - Overpass rate limited)
- Script: `extraer_osm_extra.py`
- Se sabe que existen: ~9.000 parquímetros, ~21.600 entradas de parking
- Tags pendientes: parking_entrance, parking_space, parking:lane, parking:condition, vending=parking_tickets
- Los servidores Overpass quedaron saturados — reintentar mañana con más pausa entre queries

### 3. datos.gob.es - Catálogo nacional (COMPLETADO)
- **225 datasets** catalogados de aparcamiento
- Fichero catálogo: `aparcamientos_datos_gob.csv`
- Enriquecido con nombres reales de publicadores (DIR3) y CCAA/provincia/municipio
- 22 municipios, 16 comunidades autónomas
- Script: `extraer_aparcamientos.py`
- Script descarga CSVs: `download_datos_gob.py`

### 4. Portales municipales (PARCIAL)
- Directorio: `municipal_data/`
- **Barcelona**: 9 ficheros descargados (OK)
  - Estacionamientos DUM (944KB), reservas infraestructura (14MB), tramos superficie (3MB)
  - Aparcamientos bajo superficie, horarios, tarifas, colores, servicio bicis
- **Málaga**: 10 ficheros descargados (OK)
  - Aparcamientos bici (47KB), motos (60KB), movilidad reducida (267KB)
  - Rotación, residentes, plazas, uso, ocupación, tarifas
- **Madrid**: Portal cambió a CKAN + WAF bloquea API → PENDIENTE acceso manual
- **Valencia**: API opendatasoft no devolvió resultados con los queries probados → PENDIENTE
- **Zaragoza, Bilbao/Euskadi, Sevilla, Gijón**: APIs no respondieron → PENDIENTE

### 5. Cliente API datos.gob.es (COMPLETADO)
- `datos_gob_client.py` — clase DatosGobClient con httpx, reintentos, paginación automática
- `requirements.txt` — solo httpx

## Resumen de datos totales

| Fuente | Registros | Estado |
|---|---|---|
| OSM amenity=parking | 163.000 | COMPLETADO |
| OSM parquímetros | ~9.000 | PENDIENTE (coords) |
| OSM entradas parking | ~21.600 | PENDIENTE (coords) |
| datos.gob.es catálogo | 225 datasets | COMPLETADO |
| Barcelona municipal | 9 ficheros | COMPLETADO |
| Málaga municipal | 10 ficheros | COMPLETADO |
| Madrid municipal | 0 | PENDIENTE |
| Otros municipios | 0 | PENDIENTE |

## Ficheros en el repo

```
parktoday/
├── PROGRESO.md                  # Este fichero
├── README.md
├── requirements.txt
├── .gitignore
├── datos_gob_client.py          # Cliente API datos.gob.es
├── extraer_aparcamientos.py     # Extractor datos.gob.es con enriquecimiento DIR3
├── extraer_osm_parking.py       # Extractor OSM amenity=parking (cuadrantes)
├── extraer_osm_extra.py         # Extractor OSM tags extra
├── download_datos_gob.py        # Descargador de CSVs de datos.gob.es
├── aparcamientos_datos_gob.csv  # 225 datasets catalogados
├── parkings_osm_espana.csv      # 163K parkings OSM (13MB)
├── mapa_parkings.html           # Mapa interactivo de calor
└── municipal_data/              # Datos de portales municipales
    ├── municipal_barcelona_*.csv/json (9 ficheros)
    └── municipal_malaga_*.csv (10 ficheros)
```

## Próximos pasos
1. **Reintentar OSM extra** (parquímetros + entradas con coordenadas) — esperar a que Overpass se recupere
2. **Madrid**: acceder al portal CKAN manualmente o via browser automation
3. **Valencia, Zaragoza, Sevilla**: buscar URLs directas a los datos
4. **Normalizar** TODOS los datos a un formato único: id, lat, lon, tipo, nombre, capacidad, pago, zona, fuente
5. **Generar mapa** de cobertura final por CCAA
6. **Eliminar duplicados** entre fuentes (mismo parking en OSM y en municipal)
7. **Diseñar estructura de la app**

## Notas técnicas
- Overpass API: usar 30-60s entre queries. Endpoints: kumi.systems (primary), overpass-api.de (backup)
- datos.madrid.es: migraron a CKAN 2.9.11, WAF bloquea /api/ con 403. Probar con browser.
- Git root es /Users/victorjaenruiz (home), proyecto en subcarpeta parktoday/
- Python venv: .venv/bin/python3 (httpx instalado)

## Repo GitHub
https://github.com/vjaentende/parktoday
