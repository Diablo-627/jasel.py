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
        <style>
            #controls {
                text-align: center;
                margin: 10px;
            }
            button {
                margin: 5px;
                padding: 8px 12px;
                font-size: 14px;
            }
        </style>
        <script src="https://maps.googleapis.com/maps/api/js?key=AIzaSyBQok61N3EKdXRtH1PJm3Ol-VznF8-PgNo&libraries=places"></script>
        <script>
        let allMarkers = [];
        let directionsRenderer;
        let directionsService;
        let map;
        let activeInfoWindow = null;
        let priorityMarkers = [];
        let routeMarkers = [];
        let isPrioritySelecting = false;
        let isRouteSelecting = false;

        function initMap() {
            map = new google.maps.Map(document.getElementById('map'), {
                zoom: 13,
                center: {lat: 50.05, lng: 72.95}
            });

            directionsService = new google.maps.DirectionsService();
            directionsRenderer = new google.maps.DirectionsRenderer({ map: map });

            var points = {{ points | safe }};

            for (let i = 0; i < points.length; i++) {
                let marker = new google.maps.Marker({
                    position: {lat: points[i].lat, lng: points[i].lng},
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
                    if (activeInfoWindow) activeInfoWindow.close();
                    infowindow.open(map, marker);
                    activeInfoWindow = infowindow;

                    if (isPrioritySelecting && !priorityMarkers.includes(marker)) {
                        priorityMarkers.push(marker);
                        marker.setIcon({
                            path: google.maps.SymbolPath.BACKWARD_CLOSED_ARROW,
                            scale: 6,
                            fillColor: "#FFD700",
                            fillOpacity: 1,
                            strokeWeight: 1,
                            strokeColor: "#000"
                        });
                    } else if (isRouteSelecting && !routeMarkers.includes(marker)) {
                        routeMarkers.push(marker);
                        marker.setIcon({
                            path: google.maps.SymbolPath.FORWARD_CLOSED_ARROW,
                            scale: 6,
                            fillColor: "#00CED1",
                            fillOpacity: 1,
                            strokeWeight: 1,
                            strokeColor: "#000"
                        });
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

        function togglePriorityMode() {
            if (!isPrioritySelecting) {
                alert("Выберите приоритетные адреса. Повторно нажмите кнопку для завершения.");
                isPrioritySelecting = true;
            } else {
                isPrioritySelecting = false;
                document.getElementById("priorityBtn").disabled = true;
            }
        }

        function toggleRouteMode() {
            if (!isRouteSelecting) {
                alert("Выберите точки маршрута (минимум 2). Затем нажмите снова.");
                isRouteSelecting = true;
            } else {
                isRouteSelecting = false;
                if (routeMarkers.length < 2) {
                    alert("Нужно минимум 2 точки для маршрута!");
                    return;
                }

                let waypoints = routeMarkers.slice(1, -1).map(m => ({
                    location: m.getPosition(),
                    stopover: true
                }));

                directionsService.route({
                    origin: routeMarkers[0].getPosition(),
                    destination: routeMarkers[routeMarkers.length - 1].getPosition(),
                    waypoints: waypoints,
                    travelMode: google.maps.TravelMode.DRIVING
                }, function(result, status) {
                    if (status === 'OK') {
                        directionsRenderer.setDirections(result);
                    } else {
                        alert('Ошибка построения маршрута: ' + status);
                    }
                });

                document.getElementById("routeBtn").disabled = true;
            }
        }

        function resetRoute() {
            directionsRenderer.setDirections({ routes: [] });

            priorityMarkers.forEach(m => m.setIcon({
                path: google.maps.SymbolPath.CIRCLE,
                scale: 8,
                fillColor: "blue",
                fillOpacity: 1,
                strokeWeight: 1,
                strokeColor: "#000"
            }));

            routeMarkers.forEach(m => m.setIcon({
                path: google.maps.SymbolPath.CIRCLE,
                scale: 8,
                fillColor: "blue",
                fillOpacity: 1,
                strokeWeight: 1,
                strokeColor: "#000"
            }));

            priorityMarkers = [];
            routeMarkers = [];
            isPrioritySelecting = false;
            isRouteSelecting = false;
            document.getElementById("priorityBtn").disabled = false;
            document.getElementById("routeBtn").disabled = false;
        }
        </script>
    </head>
    <body onload="initMap()">
        <h2 style="text-align:center;">🗺️ Карта точек вывоза (Жасыл Ел)</h2>
        <div id="controls">
            <label><input type="checkbox" id="greenToggle" checked onchange="toggleGreenMarkers()"> Показывать зелёные метки (вывезено)</label><br>
            <button onclick="togglePriorityMode()" id="priorityBtn">⭐ Назначить приоритет</button>
            <button onclick="toggleRouteMode()" id="routeBtn">📍 Построить маршрут</button>
            <button onclick="resetRoute()">🔄 Сбросить всё</button>
        </div>
        <div id="map" style="height: 600px; width: 100%;"></div>
    </body>
    </html>
    """
    return render_template_string(html_template, points=points)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
