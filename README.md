# Ai Scalping Bot - Modular Ready-to-Run (Replit)
## Setup (Replit)
1. Upload this project to Replit (Import the zip or create files manually).
2. In Replit's **Secrets (Environment variables)** add these keys:
   - TELEGRAM_TOKEN
   - TELEGRAM_CHAT_ID
   - MEXC_API_KEY
   - MEXC_SECRET_KEY
3. In the Replit Shell (or package manager) install required packages:
   pip install ccxt requests scikit-learn
4. Run `main.py` (Replit's Run button).
5. Logs are printed to console. DB fallback uses `replit_db_fallback.json` if Replit DB is not available.
