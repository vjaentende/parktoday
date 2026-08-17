# parktoday — Cliente Python para datos.gob.es

Cliente ligero para la API del catálogo nacional de datos abiertos de España.

## Instalación

```bash
pip install -r requirements.txt
```

## Uso rápido

```python
from datos_gob_client import DatosGobClient

with DatosGobClient() as client:
    # Buscar por título
    result = client.search_datasets_by_title("aparcamiento")
    for ds in result["items"]:
        print(ds["title"])

    # Iterar todos los datasets (generador paginado)
    for dataset in client.iter_datasets():
        print(dataset["identifier"])
```

## Métodos disponibles

| Método | Endpoint |
|---|---|
| `list_datasets()` | `GET /catalog/dataset` |
| `get_dataset(id)` | `GET /catalog/dataset/{id}` |
| `search_datasets_by_title(text)` | `GET /catalog/dataset/title/{text}` |
| `datasets_by_publisher(id)` | `GET /catalog/dataset/publisher/{id}` |
| `datasets_by_spatial(kind, value)` | `GET /catalog/dataset/spatial/{kind}/{value}` |
| `datasets_by_theme(theme)` | `GET /catalog/dataset/theme/{theme}` |
| `list_distributions()` | `GET /catalog/distribution` |
| `list_publishers()` | `GET /catalog/publisher` |
| `iter_datasets()` | Generador paginado sobre todos los datasets |

Todos los métodos de listado aceptan `page`, `page_size` y (donde aplique) `sort`.

## Ejecución de ejemplos

```bash
python datos_gob_client.py
```
