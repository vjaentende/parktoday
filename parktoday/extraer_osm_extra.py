#!/usr/bin/env python3
"""
Query OpenStreetMap Overpass API for additional parking-related data in Spain.
Covers: parking_entrance, parking_space, parking_lane, parking:condition,
        vending=parking_tickets, leisure=pitch+sport=parking
"""

import subprocess
import json
import csv
import time
import os
import sys

WORKDIR = "/Users/victorjaenruiz/parktoday"
ENDPOINT = "https://overpass.kumi.systems/api/interpreter"
TIMEOUT = 300
PAUSE = 30  # seconds between queries

# Spain split into quadrants + Canarias
REGIONS = {
    "SW": "(35.9,-9.4,39.8,-0.5)",
    "NW": "(39.8,-9.4,43.8,-0.5)",
    "SE": "(35.9,-0.5,39.8,4.4)",
    "NE": "(39.8,-0.5,43.8,4.4)",
    "Canarias": "(27.5,-18.3,29.5,-13.3)",
}

# Define queries - each returns nwr (nodes, ways, relations) with out center for ways/rels
QUERIES = {
    "parking_entrance": """
[out:json][timeout:{timeout}];
(
  nwr["amenity"="parking_entrance"]{bbox};
);
out center tags;
""",
    "parking_space": """
[out:json][timeout:{timeout}];
(
  nwr["amenity"="parking_space"]{bbox};
);
out center tags;
""",
    "parking_lane": """
[out:json][timeout:{timeout}];
(
  way["parking:lane"]{bbox};
  way["parking:lane:left"]{bbox};
  way["parking:lane:right"]{bbox};
  way["parking:lane:both"]{bbox};
);
out center tags;
""",
    "parking_condition": """
[out:json][timeout:{timeout}];
(
  nwr["parking:condition"]{bbox};
  nwr["parking:condition:left"]{bbox};
  nwr["parking:condition:right"]{bbox};
  nwr["parking:condition:both"]{bbox};
);
out center tags;
""",
    "vending_parking_tickets": """
[out:json][timeout:{timeout}];
(
  nwr["vending"="parking_tickets"]{bbox};
);
out center tags;
""",
    "leisure_pitch_parking": """
[out:json][timeout:{timeout}];
(
  nwr["leisure"="pitch"]["sport"="parking"]{bbox};
);
out center tags;
""",
}


def run_overpass_query(query_text, output_file):
    """Run an Overpass query using curl and save to file."""
    cmd = [
        "curl", "-s", "-S", "--max-time", str(TIMEOUT + 60),
        "-X", "POST",
        "-d", f"data={query_text}",
        "-o", output_file,
        "-w", "%{http_code}",
        ENDPOINT
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT + 120)
    http_code = result.stdout.strip()
    if result.returncode != 0:
        print(f"  ERROR: curl failed: {result.stderr}")
        return False
    if http_code != "200":
        print(f"  ERROR: HTTP {http_code}")
        # Print first 500 chars of response for debugging
        try:
            with open(output_file, 'r') as f:
                print(f"  Response: {f.read(500)}")
        except:
            pass
        return False
    # Validate JSON
    try:
        with open(output_file, 'r') as f:
            data = json.load(f)
        n = len(data.get("elements", []))
        print(f"  OK: {n} elements")
        return True
    except json.JSONDecodeError as e:
        print(f"  ERROR: Invalid JSON: {e}")
        return False


def is_portugal(lat, lon):
    """Filter out Portugal: lon < -6.2 AND 37.0 < lat < 42.2"""
    return lon < -6.2 and 37.0 < lat < 42.2


def extract_center(element):
    """Get lat/lon from element (node or way/relation with center)."""
    if element["type"] == "node":
        return element.get("lat"), element.get("lon")
    elif "center" in element:
        return element["center"].get("lat"), element["center"].get("lon")
    return None, None


def extract_parking_tags(tags):
    """Extract parking-specific tags into structured fields."""
    result = {
        "parking_condition": "",
        "time_limit": "",
        "fee": "",
        "maxstay": "",
        "zone_type": "",
        "parking_lane_type": "",
        "access": "",
        "capacity": "",
        "operator": "",
        "opening_hours": "",
        "surface": "",
        "ref": "",
        "other_parking_tags": "",
    }

    other = []
    for k, v in tags.items():
        kl = k.lower()
        if "parking:condition" in kl:
            if result["parking_condition"]:
                result["parking_condition"] += "; "
            result["parking_condition"] += f"{k}={v}"
        elif "parking:lane" in kl:
            if result["parking_lane_type"]:
                result["parking_lane_type"] += "; "
            result["parking_lane_type"] += f"{k}={v}"
        elif kl == "maxstay":
            result["maxstay"] = v
        elif kl == "fee":
            result["fee"] = v
        elif kl in ("zone", "zone:type", "parking:zone", "zone:traffic"):
            result["zone_type"] = v
        elif kl == "access":
            result["access"] = v
        elif kl == "capacity":
            result["capacity"] = v
        elif kl == "operator":
            result["operator"] = v
        elif kl == "opening_hours":
            result["opening_hours"] = v
        elif kl == "surface":
            result["surface"] = v
        elif kl == "ref":
            result["ref"] = v
        elif kl.startswith("parking") or kl.startswith("zone") or kl in ("time_limit",):
            other.append(f"{k}={v}")

    result["other_parking_tags"] = "; ".join(other)
    return result


def process_all():
    os.makedirs(f"{WORKDIR}/osm_extra_raw", exist_ok=True)

    all_elements = []  # (tipo_tag, element)
    query_count = 0
    total_queries = len(QUERIES) * len(REGIONS)

    for qname, qtemplate in QUERIES.items():
        for rname, bbox in REGIONS.items():
            query_count += 1
            outfile = f"{WORKDIR}/osm_extra_raw/{qname}_{rname}.json"

            # Skip if already downloaded successfully
            if os.path.exists(outfile):
                try:
                    with open(outfile, 'r') as f:
                        data = json.load(f)
                    n = len(data.get("elements", []))
                    if n >= 0:
                        print(f"[{query_count}/{total_queries}] {qname} / {rname}: CACHED ({n} elements)")
                        continue
                except:
                    pass

            query = qtemplate.replace("{timeout}", str(TIMEOUT)).replace("{bbox}", bbox)
            print(f"[{query_count}/{total_queries}] {qname} / {rname}...", end=" ", flush=True)

            success = run_overpass_query(query, outfile)
            if not success:
                # Retry once after longer wait
                print(f"  Retrying in 60s...")
                time.sleep(60)
                print(f"  Retry:", end=" ", flush=True)
                run_overpass_query(query, outfile)

            # Wait between queries to avoid rate limiting
            if query_count < total_queries:
                print(f"  Waiting {PAUSE}s...")
                time.sleep(PAUSE)

    # Now load all results
    print("\n=== Loading all results ===")
    seen_ids = set()

    for qname in QUERIES:
        count = 0
        for rname in REGIONS:
            outfile = f"{WORKDIR}/osm_extra_raw/{qname}_{rname}.json"
            if not os.path.exists(outfile):
                continue
            try:
                with open(outfile, 'r') as f:
                    data = json.load(f)
                for el in data.get("elements", []):
                    osm_id = f"{el['type'][0]}{el['id']}"
                    if osm_id in seen_ids:
                        continue
                    lat, lon = extract_center(el)
                    if lat is None:
                        continue
                    if is_portugal(lat, lon):
                        continue
                    seen_ids.add(osm_id)
                    all_elements.append((qname, el, lat, lon))
                    count += 1
            except Exception as e:
                print(f"  Error loading {outfile}: {e}")
        print(f"  {qname}: {count} unique elements (after dedup & Portugal filter)")

    # Write CSV
    print(f"\n=== Writing CSV ({len(all_elements)} total elements) ===")
    csv_path = f"{WORKDIR}/parkings_osm_extra.csv"

    fieldnames = [
        "osm_id", "tipo_tag", "nombre", "lat", "lon",
        "parking_condition", "parking_lane_type", "time_limit", "fee",
        "maxstay", "zone_type", "access", "capacity", "operator",
        "opening_hours", "surface", "ref", "other_parking_tags"
    ]

    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for tipo, el, lat, lon in all_elements:
            tags = el.get("tags", {})
            osm_id = f"{el['type'][0]}{el['id']}"

            ptags = extract_parking_tags(tags)

            row = {
                "osm_id": osm_id,
                "tipo_tag": tipo,
                "nombre": tags.get("name", ""),
                "lat": lat,
                "lon": lon,
            }
            row.update(ptags)
            writer.writerow(row)

    print(f"\nSaved to {csv_path}")

    # Summary
    print("\n=== SUMMARY ===")
    from collections import Counter
    counter = Counter(t for t, _, _, _ in all_elements)
    for tag, cnt in counter.most_common():
        print(f"  {tag}: {cnt}")
    print(f"  TOTAL: {len(all_elements)}")


if __name__ == "__main__":
    process_all()
