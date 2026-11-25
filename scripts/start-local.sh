#!/bin/zsh
set -euo pipefail
project_dir="$(cd "$(dirname "$0")/.." && pwd)"
runtime_dir="$project_dir/.deploy/local-preview"
"$runtime_dir/services/start-services.sh"
export SQL_DB_URL=postgresql+asyncpg://postgres@127.0.0.1:55432/erp_local_preview
export REDIS_URL=redis://127.0.0.1:56379/9
export SECRET_KEY="$(cat "$runtime_dir/signing-key")"
export CAPTCHA_ENABLE="${CAPTCHA_ENABLE:-false}" SERVER_HOST=127.0.0.1 SERVER_PORT=8080
export ADMIN_USERNAME=admin ADMIN_PASSWORD="$(cat "$runtime_dir/admin-password")"
"$runtime_dir/venv/bin/python" - <<'PYCODE'
import asyncio, asyncpg
async def main():
    conn = await asyncpg.connect("postgresql://postgres@127.0.0.1:55432/postgres")
    try:
        if not await conn.fetchval("SELECT 1 FROM pg_database WHERE datname='erp_local_preview'"):
            await conn.execute("CREATE DATABASE erp_local_preview")
    finally:
        await conn.close()
asyncio.run(main())
PYCODE
cd "$project_dir/backend"
"$runtime_dir/venv/bin/python" main.py init
unset ADMIN_PASSWORD
exec "$runtime_dir/venv/bin/python" main.py run
