#!/usr/bin/env python3
"""Download parking data files from datos.gob.es catalog CSV."""

import csv
import os
import re
import json
import unicodedata
import httpx
import traceback
from pathlib import Path
from urllib.parse import urlparse

CSV_PATH = "/Users/victorjaenruiz/parktoday/aparcamientos_datos_gob.csv"
OUT_DIR = "/Users/victorjaenruiz/parktoday/datos_gob_descargas"

# Extensions we want to download (data files)
DATA_EXTENSIONS = {'.csv', '.json', '.geojson', '.xls', '.xlsx', '.kml', '.shp', '.zip'}

# Coordinate column name patterns
COORD_PATTERNS = re.compile(
    r'\b(lat|lon|lng|latitude|longitude|latitud|longitud|coord|coordenada|'
    r'geo_point|geopoint|point|ubicacion|posicion|geometry|geojson|'
    r'sdopunto|wkt|the_geom|geom|shape|location|position)\b',
    re.IGNORECASE
)
# Specific x/y patterns (need word boundary to avoid false positives)
XY_PATTERNS = re.compile(r'^[xy]$|^coord[_]?[xy]$|^pos[_]?[xy]$|^utm[_]?[xy]$', re.IGNORECASE)


def slugify(text):
    """Create a safe filename from text."""
    if not text:
        return "unknown"
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    text = re.sub(r'[^\w\s-]', '', text.lower())
    text = re.sub(r'[\s_]+', '_', text.strip())
    return text[:60] or "unknown"


def is_data_url(url):
    """Check if URL points to a downloadable data file (not HTML/WMS/API)."""
    url_lower = url.lower()

    # Skip obvious non-data URLs
    skip_patterns = [
        'wms', 'wfs', 'wmts', 'ogc', 'getmap', 'getcapabilities',
        'getfeature', 'service=', 'request=', 'visor', 'viewer',
        'geoportal', 'callejero', 'mapa', 'visores',
    ]
    for pat in skip_patterns:
        if pat in url_lower:
            return False

    # Check if URL ends with a data extension
    parsed = urlparse(url)
    path = parsed.path.lower()

    # Direct extension match
    for ext in DATA_EXTENSIONS:
        if path.endswith(ext):
            return True

    # Check for download in path (common pattern for data portals)
    if '/download/' in url_lower or 'download' in path.split('/')[-1:]:
        return True

    # URLs with resource/download pattern (CKAN)
    if '/resource/' in url_lower and '/download/' in url_lower:
        return True

    return False


def guess_extension(url, content_type=''):
    """Guess file extension from URL or content type."""
    parsed = urlparse(url)
    path = parsed.path.lower()

    for ext in DATA_EXTENSIONS:
        if path.endswith(ext):
            return ext

    # From content type
    ct = content_type.lower()
    if 'csv' in ct:
        return '.csv'
    if 'json' in ct:
        return '.json'
    if 'excel' in ct or 'spreadsheet' in ct:
        return '.xlsx'
    if 'kml' in ct:
        return '.kml'

    # Default: try to get from last path segment
    last = path.split('/')[-1]
    if '.' in last:
        ext = '.' + last.rsplit('.', 1)[-1]
        if ext in DATA_EXTENSIONS:
            return ext

    return '.dat'


def check_coordinates_csv(filepath):
    """Check if a CSV file contains coordinate columns."""
    try:
        # Try different encodings
        for enc in ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']:
            try:
                with open(filepath, 'r', encoding=enc, errors='replace') as f:
                    # Read first line to get headers
                    sample = f.read(8192)
                    if not sample.strip():
                        return False, []

                    # Try to detect delimiter
                    sniffer = csv.Sniffer()
                    try:
                        dialect = sniffer.sniff(sample[:2048])
                    except csv.Error:
                        dialect = csv.excel

                    f.seek(0)
                    reader = csv.reader(f, dialect)
                    try:
                        headers = next(reader)
                    except StopIteration:
                        return False, []

                    coord_cols = []
                    for h in headers:
                        h_clean = h.strip().strip('"').strip()
                        if COORD_PATTERNS.search(h_clean) or XY_PATTERNS.match(h_clean):
                            coord_cols.append(h_clean)

                    return len(coord_cols) > 0, coord_cols
            except UnicodeDecodeError:
                continue
    except Exception:
        pass
    return False, []


def check_coordinates_json(filepath):
    """Check if a JSON/GeoJSON file contains coordinate data."""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read(100000)  # First 100KB

        data = json.loads(content)

        # GeoJSON detection
        if isinstance(data, dict):
            if data.get('type') in ('FeatureCollection', 'Feature', 'Point', 'MultiPoint',
                                      'LineString', 'MultiLineString', 'Polygon', 'MultiPolygon',
                                      'GeometryCollection'):
                return True, ['GeoJSON geometry']

            # Check for coordinate keys in top-level or first record
            items = data if isinstance(data, list) else [data]
        elif isinstance(data, list) and len(data) > 0:
            items = data[:5]
        else:
            return False, []

        coord_cols = []
        for item in items:
            if isinstance(item, dict):
                for key in item.keys():
                    if COORD_PATTERNS.search(key) or XY_PATTERNS.match(key):
                        coord_cols.append(key)
                # Check nested geometry
                if 'geometry' in item or 'geo_point_2d' in item or 'location' in item:
                    coord_cols.append('nested_geometry')
                break  # Only check first item

        return len(coord_cols) > 0, list(set(coord_cols))
    except (json.JSONDecodeError, Exception):
        pass
    return False, []


def check_coordinates_geojson(filepath):
    """GeoJSON files always have coordinates by definition."""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read(1000)
        if 'coordinates' in content or 'geometry' in content:
            return True, ['GeoJSON coordinates']
    except Exception:
        pass
    return True, ['GeoJSON (assumed)']


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    # Read CSV
    rows = []
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    print(f"Total rows in CSV: {len(rows)}")

    # Extract all URLs and classify
    all_urls = []
    url_metadata = {}  # url -> (municipio, titulo, row_index)

    for i, row in enumerate(rows):
        urls_str = row.get('urls_descarga', '')
        if not urls_str:
            continue

        municipio = row.get('municipio', '').strip()
        publicador = row.get('publicador_nombre', '').strip()
        titulo = row.get('titulo', '').strip()
        source_name = municipio if municipio else publicador

        urls = [u.strip() for u in urls_str.split(' | ') if u.strip()]
        for url in urls:
            all_urls.append(url)
            url_metadata[url] = (source_name, titulo, i)

    print(f"Total URLs found: {len(all_urls)}")

    # Filter to data URLs
    data_urls = [u for u in all_urls if is_data_url(u)]
    print(f"Data URLs (filtered): {len(data_urls)}")

    # Deduplicate
    seen = set()
    unique_data_urls = []
    for u in data_urls:
        if u not in seen:
            seen.add(u)
            unique_data_urls.append(u)

    print(f"Unique data URLs: {len(unique_data_urls)}")

    # Prioritize: CSV and JSON first, then others
    def priority(url):
        path = urlparse(url).path.lower()
        if path.endswith('.csv'):
            return 0
        if path.endswith('.json') or path.endswith('.geojson'):
            return 1
        if path.endswith('.xlsx') or path.endswith('.xls'):
            return 2
        if path.endswith('.kml'):
            return 3
        return 4

    unique_data_urls.sort(key=priority)

    # Download files
    downloaded = []
    failed = []
    used_filenames = set()

    client = httpx.Client(timeout=15.0, follow_redirects=True, verify=False)

    for idx, url in enumerate(unique_data_urls):
        source_name, titulo, _ = url_metadata.get(url, ("unknown", "unknown", 0))
        ext = guess_extension(url)

        # Build filename
        source_slug = slugify(source_name)
        title_slug = slugify(titulo)

        # Also include something from the URL to avoid collisions
        url_filename = urlparse(url).path.split('/')[-1]
        url_slug = slugify(url_filename.rsplit('.', 1)[0] if '.' in url_filename else url_filename)

        base_name = f"{source_slug}_{url_slug}"
        if len(base_name) > 120:
            base_name = base_name[:120]

        filename = f"{base_name}{ext}"

        # Handle duplicates
        counter = 1
        while filename in used_filenames:
            filename = f"{base_name}_{counter}{ext}"
            counter += 1
        used_filenames.add(filename)

        filepath = os.path.join(OUT_DIR, filename)

        print(f"[{idx+1}/{len(unique_data_urls)}] Downloading: {url[:100]}...")

        try:
            resp = client.get(url)
            if resp.status_code == 200:
                content_type = resp.headers.get('content-type', '')

                # Skip if we got an HTML page instead of data
                if 'text/html' in content_type and ext not in ('.html',):
                    # Check if it's really HTML
                    snippet = resp.content[:500].decode('utf-8', errors='replace').lower()
                    if '<html' in snippet or '<!doctype' in snippet:
                        print(f"  -> Skipped (HTML response)")
                        failed.append((url, "HTML response instead of data"))
                        continue

                # Re-guess extension from content type if we got .dat
                if ext == '.dat':
                    new_ext = guess_extension(url, content_type)
                    if new_ext != '.dat':
                        old_filename = filename
                        used_filenames.discard(old_filename)
                        filename = f"{base_name}{new_ext}"
                        while filename in used_filenames:
                            filename = f"{base_name}_{counter}{new_ext}"
                            counter += 1
                        used_filenames.add(filename)
                        filepath = os.path.join(OUT_DIR, filename)

                with open(filepath, 'wb') as f:
                    f.write(resp.content)

                size_kb = len(resp.content) / 1024
                print(f"  -> OK ({size_kb:.1f} KB) -> {filename}")
                downloaded.append((url, filepath, filename, source_name, titulo))
            else:
                print(f"  -> Failed (HTTP {resp.status_code})")
                failed.append((url, f"HTTP {resp.status_code}"))
        except Exception as e:
            print(f"  -> Error: {e}")
            failed.append((url, str(e)))

    client.close()

    print(f"\n{'='*60}")
    print(f"Downloaded: {len(downloaded)} / {len(unique_data_urls)}")
    print(f"Failed: {len(failed)}")

    # Check for coordinates in downloaded files
    files_with_coords = []

    print(f"\nChecking for coordinate data...")
    for url, filepath, filename, source_name, titulo in downloaded:
        ext = os.path.splitext(filename)[1].lower()

        has_coords = False
        coord_cols = []

        if ext == '.csv':
            has_coords, coord_cols = check_coordinates_csv(filepath)
        elif ext == '.json':
            has_coords, coord_cols = check_coordinates_json(filepath)
        elif ext == '.geojson':
            has_coords, coord_cols = check_coordinates_geojson(filepath)
        elif ext == '.kml':
            # KML always has coordinates
            has_coords = True
            coord_cols = ['KML coordinates']
        elif ext in ('.zip', '.shp'):
            # Likely shapefile with coordinates
            has_coords = True
            coord_cols = ['Shapefile (assumed)']

        if has_coords:
            files_with_coords.append((filename, source_name, titulo, coord_cols))
            print(f"  COORDS: {filename} -> {coord_cols}")

    # Write summary
    summary_path = os.path.join(OUT_DIR, "RESUMEN.txt")
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write("=" * 70 + "\n")
        f.write("RESUMEN DE DESCARGAS - datos.gob.es (aparcamientos)\n")
        f.write("=" * 70 + "\n\n")

        f.write(f"Total filas en CSV catalogo:    {len(rows)}\n")
        f.write(f"Total URLs encontradas:         {len(all_urls)}\n")
        f.write(f"URLs de datos (filtradas):      {len(data_urls)}\n")
        f.write(f"URLs unicas de datos:           {len(unique_data_urls)}\n")
        f.write(f"Archivos descargados:           {len(downloaded)}\n")
        f.write(f"Descargas fallidas:             {len(failed)}\n")
        f.write(f"Archivos con coordenadas:       {len(files_with_coords)}\n")

        f.write(f"\n{'='*70}\n")
        f.write("ARCHIVOS CON DATOS GEOGRAFICOS (COORDENADAS)\n")
        f.write("=" * 70 + "\n\n")

        for filename, source_name, titulo, coord_cols in files_with_coords:
            f.write(f"Archivo:    {filename}\n")
            f.write(f"Fuente:     {source_name}\n")
            f.write(f"Titulo:     {titulo}\n")
            f.write(f"Columnas:   {', '.join(coord_cols)}\n")
            f.write(f"\n")

        f.write(f"\n{'='*70}\n")
        f.write("TODOS LOS ARCHIVOS DESCARGADOS\n")
        f.write("=" * 70 + "\n\n")

        for url, filepath, filename, source_name, titulo in downloaded:
            size = os.path.getsize(filepath)
            f.write(f"{filename}  ({size/1024:.1f} KB)  [{source_name}]\n")

        f.write(f"\n{'='*70}\n")
        f.write("DESCARGAS FALLIDAS\n")
        f.write("=" * 70 + "\n\n")

        for url, reason in failed:
            f.write(f"URL: {url}\n")
            f.write(f"Motivo: {reason}\n\n")

    print(f"\nResumen guardado en: {summary_path}")
    print(f"Archivos con coordenadas: {len(files_with_coords)}")


if __name__ == '__main__':
    main()
