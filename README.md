# SRM Chatbots API

## Gemini setup

Chat and public widgets use the Gemini Developer API. Ollama is no longer needed.

1. Create an API key at https://aistudio.google.com/apikey. A project identifier
   such as `gen-lang-client-...` is not an API key.
2. Set these values in this backend directory's `.env`:

   ```dotenv
   GEMINI_API_KEY=your_actual_api_key
   GEMINI_MODEL=gemini-2.5-flash-lite
   ```

   Keep the key on the backend; never put it in frontend environment variables.
   Google lists Flash-Lite with a free tier, subject to quotas. Free usage depends
   on the project's billing tier: https://ai.google.dev/gemini-api/docs/pricing.
3. With the backend virtual environment active, run `python manage.py migrate`
   to update existing agents' stored model names, then restart the Django server.

Existing local model names fall back to `GEMINI_MODEL` until migrated. Agents
with a Gemini model name use that model explicitly. Provider errors, exhausted
quotas, blocked responses, and missing credentials return a generic HTTP 503
without exposing the key or provider response to clients.
