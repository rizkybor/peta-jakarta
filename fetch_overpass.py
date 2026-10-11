import json, sys, time, requests
outdir = sys.argv[1]
H = {"User-Agent": "jakarta-a3-map/1.0", "Accept": "*/*"}
URLS = ["https://overpass-api.de/api/interpreter", "https://overpass.private.coffee/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
def run(q, name):
    for attempt in range(3):
        for url in URLS:
            try:
                r = requests.post(url, data={"data": q}, timeout=300, headers=H)
                r.raise_for_status()
                d = r.json()
                json.dump(d, open(f"{outdir}/{name}.json", "w"))
                print("ok", name, url, len(d["elements"])); return
            except Exception as e:
                print("fail", name, url, str(e)[:80])
        time.sleep(10)
    sys.exit(f"gave up {name}")
HW = "^(motorway|trunk|primary|secondary|tertiary|motorway_link|trunk_link|primary_link)$"
lats = [-6.38, -6.23, -6.08]; lons = [106.68, 106.83, 106.98]
for i in range(2):
    for j in range(2):
        b = f"({lats[i]},{lons[j]},{lats[i+1]},{lons[j+1]})"
        run(f'[out:json][timeout:180];way["highway"~"{HW}"]{b};out geom qt;', f"roads_{i}{j}")
        time.sleep(3)
run('[out:json][timeout:180];relation["boundary"="administrative"]["admin_level"~"^(4|5)$"](-6.40,106.66,-6.06,107.00);out geom;', "bounds")
run('[out:json][timeout:120];(way["natural"="coastline"](-6.15,106.66,-6.0,107.0););out geom qt;', "coast")
