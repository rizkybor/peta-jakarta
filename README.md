# peta-jakarta

Peta Jalan & Transportasi DKI Jakarta ukuran A3 landscape (420 × 297 mm),
dibuat dari data OpenStreetMap: jaringan jalan, rel dan stasiun kereta api,
busway TransJakarta (Koridor 1–14) beserta halte, serta MRT Jakarta.
Skala 1 : 125.000 bila dicetak A3 ukuran asli.

```bash
git clone https://github.com/rizkybor/peta-jakarta.git
cd peta-jakarta
```

## Persiapan

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Langkah

1. Unduh data OSM Pulau Jawa (± 900 MB):

   ```bash
   curl -L -o java.osm.pbf https://download.geofabrik.de/asia/indonesia/java-latest.osm.pbf
   ```

2. Ambil data jalan, rel, garis pantai, batas kota, dan nama tempat di Jakarta:

   ```bash
   .venv/bin/python extract.py java.osm.pbf jakarta.json
   ```

3. Ambil koridor busway TransJakarta (Koridor 1–14) dan haltenya, jalur dan
   stasiun MRT Jakarta, serta stasiun kereta api (KRL / KAI):

   ```bash
   .venv/bin/python extract_transjakarta.py java.osm.pbf transjakarta.json
   .venv/bin/python extract_mrt.py java.osm.pbf mrt.json
   .venv/bin/python extract_stations.py java.osm.pbf stations.json
   ```

4. Gambar peta (opsi `--transjakarta`, `--mrt`, dan `--stations` boleh
   dihilangkan):

   ```bash
   mkdir -p output
   .venv/bin/python render.py jakarta.json output/peta-jalan-jakarta-a3 \
       --transjakarta transjakarta.json --mrt mrt.json --stations stations.json
   ```

   Hasilnya `output/peta-jalan-jakarta-a3.pdf` (vektor, siap cetak) dan
   `.png` (300 dpi). Skala peta tepat 1 : 125.000 (1 cm = 1,25 km) bila
   dicetak A3 dengan ukuran asli (100%, bukan "Fit to page").

`fetch_overpass.py` adalah alternatif langkah 1–2 (tanpa busway) lewat Overpass API, tapi
server Overpass sering timeout untuk area sebesar Jakarta.

## Lisensi data

Data peta © kontributor OpenStreetMap, lisensi ODbL
(https://www.openstreetmap.org/copyright).
