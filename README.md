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

   Tambahkan `--style transit` untuk gaya skema transit: jalan dipudarkan
   abu-abu, sedangkan rel, busway, dan MRT digambar tebal di atasnya:

   ```bash
   .venv/bin/python render.py jakarta.json output/peta-jalan-jakarta-a3-transit \
       --transjakarta transjakarta.json --mrt mrt.json --stations stations.json \
       --style transit
   ```

5. (Opsional) Versi peta orienteering dengan simbologi ISOM 2017 (gaya OCAD /
   OpenOrienteering Mapper). Ambil dulu tutupan lahan (taman, lapangan, sawah,
   hutan kota, badan air, area industri / militer), lalu gambar:

   ```bash
   .venv/bin/python extract_landcover.py java.osm.pbf landcover.json
   .venv/bin/python render_orienteering.py jakarta.json output/peta-jalan-jakarta-a3-orienteering \
       --landcover landcover.json --stations stations.json
   ```

   Tambahkan `--transjakarta` dan `--mrt` agar kereta api, busway, dan MRT
   tetap ditonjolkan di atas peta orienteering (seperti `--style transit`):

   ```bash
   .venv/bin/python render_orienteering.py jakarta.json output/peta-jalan-jakarta-a3-orienteering-transit \
       --landcover landcover.json --stations stations.json \
       --transjakarta transjakarta.json --mrt mrt.json
   ```

   Opsi `--scale 100000` mencetak peta orienteering pada skala 1 : 100.000.
   Bidang peta dilebarkan menjadi 296 mm, sehingga pinggiran Jakarta (terutama
   ujung selatan) sedikit terpotong. Tambahkan `--rail-symbol` agar rel kereta
   memakai simbol rel ISOM 515 (garis dengan bantalan melintang) alih-alih garis
   abu tebal; jalur rel ganda / paralel digambar satu garis per koridor.

   ```bash
   .venv/bin/python render_orienteering.py jakarta.json output/peta-jalan-jakarta-a3-orienteering-transit-100k \
       --landcover landcover.json --stations stations.json \
       --transjakarta transjakarta.json --mrt mrt.json --scale 100000 --rail-symbol
   ```

   Opsi `--isom` mengikuti dokumen IOF ISOM 2017-2 (revisi Januari 2024) lebih
   ketat: kode, warna, dan lebar simbol dalam mm (502/503 jalan, 509 rel kereta
   — digambar 200% agar menonjol, 301 air bertepi hitam, 304 sungai 0,30 mm,
   406/408 vegetasi, 520 area tidak boleh dimasuki bertepi hitam, 601 garis
   utara biru 0,12 mm), teks menghadap utara, serta info interval kontur dan
   spesifikasi di tepi peta:

   ```bash
   .venv/bin/python render_orienteering.py jakarta.json output/jakarta-orienteering-100kScale-isom2017-2 \
       --landcover landcover.json --stations stations.json \
       --transjakarta transjakarta.json --mrt mrt.json --scale 100000 --isom \
       --logo "Logo Full Color.png"
   ```

   `--logo` menaruh logo event di bagian atas sidebar.

`fetch_overpass.py` adalah alternatif langkah 1–2 (tanpa busway) lewat Overpass API, tapi
server Overpass sering timeout untuk area sebesar Jakarta.

## Lisensi data

Data peta © kontributor OpenStreetMap, lisensi ODbL
(https://www.openstreetmap.org/copyright).
