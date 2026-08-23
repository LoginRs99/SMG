# SMG Bot

Automatizációs bot Docker és helyi környezetre.

## Használat Dockerrel

1. Konfiguráció létrehozása:
   ```bash
   cp .env.example .env
   ```
   Töltsd ki a `.env` fájlban a `COOKIE` értékét.

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
