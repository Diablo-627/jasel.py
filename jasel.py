from flask import Flask, render_template_string
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import re
import requests

# Настройка доступа к Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("/etc/secrets/your_key.json", scope)
client = gspread.authorize(creds)

SPREADSHEET_KEY = "1qZfhq1E9CzxWv1tUUDDr4dVDfu4cZ53pEA2lESkVW1E"
SHEET_NAME = "АДРЕСА"

app = Flask(__name__)

@app.route("/")
def map_view():
    sheet = client.open_by_key(SPREADSHEET_KEY).worksheet(SHEET_NAME)
    rows = sheet.get_all_values()[1:]  # Пропустить заголовок

    points = []
    valid_rows = 0
    for row in rows:
        try:
            if len(row) < 9 or not row[5].startswith("http"):
                continue

            coordinator = row[1]
            address = row[2]
            trash_type = row[3]
            details = row[4]
            url = row[5]
            status = row[8].strip().lower()

            r = requests.get(url, allow_redirects=True)
            final_url = r.url

            match = re.search(r"m=([\d\.]+)[,%]([\d\.]+)", final_url)
            if not match:
                match = re.search(r"/([\d\.]+),([\d\.]+)", final_url.split('?')[0])
            if not match:
                continue

            lon = float(match.group(1))
            lat = float(match.group(2))

            color = "green" if status == "true" else "red"

            points.append({
                "lat": lat,
                "lng": lon,
                "color": color,
                "info": f"👤 {coordinator}<br>📍 {address}<br>🧹 {trash_type}<br>📦 {details}<br>🔗 <a href='{url}' target='_blank'>2ГИС</a>"
            })
            valid_rows += 1
        except Exception as e:
            continue

    print(f"[INFO] Карта запрошена. Всего точек: {len(points)} из {valid_rows} допустимых строк.")

    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Карта точек вывоза — Жасыл Ел</title>
        <meta charset="utf-8">
        <script src="https://maps.googleapis.com/maps/api/js?key=AIzaSyBQok61N3EKdXRtH1PJm3Ol-VznF8-PgNo"></script>
        <script>
        let allMarkers = [];
        let routeLines = [];

        function initMap() {
            const map = new google.maps.Map(document.getElementById('map'), {
                zoom: 13,
                center: {lat: 50.05, lng: 72.95}
            });

            const points = {{ points | safe }};

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
                    infowindow.open(map, marker);
                });

                allMarkers.push({ marker: marker, color: points[i].color, position: marker.getPosition() });
            }
        }

        function toggleGreenMarkers() {
            const checkbox = document.getElementById('greenToggle');
            for (let i = 0; i < allMarkers.length; i++) {
                if (allMarkers[i].color === "green") {
                    allMarkers[i].marker.setVisible(checkbox.checked);
                }
            }
        }

        function buildRoute(groups) {
            // Очистка прошлых маршрутов
            for (let line of routeLines) line.setMap(null);
            routeLines = [];

            const markers = allMarkers.filter(m => m.marker.getVisible());
            if (markers.length === 0) return alert("Нет видимых меток для маршрута");

            const chunkSize = Math.ceil(markers.length / groups);
            for (let g = 0; g < groups; g++) {
                const chunk = markers.slice(g * chunkSize, (g + 1) * chunkSize);
                const path = chunk.map(m => m.position);

                const route = new google.maps.Polyline({
                    path: path,
                    geodesic: true,
                    strokeColor: g === 0 ? "#FF0000" : "#0000FF",
                    strokeOpacity: 1.0,
                    strokeWeight: 4
                });

                route.setMap(allMarkers[0].marker.getMap());
                routeLines.push(route);
            }
        }
        </script>
    </head>
    <body onload="initMap()">
        <h2 style="text-align:center;">🗺️ Карта точек вывоза (Жасыл Ел)</h2>
        <div style="text-align:center; margin-bottom: 10px;">
            <label><input type="checkbox" id="greenToggle" checked onchange="toggleGreenMarkers()"> Показывать зелёные метки</label>
        </div>
        <div style="text-align:center; margin-bottom: 10px;">
            <button onclick="buildRoute(1)">🚛 Построить 1 маршрут</button>
            <button onclick="buildRoute(2)">🚛🚛 Построить 2 маршрута</button>
        </div>
        <div id="map" style="height: 600px; width: 100%;"></div>
    </body>
    </html>
    """

    return render_template_string(html_template, points=points)

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
