"""
Extrae todos los datasets de aparcamiento de datos.gob.es
y los organiza por comunidad autónoma, provincia y municipio.
Exporta a CSV y muestra un resumen por consola.

Enriquece los datos geográficos usando:
1. El campo spatial del dataset (si existe)
2. El código DIR3 del publicador (L01PPMMMM → provincia PP, municipio)
3. Mapeo manual de organismos autonómicos y estatales
"""

from __future__ import annotations

import csv
import re
import sys
from collections import defaultdict
from typing import Any

from datos_gob_client import DatosGobClient

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

KEYWORDS = [
    "aparcamiento",
    "aparcamientos",
    "parking",
    "estacionamiento",
    "parquímetro",
    "zona azul",
]

RELEVANT_WORDS = {
    "aparcamiento", "aparcamientos", "parking", "estacionamiento", "estacionamientos",
    "parquímetro", "parquímetros", "zona azul", "zona verde", "aparca", "park",
    "garaje", "garajes", "párking", "parkings", "plazas de garaje",
    "disuasorio", "disuasorios", "disuasión",
    "rotatorio", "rotación",
}

OUTPUT_CSV = "aparcamientos_datos_gob.csv"

# Normalización de nombres geográficos (spatial usa nombres sin tildes)
NORMALIZE_GEO: dict[str, str] = {
    "Cataluna": "Cataluña",
    "Aragon": "Aragón",
    "Castilla Leon": "Castilla y León",
    "Comunidad Foral Navarra": "Comunidad Foral de Navarra",
    "Pais Vasco": "País Vasco",
    "Region Murcia": "Región de Murcia",
    "Comunidad Valenciana": "Comunidad Valenciana",
    "Andalucia": "Andalucía",
    "Espana": "España",
    "Malaga": "Málaga",
    "Cadiz": "Cádiz",
    "Cordoba": "Córdoba",
    "Jaen": "Jaén",
    "Almeria": "Almería",
    "Alava": "Álava",
    "Vizcaya": "Vizcaya",
    "Gipuzkoa": "Gipuzkoa",
    "Leon": "León",
    "Castellon": "Castellón",
    "Caceres": "Cáceres",
}

# ---------------------------------------------------------------------------
# Mapeo geográfico: códigos INE de provincia → (nombre provincia, CCAA)
# ---------------------------------------------------------------------------

PROVINCIAS_INE: dict[str, tuple[str, str]] = {
    "01": ("Álava", "País Vasco"),
    "02": ("Albacete", "Castilla-La Mancha"),
    "03": ("Alicante", "Comunidad Valenciana"),
    "04": ("Almería", "Andalucía"),
    "05": ("Ávila", "Castilla y León"),
    "06": ("Badajoz", "Extremadura"),
    "07": ("Islas Baleares", "Islas Baleares"),
    "08": ("Barcelona", "Cataluña"),
    "09": ("Burgos", "Castilla y León"),
    "10": ("Cáceres", "Extremadura"),
    "11": ("Cádiz", "Andalucía"),
    "12": ("Castellón", "Comunidad Valenciana"),
    "13": ("Ciudad Real", "Castilla-La Mancha"),
    "14": ("Córdoba", "Andalucía"),
    "15": ("A Coruña", "Galicia"),
    "16": ("Cuenca", "Castilla-La Mancha"),
    "17": ("Girona", "Cataluña"),
    "18": ("Granada", "Andalucía"),
    "19": ("Guadalajara", "Castilla-La Mancha"),
    "20": ("Gipuzkoa", "País Vasco"),
    "21": ("Huelva", "Andalucía"),
    "22": ("Huesca", "Aragón"),
    "23": ("Jaén", "Andalucía"),
    "24": ("León", "Castilla y León"),
    "25": ("Lleida", "Cataluña"),
    "26": ("La Rioja", "La Rioja"),
    "27": ("Lugo", "Galicia"),
    "28": ("Madrid", "Comunidad de Madrid"),
    "29": ("Málaga", "Andalucía"),
    "30": ("Murcia", "Región de Murcia"),
    "31": ("Navarra", "Comunidad Foral de Navarra"),
    "32": ("Ourense", "Galicia"),
    "33": ("Asturias", "Principado de Asturias"),
    "34": ("Palencia", "Castilla y León"),
    "35": ("Las Palmas", "Canarias"),
    "36": ("Pontevedra", "Galicia"),
    "37": ("Salamanca", "Castilla y León"),
    "38": ("Santa Cruz de Tenerife", "Canarias"),
    "39": ("Cantabria", "Cantabria"),
    "40": ("Segovia", "Castilla y León"),
    "41": ("Sevilla", "Andalucía"),
    "42": ("Soria", "Castilla y León"),
    "43": ("Tarragona", "Cataluña"),
    "44": ("Teruel", "Aragón"),
    "45": ("Toledo", "Castilla-La Mancha"),
    "46": ("Valencia", "Comunidad Valenciana"),
    "47": ("Valladolid", "Castilla y León"),
    "48": ("Vizcaya", "País Vasco"),
    "49": ("Zamora", "Castilla y León"),
    "50": ("Zaragoza", "Aragón"),
    "51": ("Ceuta", "Ceuta"),
    "52": ("Melilla", "Melilla"),
}

# ---------------------------------------------------------------------------
# Mapeo de códigos DIR3 de publicador → (nombre, municipio, provincia, CCAA)
# Resueltos desde datos.gob.es/recurso/sector-publico/org/Organismo/{code}
# ---------------------------------------------------------------------------

PUBLISHER_INFO: dict[str, dict[str, str]] = {
    # Organismos autonómicos (A...)
    "A01002820": {"nombre": "Junta de Andalucía", "comunidad": "Andalucía"},
    "A04003003": {"nombre": "Gobierno de las Illes Balears", "comunidad": "Islas Baleares"},
    "A05003423": {"nombre": "Instituto Canario de Estadística (ISTAC)", "comunidad": "Canarias"},
    "A07002862": {"nombre": "Junta de Castilla y León", "comunidad": "Castilla y León"},
    "A09002970": {"nombre": "Generalitat de Catalunya", "comunidad": "Cataluña"},
    "A13002908": {"nombre": "Comunidad de Madrid", "comunidad": "Comunidad de Madrid"},
    "A14002961": {"nombre": "Región de Murcia (CARM)", "comunidad": "Región de Murcia"},
    "A15002917": {"nombre": "Comunidad Foral de Navarra", "comunidad": "Comunidad Foral de Navarra"},
    "A16003011": {"nombre": "Comunidad Autónoma del País Vasco", "comunidad": "País Vasco"},
    # Organismos estatales (EA...)
    "EA0042823": {"nombre": "Instituto Nacional de Estadística (INE)", "comunidad": "España (estatal)"},
    # Ayuntamientos (L01PPMMMM) — nombre completo
    "L01010590": {"nombre": "Ayuntamiento de Vitoria-Gasteiz", "municipio": "Vitoria-Gasteiz", "provincia": "Álava", "comunidad": "País Vasco"},
    "L01061535": {"nombre": "Ayuntamiento de Villanueva de la Serena", "municipio": "Villanueva de la Serena", "provincia": "Badajoz", "comunidad": "Extremadura"},
    "L01080193": {"nombre": "Ayuntamiento de Barcelona", "municipio": "Barcelona", "provincia": "Barcelona", "comunidad": "Cataluña"},
    "L01082798": {"nombre": "Ayuntamiento de Terrassa", "municipio": "Terrassa", "provincia": "Barcelona", "comunidad": "Cataluña"},
    "L01100377": {"nombre": "Ayuntamiento de Cáceres", "municipio": "Cáceres", "provincia": "Cáceres", "comunidad": "Extremadura"},
    "L01200697": {"nombre": "Ayuntamiento de Donostia/San Sebastián", "municipio": "Donostia/San Sebastián", "provincia": "Gipuzkoa", "comunidad": "País Vasco"},
    "L01280066": {"nombre": "Ayuntamiento de Alcobendas", "municipio": "Alcobendas", "provincia": "Madrid", "comunidad": "Comunidad de Madrid"},
    "L01280148": {"nombre": "Ayuntamiento de Arganda del Rey", "municipio": "Arganda del Rey", "provincia": "Madrid", "comunidad": "Comunidad de Madrid"},
    "L01280796": {"nombre": "Ayuntamiento de Madrid", "municipio": "Madrid", "provincia": "Madrid", "comunidad": "Comunidad de Madrid"},
    "L01281150": {"nombre": "Ayuntamiento de Pozuelo de Alarcón", "municipio": "Pozuelo de Alarcón", "provincia": "Madrid", "comunidad": "Comunidad de Madrid"},
    "L01281317": {"nombre": "Ayuntamiento de San Lorenzo de El Escorial", "municipio": "San Lorenzo de El Escorial", "provincia": "Madrid", "comunidad": "Comunidad de Madrid"},
    "L01290672": {"nombre": "Ayuntamiento de Málaga", "municipio": "Málaga", "provincia": "Málaga", "comunidad": "Andalucía"},
    "L01300243": {"nombre": "Ayuntamiento de Lorca", "municipio": "Lorca", "provincia": "Murcia", "comunidad": "Región de Murcia"},
    "L01312016": {"nombre": "Ayuntamiento de Pamplona", "municipio": "Pamplona", "provincia": "Navarra", "comunidad": "Comunidad Foral de Navarra"},
    "L01330241": {"nombre": "Ayuntamiento de Gijón", "municipio": "Gijón", "provincia": "Asturias", "comunidad": "Principado de Asturias"},
    "L01360577": {"nombre": "Ayuntamiento de Vigo", "municipio": "Vigo", "provincia": "Pontevedra", "comunidad": "Galicia"},
    "L01380380": {"nombre": "Ayuntamiento de Santa Cruz de Tenerife", "municipio": "Santa Cruz de Tenerife", "provincia": "Santa Cruz de Tenerife", "comunidad": "Canarias"},
    "L01390759": {"nombre": "Ayuntamiento de Santander", "municipio": "Santander", "provincia": "Cantabria", "comunidad": "Cantabria"},
    "L01462444": {"nombre": "Ayuntamiento de Torrent", "municipio": "Torrent", "provincia": "Valencia", "comunidad": "Comunidad Valenciana"},
    "L01462508": {"nombre": "Ayuntamiento de Valencia", "municipio": "Valencia", "provincia": "Valencia", "comunidad": "Comunidad Valenciana"},
    "L01480209": {"nombre": "Ayuntamiento de Bilbao", "municipio": "Bilbao", "provincia": "Vizcaya", "comunidad": "País Vasco"},
    "L01502973": {"nombre": "Ayuntamiento de Zaragoza", "municipio": "Zaragoza", "provincia": "Zaragoza", "comunidad": "Aragón"},
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_title_es(dataset: dict[str, Any]) -> str:
    title = dataset.get("title", "")
    if isinstance(title, list):
        for t in title:
            if isinstance(t, dict) and t.get("_lang") == "es":
                return t["_value"]
        if title and isinstance(title[0], dict):
            return title[0].get("_value", "")
    return str(title)


def get_description_es(dataset: dict[str, Any]) -> str:
    desc = dataset.get("description", "")
    if isinstance(desc, list):
        for d in desc:
            if isinstance(d, dict) and d.get("_lang") == "es":
                return d["_value"]
        if desc and isinstance(desc[0], dict):
            return desc[0].get("_value", "")
    return str(desc) if desc else ""


def is_parking_related(title: str) -> bool:
    """Comprueba que el título realmente habla de aparcamiento."""
    lower = title.lower()
    for word in RELEVANT_WORDS:
        if word in lower:
            return True
    return False


def extract_publisher_code(publisher: Any) -> str:
    """Extrae el código DIR3 del publisher URI."""
    if not publisher or not isinstance(publisher, str):
        return ""
    m = re.search(r"/Organismo/(.+)$", publisher)
    return m.group(1) if m else publisher


def parse_spatial(spatial: Any) -> dict[str, str]:
    """Extrae comunidad autónoma, provincia, municipio y país de la URI spatial."""
    result: dict[str, str] = {"pais": "", "comunidad": "", "provincia": "", "municipio": ""}
    if not spatial:
        return result
    uris = spatial if isinstance(spatial, list) else [spatial]
    for uri in uris:
        if not isinstance(uri, str):
            continue
        m = re.search(r"/territorio/(Autonomia|Provincia|Pais|Municipio)/(.+)$", uri)
        if m:
            tipo, valor = m.group(1), m.group(2).replace("-", " ")
            valor = NORMALIZE_GEO.get(valor, valor)
            if tipo == "Pais":
                result["pais"] = valor
            elif tipo == "Autonomia":
                result["comunidad"] = valor
            elif tipo == "Provincia":
                result["provincia"] = valor
            elif tipo == "Municipio":
                result["municipio"] = valor
    return result


def enrich_geo(
    geo: dict[str, str], publisher_code: str
) -> dict[str, str]:
    """Enriquece la info geográfica con datos del publicador si faltan."""
    pub_info = PUBLISHER_INFO.get(publisher_code, {})

    # Si no tenemos comunidad desde spatial, intentar desde el publicador
    if not geo["comunidad"] and pub_info.get("comunidad"):
        geo["comunidad"] = pub_info["comunidad"]

    # Si no tenemos provincia, intentar desde publicador conocido o código DIR3
    if not geo["provincia"]:
        if pub_info.get("provincia"):
            geo["provincia"] = pub_info["provincia"]
        elif publisher_code.startswith("L01") and len(publisher_code) >= 5:
            prov_code = publisher_code[3:5]
            if prov_code in PROVINCIAS_INE:
                geo["provincia"] = PROVINCIAS_INE[prov_code][0]
                if not geo["comunidad"]:
                    geo["comunidad"] = PROVINCIAS_INE[prov_code][1]

    # Si no tenemos municipio, intentar desde publicador conocido
    if not geo["municipio"] and pub_info.get("municipio"):
        geo["municipio"] = pub_info["municipio"]

    return geo


def get_publisher_name(code: str) -> str:
    """Devuelve el nombre legible del publicador."""
    info = PUBLISHER_INFO.get(code)
    if info:
        return info["nombre"]
    return code


def get_distributions(dataset: dict[str, Any]) -> list[dict[str, str]]:
    """Extrae URLs de descarga de las distribuciones."""
    dist = dataset.get("distribution", [])
    if isinstance(dist, dict):
        dist = [dist]
    results = []
    for d in dist:
        if not isinstance(d, dict):
            continue
        fmt = d.get("format", "")
        if isinstance(fmt, dict):
            # Prefer MIME value (text/csv) over _about URL
            fmt = fmt.get("value", fmt.get("_about", str(fmt)))
        if isinstance(fmt, str):
            # URI like ".../file-type/CSV" → "CSV"
            if "file-type/" in fmt:
                fmt = fmt.split("file-type/")[-1]
            # MIME like "text/csv" → "CSV", "application/json" → "JSON"
            elif "/" in fmt and len(fmt) < 60:
                fmt = fmt.split("/")[-1].upper()
                # Clean up suffixes like "gml+xml" → "GML+XML"
            # Already clean → keep as-is
        results.append({
            "format": str(fmt),
            "download_url": d.get("downloadURL", d.get("accessURL", "")),
        })
    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    client = DatosGobClient()
    seen: set[str] = set()
    datasets: list[dict[str, Any]] = []

    print("Buscando datasets de aparcamiento en datos.gob.es...")

    for kw in KEYWORDS:
        page = 0
        while True:
            result = client.search_datasets_by_title(kw, page=page, page_size=50)
            items = result.get("items", [])
            for ds in items:
                about = ds.get("_about", "")
                if about in seen:
                    continue
                seen.add(about)
                title = get_title_es(ds)
                if is_parking_related(title):
                    datasets.append(ds)
            if "next" not in result or not items:
                break
            page += 1
        sys.stdout.write(f"  '{kw}' procesado — {len(datasets)} datasets acumulados\n")

    print(f"\nTotal datasets de aparcamiento encontrados: {len(datasets)}")

    # Build rows with enriched geo data
    rows: list[dict[str, str]] = []
    for ds in datasets:
        title = get_title_es(ds)
        desc = get_description_es(ds)
        pub_code = extract_publisher_code(ds.get("publisher"))
        geo = parse_spatial(ds.get("spatial"))
        geo = enrich_geo(geo, pub_code)
        distributions = get_distributions(ds)
        download_urls = " | ".join(d["download_url"] for d in distributions if d["download_url"])
        formats = " | ".join(d["format"] for d in distributions if d["format"])

        rows.append({
            "titulo": title,
            "descripcion": desc[:300],
            "comunidad_autonoma": geo["comunidad"],
            "provincia": geo["provincia"],
            "municipio": geo["municipio"],
            "publicador_codigo": pub_code,
            "publicador_nombre": get_publisher_name(pub_code),
            "identificador": ds.get("identifier", ""),
            "url_catalogo": ds.get("_about", ""),
            "formatos": formats,
            "urls_descarga": download_urls,
            "licencia": ds.get("license", ""),
            "fecha_modificacion": ds.get("modified", ""),
        })

    # Sort by comunidad > provincia > municipio > titulo
    rows.sort(key=lambda r: (r["comunidad_autonoma"], r["provincia"], r["municipio"], r["titulo"]))

    # Write CSV
    fieldnames = list(rows[0].keys()) if rows else []
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"CSV exportado: {OUTPUT_CSV} ({len(rows)} filas)")

    # Print summary
    print("\n" + "=" * 70)
    print("RESUMEN POR COMUNIDAD AUTÓNOMA / PROVINCIA / MUNICIPIO")
    print("=" * 70)

    by_ccaa: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in rows:
        ccaa = r["comunidad_autonoma"] or "(sin localizar)"
        by_ccaa[ccaa].append(r)

    total_located = sum(len(v) for k, v in by_ccaa.items() if k != "(sin localizar)")
    total_unlocated = len(by_ccaa.get("(sin localizar)", []))
    print(f"\nLocalizados: {total_located} / {len(rows)}  |  Sin localizar: {total_unlocated}")

    for ccaa in sorted(by_ccaa):
        items = by_ccaa[ccaa]
        print(f"\n{'━' * 60}")
        print(f"  {ccaa} ({len(items)} datasets)")
        print(f"{'━' * 60}")

        by_prov: dict[str, list[dict[str, str]]] = defaultdict(list)
        for r in items:
            prov = r["provincia"] or "(sin provincia)"
            by_prov[prov].append(r)

        for prov in sorted(by_prov):
            prov_items = by_prov[prov]
            print(f"\n    📍 {prov} ({len(prov_items)} datasets)")

            by_muni: dict[str, list[dict[str, str]]] = defaultdict(list)
            for r in prov_items:
                muni = r["municipio"] or "(nivel provincial/autonómico)"
                by_muni[muni].append(r)

            for muni in sorted(by_muni):
                muni_items = by_muni[muni]
                if muni != "(nivel provincial/autonómico)":
                    print(f"      🏘  {muni} ({len(muni_items)}):")
                else:
                    print(f"      {muni}:")
                for r in muni_items:
                    pub = r["publicador_nombre"]
                    fmts = r["formatos"][:40] if r["formatos"] else "?"
                    print(f"        • {r['titulo'][:75]}")
                    print(f"          [{pub}] Formatos: {fmts}")

    client.close()


if __name__ == "__main__":
    main()
