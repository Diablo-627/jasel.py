from flask import Flask, render_template_string
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import re
import requests
import os
import hashlib
import time

# Доступ к Google Sheets
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
    rows = sheet.get_all_values()[1:]  # Пропускаем заголовок

    points = []
    processed = 0
    skipped = 0

    for row in rows:
        try:
            # Проверка: достаточно столбцов, URL в 6-м индексе (row[5]), статус в 10-м (row[9]), фото в 7-м (row[6])
            if len(row) < 10 or not row[5].startswith("http"):
                skipped += 1
                continue

            coordinator = row[1]
            address = row[2]
            trash_type = row[3]
            details = row[4]
            url = row[5]
            photo_url = row[6].strip()
            status = row[9].strip().lower()  # теперь статус в 10-м столбце (индекс 9)

            row_data = f"{coordinator}|{address}|{trash_type}|{details}|{url}|{status}|{photo_url}"
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

            # Цвет по статусу
            color = "green" if status == "true" else "red"

            info_html = f"👤 Координатор: {coordinator}<br>📍 Адрес: {address}<br>🧹 Мусор: {trash_type}<br>📦 Детали: {details}<br>🔗 <a href='{url}' target='_blank'>2ГИС</a>"
            if photo_url:
                info_html += f"<br>📷 <a href='{photo_url}' target='_blank'>Фото</a>"

            points.append({
                "lat": lat,
                "lng": lon,
                "color": color,
                "info": info_html
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
        <style>
            #controls {text-align: center; margin-bottom: 10px;}
            button {margin: 0 5px; padding: 6px 12px; font-size: 14px;}
        </style>
        <script>
        let allMarkers = [];
        let currentInfoWindow = null;
        let prioritySetMode = false;
        let priorityMarkers = new Set();

        function initMap() {
            let map = new google.maps.Map(document.getElementById('map'), {
                zoom: 13,
                center: {lat: 50.05, lng: 72.95}
            });

            let points = {{ points | safe }};

            for (let i = 0; i < points.length; i++) {
                let point = points[i];
                let marker = new google.maps.Marker({
                    position: {lat: point.lat, lng: point.lng},
                    map: map,
                    icon: {
                        path: google.maps.SymbolPath.CIRCLE,
                        scale: 8,
                        fillColor: point.color,
                        fillOpacity: 1,
                        strokeWeight: 1,
                        strokeColor: "#000"
                    }
                });

                marker.priority = false;
                marker.defaultColor = point.color;

                let infowindow = new google.maps.InfoWindow({
                    content: point.info
                });

                marker.addListener('click', function() {
                    if (prioritySetMode) {
                        // Переключаем приоритет
                        if (marker.priority) {
                            marker.priority = false;
                            marker.setIcon({
                                path: google.maps.SymbolPath.CIRCLE,
                                scale: 8,
                                fillColor: marker.defaultColor,
                                fillOpacity: 1,
                                strokeWeight: 1,
                                strokeColor: "#000"
                            });
                            priorityMarkers.delete(marker);
                        } else {
                            marker.priority = true;
                            marker.setIcon({
                                path: google.maps.SymbolPath.CIRCLE,
                                scale: 10,
                                fillColor: 'blue',
                                fillOpacity: 1,
                                strokeWeight: 2,
                                strokeColor: "#000"
                            });
                            priorityMarkers.add(marker);
                        }
                    } else {
                        // Открываем инфо окно, закрывая предыдущее
                        if (currentInfoWindow) {
                            currentInfoWindow.close();
                        }
                        infowindow.open(map, marker);
                        currentInfoWindow = infowindow;
                    }
                });

                allMarkers.push(marker);
            }
        }

        function toggleGreenMarkers() {
            let checkbox = document.getElementById('greenToggle');
            for (let i = 0; i < allMarkers.length; i++) {
                if (!allMarkers[i].priority && allMarkers[i].defaultColor === "green") {
                    allMarkers[i].setVisible(checkbox.checked);
                }
            }
        }

        function resetMap() {
            // Сброс приоритетов и цвета маркеров
            priorityMarkers.forEach(marker => {
                marker.priority = false;
                marker.setIcon({
                    path: google.maps.SymbolPath.CIRCLE,
                    scale: 8,
                    fillColor: marker.defaultColor,
                    fillOpacity: 1,
                    strokeWeight: 1,
                    strokeColor: "#000"
                });
            });
            priorityMarkers.clear();

            // Показываем все маркеры
            for (let i = 0; i < allMarkers.length; i++) {
                allMarkers[i].setVisible(true);
            }

            prioritySetMode = false;
            document.getElementById('priorityBtn').innerText = 'Назначить приоритет';
        }

        function togglePriorityMode() {
            prioritySetMode = !prioritySetMode;
            let btn = document.getElementById('priorityBtn');
            if (prioritySetMode) {
                btn.innerText = 'Завершить назначение приоритета';
                alert("Кликните на метки, чтобы назначить или снять приоритет.");
            } else {
                btn.innerText = 'Назначить приоритет';
                alert("Приоритетные точки сохранены. Вы можете строить маршрут.");
            }
        }

        function buildRoute() {
            let selectedMarkers = allMarkers.filter(m => m.getVisible() && (!prioritySetMode));
            if (selectedMarkers.length < 2) {
                alert("Выберите минимум 2 видимые метки для построения маршрута.");
                return;
            }

            // Здесь логика построения маршрута (например, через Google Directions API)
            alert("Маршрут строится для выбранных точек (демо).");
        }
        </script>
    </head>
    <body onload="initMap()">
        <h2 style="text-align:center;">🗺️ Карта точек вывоза (Жасыл Ел)</h2>
        <div id="controls">
            <label><input type="checkbox" id="greenToggle" checked onchange="toggleGreenMarkers()"> Показывать зелёные метки (вывезено)</label>
            <button onclick="buildRoute()">Построить маршрут</button>
            <button onclick="resetMap()">Сбросить</button>
            <button id="priorityBtn" onclick="togglePriorityMode()">Назначить приоритет</button>
        </div>
        <div id="map" style="height: 600px; width: 100%;"></div>
    </body>
    </html>
    """

    return render_template_string(html_template, points=points)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
