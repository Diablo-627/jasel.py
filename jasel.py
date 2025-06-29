from flask import Flask, render_template_string
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import re
import requests
import os
import hashlib
import time

# Настройка доступа к Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("/etc/secrets/your_key.json", scope)
client = gspread.authorize(creds)

SPREADSHEET_KEY = "1qZfhq1E9CzxWv1tUUDDr4dVDfu4cZ53pEA2lESkVW1E"
SHEET_NAME = "АДРЕСА"

last_row_hashes = {}
last_url_results = {}

app = Flask(__name__)

@app.route("/")
def map_view():
    sheet = client.open_by_key(SPREADSHEET_KEY).worksheet(SHEET_NAME)
    rows = sheet.get_all_values()[1:]  # Пропустить заголовок

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
            photo = row[6] if len(row) > 6 and row[6].startswith("http") else None
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

            info_html = f"""
            👤 Координатор: {coordinator}<br>
            📍 Адрес: {address}<br>
            🧹 Мусор: {trash_type}<br>
            📦 Детали: {details}<br>
            🔗 <a href='{url}' target='_blank'>2ГИС</a><br>
            """
            if photo:
                info_html += f"🖼 <a href='{photo}' target='_blank'>Фото</a><br>"

            points.append({
                "lat": lat,
                "lng": lon,
                "color": color,
                "info": info_html.strip(),
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
        <meta charset='utf-8'>
        <script src="https://maps.googleapis.com/maps/api/js?key=AIzaSyBQok61N3EKdXRtH1PJm3Ol-VznF8-PgNo&libraries=places"></script>
        <style>
            #map { height: 600px; width: 100%; }
            .controls { text-align:center; margin-bottom: 10px; }
            button { margin: 5px; padding: 8px 14px; font-size: 14px; }
        </style>
    </head>
    <body>
        <h2 style="text-align:center;">🗺️ Карта точек вывоза (Жасыл Ел)</h2>
        <div class="controls">
            <label><input type="checkbox" id="greenToggle" checked onchange="toggleGreenMarkers()"> Показывать зелёные метки (вывезено)</label><br>
            <button onclick="startRouteSelection()">Построить маршрут</button>
            <button onclick="resetAll()">Сбросить</button>
            <button onclick="startPrioritySelection()">Назначить приоритет</button>
        </div>
        <div id="map"></div>

        <script>
            let allMarkers = [];
            let selectedMarkers = [];
            let priorityMarkers = [];
            let selectingRoute = false;
            let selectingPriority = false;
            let currentInfoWindow = null;

            function initMap() {
                let map = new google.maps.Map(document.getElementById('map'), {
                    zoom: 13,
                    center: {lat: 50.05, lng: 72.95}
                });

                let points = {{ points | safe }};

                for (let i = 0; i < points.length; i++) {
                    let marker = new google.maps.Marker({
                        position: {lat: points[i].lat, lng: points[i].lng},
                        map: map,
                        icon: getIcon(points[i].color)
                    });

                    marker.customData = points[i];

                    let infowindow = new google.maps.InfoWindow({ content: points[i].info });

                    marker.addListener('click', function() {
                        if (currentInfoWindow) currentInfoWindow.close();
                        currentInfoWindow = infowindow;
                        infowindow.open(map, marker);

                        if (selectingRoute) toggleMarkerSelection(marker, selectedMarkers, 'blue');
                        else if (selectingPriority) toggleMarkerSelection(marker, priorityMarkers, 'orange');
                    });

                    allMarkers.push(marker);
                }
            }

            function toggleGreenMarkers() {
                let checkbox = document.getElementById('greenToggle');
                allMarkers.forEach(marker => {
                    if (marker.customData.color === "green") {
                        marker.setVisible(checkbox.checked);
                    }
                });
            }

            function getIcon(color) {
                return {
                    path: google.maps.SymbolPath.CIRCLE,
                    scale: 8,
                    fillColor: color,
                    fillOpacity: 1,
                    strokeWeight: 1,
                    strokeColor: "#000"
                };
            }

            function toggleMarkerSelection(marker, list, highlightColor) {
                let idx = list.indexOf(marker);
                if (idx > -1) {
                    list.splice(idx, 1);
                    marker.setIcon(getIcon(marker.customData.color));
                } else {
                    list.push(marker);
                    marker.setIcon(getIcon(highlightColor));
                }
            }

            function startRouteSelection() {
                if (!selectingRoute) {
                    alert("Выберите минимум 2 точки для маршрута, затем снова нажмите 'Построить маршрут'");
                    selectingRoute = true;
                    selectedMarkers = [];
                } else {
                    selectingRoute = false;
                    if (selectedMarkers.length < 2) return alert("Мало точек для маршрута");
                    let coords = selectedMarkers.map(m => m.getPosition().toUrlValue()).join("|");
                    window.open("https://www.google.com/maps/dir/" + coords);
                }
            }

            function startPrioritySelection() {
                if (!selectingPriority) {
                    alert("Выберите приоритетные точки, затем снова нажмите 'Назначить приоритет'");
                    selectingPriority = true;
                    priorityMarkers = [];
                } else {
                    selectingPriority = false;
                    priorityMarkers.forEach(marker => marker.setIcon(getIcon("orange")));
                }
            }

            function resetAll() {
                selectingRoute = false;
                selectingPriority = false;
                selectedMarkers = [];
                priorityMarkers = [];
                allMarkers.forEach(marker => marker.setIcon(getIcon(marker.customData.color)));
                if (currentInfoWindow) currentInfoWindow.close();
            }
        </script>
    </body>
    </html>
    """
    return render_template_string(html_template, points=points)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
