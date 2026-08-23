# SMG

Automatizációs bot Docker és helyi környezetre.

## Használat Dockerrel

1. Konfiguráció létrehozása:
   ```bash
   cp config/config.ini.example config/config.ini
   ```
   Töltsd ki a `config/config.ini` fájlt a szükséges adatokkal.

2. Indítás:
   ```bash
   docker compose up -d
   ```

3. Naplók megtekintése:
   ```bash
   docker compose logs -f
   ```

## Helyi futtatás

```bash
pip install -r requirements.txt
python -m smg_bot.main
```
