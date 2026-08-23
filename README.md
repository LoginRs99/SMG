# SMG Bot 🤖

Modern, megbízható és moduláris ajándéksorsolás-automatizációs bot 24/7-es Docker futtatásra tervezve.

---

## 🌟 Főbb funkciók

- **Automatikus részvétel:** Kívánságlista, ajánlott elemek, csoportos sorsolások és egyéb egyéni kategóriák intelligens kezelése.
- **Special Mode:** Ciklikusan körbejárja a beállított kategóriákat (`Wishlist`, `Group`, `Recommended`, `Copies`, `DLC`).
- **WonCache:** Helyi perzisztens gyorsítótár (`logs/won_cache.json`) a korábban megnyert tételek felesleges hálózati kérések nélküli szűrésére.
- **Dinamikus pontkezelés:** Intelligens alvási idő kalkuláció az aktuális pontszám és a visszatöltődési ráta alapján.
- **Anti-detection & Stealth:**
  - Kérésenkénti böngésző User-Agent rotáció.
  - Szigorú, kérések közötti minimum intervallum (`min_request_interval = 5.0s`).
  - $\pm 20\%$ véletlenszerű időzítési szórás (jitter) és emberi késleltetések (`human_delay`).
  - 15%-os véletlenszerű kihagyás a természetes felhasználói viselkedés szimulációjához.
- **Zero-Crash Hot-Reload:** Munkamenet-lejárat esetén IDLE készenlétbe áll, és automatikusan betölti a frissített konfigurációt konténer-újraindítás nélkül.
- **Exponenciális hibakezelés:** Hálózati anomáliák esetén dinamikusan növekvő backoff várakozás.
- **Discord integráció:**
  - Napi statisztikai összesítő (üzemidő, sikerességi ráta, pontgazdaság).
  - Nyeremény-értesítések perzisztens deduplikációval (`notified_wins.json`).
  - Munkamenet-lejárat és helyreállítási riasztások.
  - Konfigurálható `@here` említések.
- **Docker & Healthcheck optimalizált:**
  - Heartbeat mechanizmus a hosszú várakozási ciklusok alatt, megelőzve a hamis Docker healthcheck leállásokat.
  - Secret leak védelem: a konfiguráció soha nem kerül az image-be, kizárólag runtime mountként érkezik.

---

## 📁 Projektstruktúra

```text
SMG/
├── config/
│   ├── config.ini.example        # Konfigurációs sablon
│   └── config.ini                # Saját éles beállítások (gitignored!)
├── logs/                         # Naplófájlok és perzisztens cache (gitignored!)
│   └── .gitkeep
├── smg_bot/                      # Moduláris forráskód
│   ├── __init__.py
│   ├── client.py                 # HTTP munkamenet, rate limiting, DOM feldolgozás
│   ├── config.py                 # Konfigurációkezelés, validáció, alapértelmezések
│   ├── giveaway_logic.py         # Szűrés, belépési ciklus, WonCache
│   ├── main.py                   # Belépési pont, ütemezés, vezérlés
│   └── notifier.py               # Discord értesítések és statisztika
├── .dockerignore
├── .gitignore
├── CHANGELOG.md
├── docker-compose.yml
├── Dockerfile
├── README.md
└── requirements.txt
```

---

## 🚀 Használat Dockerrel

### 1. Konfiguráció előkészítése
Másold le a konfigurációs sablont és add meg a hitelesítési adataidat:

```bash
cp config/config.ini.example config/config.ini
```

Nyisd meg a `config/config.ini` fájlt egy szövegszerkesztővel, és töltsd ki a `cookie` (valamint opcionálisan a `discord_webhook`) mezőt.

### 2. Indítás Docker Compose segítségével

```bash
docker compose up -d --build
```

### 3. Naplók követése

```bash
docker compose logs -f
```

---

## 💻 Helyi futtatás (Python 3.9+)

```bash
# Függőségek telepítése
pip install -r requirements.txt

# Bot indítása
python -m smg_bot.main
```
