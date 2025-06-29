from flask import Flask, render_template_string
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import re
import requests
import os
import hashlib
import time

# Авторизация Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("/etc/secrets/your_key.json", scope)
client = gspread.authorize(creds)

SPREADSHEET_KEY = "1qZfhq1E9CzxWv1tUUDDr4dVDfu4cZ53pEA2lESkVW1E"
SHEET_NAME = "АДРЕСА"

# Кэш
last_row_hashes = {}
last_url_results = {}

app = Flask(__name__)

@app.route("/")
def map_view():
    sheet = client.open_by_key(SPREADSHEET_KEY).worksheet(SHEET_NAME)
    rows = sheet.get_all_values()[1:]

    points = []
    processed = 0
    skipped = 0

    for row in rows:
        try:
            if len(row) < 9 or not row[5].startswith("http"):
                skipped += 1
                continue

            coordinator = row[1]
            address = row[2]
            trash_type = row[3]
            details = row[4]
            url = row[5]
            status = row[8].strip().lower()

            row_data = f"{coordinator}|{address}|{trash_type}|{details}|{url}|{status}"
            row_hash = hashlib.md5(row_data.encode()).hexdigest()

            if row_hash in last_row_hashes:
                final_url = last_url_results[row_hash]
            else:
                r = requests.get(url, allow_redirects=True, timeout=5)
                final_url = r.url
                last_row_hashes[row_hash] = True
                last_url_results[row_hash] = final_url
                time.sleep(0.1)

            match = re.search(r"m=([\d\.]+)[,%]([\d\.]+)", final_url)
            if not match:
                match = re.search(r"/([\d\.]+),([\d\.]+)", final_url.split('?')[0])
            if not match:
                skipped += 1
                continue

            lon = float(match.group(1))
            lat = float(match.group(2))

            color = "green" if status == "true" else "red"

            points.append({
                "lat": lat,
                "lng": lon,
                "color": color,
                "info": f"👤 Координатор: {coordinator}<br>📍 Адрес: {address}<br>🧹 Мусор: {trash_type}<br>📦 Детали: {details}<br>🔗 <a href='{url}' target='_blank'>2ГИС</a>"
            })
            processed += 1

        except Exception as e:
            print("[!] Ошибка:", e)
            skipped += 1
            continue

    print(f"[INFO] Карта запрошена. Всего строк: {len(rows)} | Успешных точек: {processed} | Пропущено: {skipped}")

    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Карта точек вывоза — Жасыл Ел</title>
        <meta charset="utf-8">
        <script src="https://maps.googleapis.com/maps/api/js?key=AIzaSyBQok61N3EKdXRtH1PJm3Ol-VznF8-PgNo"></script>
        <script>
        let allMarkers = [];
        let selectedPoints = [];
        let directionsRenderer;

        function initMap() {
            const map = new google.maps.Map(document.getElementById('map'), {
                zoom: 13,
                center: {lat: 50.05, lng: 72.95}
            });

            directionsRenderer = new google.maps.DirectionsRenderer({ suppressMarkers: true });
            directionsRenderer.setMap(map);

            const points = {{ points | safe }};

            for (let i = 0; i < points.length; i++) {
                let position = {lat: points[i].lat, lng: points[i].lng};
                let marker = new google.maps.Marker({
                    position: position,
                    map: map,
                    icon: {
                        path: google.maps.SymbolPath.CIRCLE,
                        scale: 8,
                        fillColor: points[i].color,
                        fillOpacity: 1,
                        strokeWeight: 1,
                        strokeColor: "#000"
                    }
                });

                let infowindow = new google.maps.InfoWindow({
                    content: points[i].info
                });

                marker.addListener('click', function() {
                    infowindow.open(map, marker);

                    const idx = selectedPoints.findIndex(p => p.lat === position.lat && p.lng === position.lng);
                    if (idx === -1) {
                        selectedPoints.push(position);
                        marker.setIcon({ ...marker.getIcon(), fillColor: "#0000ff" });
                    } else {
                        selectedPoints.splice(idx, 1);
                        marker.setIcon({ ...marker.getIcon(), fillColor: points[i].color });
                    }
                });

                allMarkers.push({ marker: marker, color: points[i].color });
            }
        }

        function toggleGreenMarkers() {
            let checkbox = document.getElementById('greenToggle');
            for (let i = 0; i < allMarkers.length; i++) {
                if (allMarkers[i].color === "green") {
                    allMarkers[i].marker.setVisible(checkbox.checked);
                }
            }
        }

        function buildManualRoute() {
            if (selectedPoints.length < 2) {
                alert("Выберите минимум 2 точки.");
                return;
            }

            const directionsService = new google.maps.DirectionsService();

            const waypoints = selectedPoints.slice(1, -1).map(loc => ({ location: loc, stopover: true }));

            directionsService.route({
                origin: selectedPoints[0],
                destination: selectedPoints[selectedPoints.length - 1],
                waypoints: waypoints,
                travelMode: 'DRIVING'
            }, function(result, status) {
                if (status === 'OK') {
                    directionsRenderer.setDirections(result);
                } else {
                    alert("Ошибка построения маршрута: " + status);
                }
            });
        }
        </script>
    </head>
    <body onload="initMap()">
        <h2 style="text-align:center;">🗺️ Карта точек вывоза (Жасыл Ел)</h2>
        <div style="text-align:center; margin: 10px;">
            <label><input type="checkbox" id="greenToggle" checked onchange="toggleGreenMarkers()"> Показывать зелёные метки (вывезено)</label>
        </div>
        <div style="text-align:center; margin: 10px;">
            <button onclick="buildManualRoute()">🧭 Построить маршрут вручную</button>
        </div>
        <div id="map" style="height: 600px; width: 100%;"></div>
    </body>
    </html>
    """
    return render_template_string(html_template, points=points)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
