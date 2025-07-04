from flask import Flask, render_template_string
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import re
import requests
import os
import hashlib
import time

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
    try:
        sheet = client.open_by_key(SPREADSHEET_KEY).worksheet(SHEET_NAME)
        rows = sheet.get_all_values()[1:]

        points = []
        processed = 0
        skipped = 0

        for row in rows:
            try:
                if len(row) < 10 or not row[5].startswith("http"):
                    skipped += 1
                    continue

                coordinator = row[1]
                address = row[2]
                trash_type = row[3]
                details = row[4]
                url = row[5]
                photo_link = row[7].strip() if len(row) > 7 else ""
                status = row[9].strip().lower() if len(row) > 9 else ""
                priority = row[10].strip().lower() if len(row) > 10 else ""

                row_data = f"{coordinator}|{address}|{trash_type}|{details}|{url}|{status}|{photo_link}|{priority}"
                row_hash = hashlib.md5(row_data.encode()).hexdigest()

                if row_hash in last_row_hashes:
                    final_url = last_url_results[row_hash]
                else:
                    try:
                        r = requests.get(url, allow_redirects=True, timeout=3)
                        final_url = r.url
                    except requests.exceptions.RequestException as e:
                        print(f"[!] Ошибка при загрузке {url}: {e}")
                        skipped += 1
                        continue

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

                color = "green" if status == "true" else ("orange" if priority == "true" else "red")

                info_html = f"👤 Координатор: {coordinator}<br>📍 Адрес: {address}<br>🧹 Мусор: {trash_type}<br>📦 Детали: {details}<br>🔗 <a href='{url}' target='_blank'>2ГИС</a>"
                if photo_link:
                    info_html += f"<br>📷 <a href='{photo_link}' target='_blank'>Фото</a>"

                points.append({
                    "lat": lat,
                    "lng": lon,
                    "color": color,
                    "info": info_html
                })
                processed += 1

            except Exception as e:
                print("[!] Ошибка при обработке строки:", e)
                skipped += 1
                continue

        print(f"[INFO] Карта запрошена. Всего строк: {len(rows)} | Успешных точек: {processed} | Пропущено: {skipped}")

        return render_template_string(html_template, points=points)

    except Exception as e:
        print("🔴 Ошибка в map_view:", e)
        import traceback
        print(traceback.format_exc())
        return "Внутренняя ошибка сервера", 500

html_template = """
<!DOCTYPE html>
<html>
<head>
    <title>Карта точек вывоза — Жасыл Ел</title>
    <meta charset="utf-8" />
    <script src="https://maps.googleapis.com/maps/api/js?key=AIzaSyBQok61N3EKdXRtH1PJm3Ol-VznF8-PgNo"></script>
    <style>
        #map { height: 600px; width: 100%; }
        #controls { text-align:center; margin-top:10px; }
        button, label {
            font-size: 18px;
            padding: 10px 15px;
            margin: 5px;
        }
    </style>
    <script>
        let allMarkers = [];
        let infoWindow = null;
        let priorityMode = false;
        let routeSelectMode = false;
        let priorityPoints = new Set();
        let routePoints = new Set();
        let routePolyline = null;
        let map;

        function initMap() {
            map = new google.maps.Map(document.getElementById('map'), {
                zoom: 13,
                center: {lat: 50.05, lng: 72.95}
            });

            var points = {{ points | safe }};

            infoWindow = new google.maps.InfoWindow();

            for (let i = 0; i < points.length; i++) {
                let pt = points[i];
                let marker = new google.maps.Marker({
                    position: {lat: pt.lat, lng: pt.lng},
                    map: map,
                    icon: {
                        path: google.maps.SymbolPath.CIRCLE,
                        scale: 8,
                        fillColor: pt.color,
                        fillOpacity: 1,
                        strokeWeight: 1,
                        strokeColor: "#000"
                    }
                });

                marker.priority = false;
                marker.routeSelected = false;
                marker.index = i;
                marker.infoContent = pt.info;

                marker.addListener('click', function() {
                    if(priorityMode) {
                        togglePriority(marker);
                        return;
                    }
                    if(routeSelectMode) {
                        toggleRouteSelection(marker);
                        return;
                    }
                    infoWindow.close();
                    infoWindow.setContent(marker.infoContent);
                    infoWindow.open(map, marker);
                });

                allMarkers.push(marker);
            }
        }

        function togglePriority(marker) {
            if(marker.priority) {
                marker.priority = false;
                marker.setIcon({
                    path: google.maps.SymbolPath.CIRCLE,
                    scale: 8,
                    fillColor: marker.routeSelected ? 'blue' : 'red',
                    fillOpacity: 1,
                    strokeWeight: 1,
                    strokeColor: "#000"
                });
                priorityPoints.delete(marker.index);
            } else {
                marker.priority = true;
                marker.setIcon({
                    path: google.maps.SymbolPath.CIRCLE,
                    scale: 10,
                    fillColor: 'orange',
                    fillOpacity: 1,
                    strokeWeight: 2,
                    strokeColor: "#000"
                });
                priorityPoints.add(marker.index);
            }
        }

        function toggleRouteSelection(marker) {
            if(marker.routeSelected) {
                marker.routeSelected = false;
                marker.setIcon({
                    path: google.maps.SymbolPath.CIRCLE,
                    scale: 8,
                    fillColor: marker.priority ? 'orange' : 'red',
                    fillOpacity: 1,
                    strokeWeight: 1,
                    strokeColor: "#000"
                });
                routePoints.delete(marker.index);
            } else {
                marker.routeSelected = true;
                marker.setIcon({
                    path: google.maps.SymbolPath.CIRCLE,
                    scale: 8,
                    fillColor: 'blue',
                    fillOpacity: 1,
                    strokeWeight: 2,
                    strokeColor: "#000"
                });
                routePoints.add(marker.index);
            }
        }

        function togglePriorityMode() {
            priorityMode = !priorityMode;
            if(priorityMode) {
                routeSelectMode = false;
                document.getElementById('priorityBtn').style.backgroundColor = '#ffa500';
                document.getElementById('routeSelectBtn').style.backgroundColor = '';
                infoWindow.close();
            } else {
                document.getElementById('priorityBtn').style.backgroundColor = '';
            }
        }

        function toggleRouteSelectionMode() {
            routeSelectMode = !routeSelectMode;
            if(routeSelectMode) {
                priorityMode = false;
                document.getElementById('routeSelectBtn').style.backgroundColor = '#00f';
                document.getElementById('priorityBtn').style.backgroundColor = '';
                infoWindow.close();
            } else {
                document.getElementById('routeSelectBtn').style.backgroundColor = '';
            }
        }

        function buildRoute() {
            if(routePoints.size < 2) {
                alert("Выберите минимум 2 точки для маршрута");
                return;
            }
            if(routePolyline) {
                routePolyline.setMap(null);
            }

            let pathCoords = [];
            routePoints.forEach(idx => {
                let m = allMarkers[idx];
                pathCoords.push(m.getPosition());
            });

            routePolyline = new google.maps.Polyline({
                path: pathCoords,
                geodesic: true,
                strokeColor: '#0000FF',
                strokeOpacity: 0.8,
                strokeWeight: 4
            });
            routePolyline.setMap(map);
        }

        function resetMap() {
            infoWindow.close();
            priorityMode = false;
            routeSelectMode = false;
            document.getElementById('priorityBtn').style.backgroundColor = '';
            document.getElementById('routeSelectBtn').style.backgroundColor = '';
            if(routePolyline) {
                routePolyline.setMap(null);
                routePolyline = null;
            }
            priorityPoints.clear();
            routePoints.clear();
            allMarkers.forEach(marker => {
                marker.priority = false;
                marker.routeSelected = false;
                marker.setIcon({
                    path: google.maps.SymbolPath.CIRCLE,
                    scale: 8,
                    fillColor: 'red',
                    fillOpacity: 1,
                    strokeWeight: 1,
                    strokeColor: "#000"
                });
            });
        }

        function toggleGreenMarkers() {
            let checkbox = document.getElementById('greenToggle');
            allMarkers.forEach(marker => {
                if(marker.priority) return;
                if(marker.routeSelected) return;
                if(marker.getIcon().fillColor === "green" || marker.getIcon().fillColor === "#008000") {
                    marker.setVisible(checkbox.checked);
                }
            });
        }
    </script>
</head>
<body onload="initMap()">
    <h2 style="text-align:center;">🗺️ Карта точек вывоза (Жасыл Ел)</h2>
    <div id="map"></div>
    <div id="controls">
        <label><input type="checkbox" id="greenToggle" checked onchange="toggleGreenMarkers()"> Показывать зелёные метки (вывезено)</label>
        <button id="priorityBtn" onclick="togglePriorityMode()">Назначить приоритет</button>
        <button id="routeSelectBtn" onclick="toggleRouteSelectionMode()">Выбрать точки маршрута</button>
        <button onclick="buildRoute()">Построить маршрут</button>
        <button onclick="resetMap()">Сбросить</button>
    </div>
</body>
</html>
"""

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
