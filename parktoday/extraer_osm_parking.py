"""
Extrae todos los parkings de España desde OpenStreetMap vía Overpass API.
Exporta a GeoJSON y CSV normalizado.

Los datos se extraen por comunidad autónoma para evitar timeouts.
"""

from __future__ import annotations

import csv
import json
import sys
import time
from typing import Any

import httpx

OVERPASS_URLS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]

# Bounding boxes por CCAA (lat_min, lon_min, lat_max, lon_max)
CCAA_BBOX: dict[str, tuple[float, float, float, float]] = {
    "Andalucía":                (36.0, -7.6, 38.8, -1.6),
    "Aragón":                   (39.8, -2.2, 42.9, 0.8),
    "Asturias":                 (42.9, -7.2, 43.7, -4.5),
    "Islas Baleares":           (38.6, 1.1, 40.1, 4.4),
    "Canarias":                 (27.6, -18.2, 29.5, -13.3),
    "Cantabria":                (42.7, -4.9, 43.5, -3.1),
    "Castilla y León":          (40.1, -7.1, 43.2, -1.7),
    "Castilla-La Mancha":       (38.0, -5.5, 41.0, -0.9),
    "Cataluña":                 (40.5, 0.15, 42.9, 3.4),
    "Comunidad Valenciana":     (37.8, -1.6, 40.8, 0.7),
    "Extremadura":              (38.0, -7.6, 40.5, -4.6),
    "Galicia":                  (41.8, -9.3, 43.8, -6.7),
    "Comunidad de Madrid":      (39.9, -4.6, 41.2, -3.0),
    "Región de Murcia":         (37.3, -2.4, 38.8, -0.6),
    "Comunidad Foral de Navarra": (41.9, -2.5, 43.3, -0.7),
    "País Vasco":               (42.4, -3.5, 43.5, -1.7),
    "La Rioja":                 (41.9, -3.2, 42.7, -1.6),
    "Ceuta":                    (35.87, -5.37, 35.92, -5.27),
    "Melilla":                  (35.26, -2.97, 35.31, -2.92),
}

OUTPUT_CSV = "parkings_osm_espana.csv"
OUTPUT_GEOJSON = "parkings_osm_espana.geojson"


def query_overpass(bbox: tuple[float, float, float, float], timeout: int = 180, max_retries: int = 3) -> list[dict[str, Any]]:
    """Consulta Overpass API para parkings en un bounding box con reintentos."""
    lat_min, lon_min, lat_max, lon_max = bbox
    query = f"""
    [out:json][timeout:{timeout}];
    (
      node["amenity"="parking"]({lat_min},{lon_min},{lat_max},{lon_max});
      way["amenity"="parking"]({lat_min},{lon_min},{lat_max},{lon_max});
    );
    out center tags;
    """
    for attempt in range(max_retries):
        for url in OVERPASS_URLS:
            try:
                client = httpx.Client(timeout=timeout + 60)
                resp = client.post(url, data={"data": query})
                client.close()
                if resp.status_code == 200:
                    return resp.json().get("elements", [])
                if resp.status_code == 429 or resp.status_code == 406:
                    wait = 15 * (attempt + 1)
                    sys.stdout.write(f"    (rate limited, esperando {wait}s...)\n")
                    sys.stdout.flush()
                    time.sleep(wait)
                    continue
            except Exception:
                continue
        time.sleep(10)
    raise RuntimeError(f"Overpass: fallo tras {max_retries} intentos")


def parse_element(el: dict[str, Any], ccaa: str) -> dict[str, str]:
    """Convierte un elemento OSM a fila normalizada."""
    tags = el.get("tags", {})

    # Coordenadas: nodes tienen lat/lon directo, ways tienen center
    if el["type"] == "node":
        lat = el.get("lat", "")
        lon = el.get("lon", "")
    else:
        center = el.get("center", {})
        lat = center.get("lat", "")
        lon = center.get("lon", "")

    # Tipo de parking
    parking_type = tags.get("parking", "")
    if not parking_type:
        if tags.get("layer", "") == "-1" or tags.get("location", "") == "underground":
            parking_type = "underground"

    # Acceso
    access = tags.get("access", "")
    fee = tags.get("fee", "")

    return {
        "osm_id": f"{el['type']}/{el['id']}",
        "nombre": tags.get("name", ""),
        "lat": str(lat),
        "lon": str(lon),
        "comunidad_autonoma": ccaa,
        "tipo": parking_type,
        "capacidad": tags.get("capacity", ""),
        "acceso": access,
        "de_pago": fee,
        "operador": tags.get("operator", ""),
        "tipo_operador": tags.get("operator:type", ""),
        "horario": tags.get("opening_hours", ""),
        "altura_max": tags.get("maxheight", ""),
        "superficie": tags.get("surface", ""),
        "iluminado": tags.get("lit", ""),
        "vigilado": tags.get("supervised", ""),
        "url": tags.get("website", tags.get("url", "")),
        "wheelchair": tags.get("wheelchair", ""),
        "fuente": "OpenStreetMap",
    }


def to_geojson(rows: list[dict[str, str]]) -> dict[str, Any]:
    """Convierte filas a GeoJSON FeatureCollection."""
    features = []
    for r in rows:
        if not r["lat"] or not r["lon"]:
            continue
        props = {k: v for k, v in r.items() if k not in ("lat", "lon") and v}
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [float(r["lon"]), float(r["lat"])],
            },
            "properties": props,
        })
    return {"type": "FeatureCollection", "features": features}


def main() -> None:
    all_rows: list[dict[str, str]] = []
    seen_ids: set[str] = set()

    print("Extrayendo parkings de OpenStreetMap (España)...")
    print(f"{'CCAA':<35} {'Parkings':>8}  {'Acumulado':>10}")
    print("-" * 60)

    for ccaa, bbox in sorted(CCAA_BBOX.items()):
        try:
            elements = query_overpass(bbox)
        except Exception as e:
            print(f"  ERROR en {ccaa}: {e}")
            continue

        count = 0
        for el in elements:
            osm_id = f"{el['type']}/{el['id']}"
            if osm_id in seen_ids:
                continue
            seen_ids.add(osm_id)
            row = parse_element(el, ccaa)
            if row["lat"] and row["lon"]:
                all_rows.append(row)
                count += 1

        print(f"  {ccaa:<33} {count:>8}  {len(all_rows):>10}")

        # Rate limiting para Overpass
        time.sleep(10)

    print(f"\nTotal parkings únicos: {len(all_rows)}")

    if not all_rows:
        print("No se obtuvieron datos. Revisa la conexión a Overpass API.")
        return

    # Stats
    with_name = sum(1 for r in all_rows if r["nombre"])
    with_capacity = sum(1 for r in all_rows if r["capacidad"])
    with_fee = sum(1 for r in all_rows if r["de_pago"])
    with_operator = sum(1 for r in all_rows if r["operador"])
    with_hours = sum(1 for r in all_rows if r["horario"])

    print(f"  Con nombre: {with_name} ({100*with_name/len(all_rows):.0f}%)")
    print(f"  Con capacidad: {with_capacity} ({100*with_capacity/len(all_rows):.0f}%)")
    print(f"  Con info de pago: {with_fee} ({100*with_fee/len(all_rows):.0f}%)")
    print(f"  Con operador: {with_operator} ({100*with_operator/len(all_rows):.0f}%)")
    print(f"  Con horario: {with_hours} ({100*with_hours/len(all_rows):.0f}%)")

    # Tipos
    from collections import Counter
    types = Counter(r["tipo"] for r in all_rows if r["tipo"])
    print("\n  Tipos de parking:")
    for t, c in types.most_common():
        print(f"    {t}: {c}")

    # Write CSV
    fieldnames = list(all_rows[0].keys())
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"\nCSV: {OUTPUT_CSV}")

    # Write GeoJSON
    geojson = to_geojson(all_rows)
    with open(OUTPUT_GEOJSON, "w", encoding="utf-8") as f:
        json.dump(geojson, f, ensure_ascii=False)
    print(f"GeoJSON: {OUTPUT_GEOJSON}")


if __name__ == "__main__":
    main()
