from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.config import settings  # noqa: E402
from backend.app.db.session import engine  # noqa: E402
from backend.app.services.embeddings import check_local_embedding_ready, embed_text_hash  # noqa: E402
from backend.app.services.llm import get_llm_provider  # noqa: E402


def ok(name: str, detail: str = "") -> tuple[bool, str, str]:
    return True, name, detail


def fail(name: str, detail: str) -> tuple[bool, str, str]:
    return False, name, detail


def check_database() -> tuple[bool, str, str]:
    try:
        with engine.connect() as conn:
            conn.execute(text("select 1"))
        return ok("database", settings.database_url.split("@")[-1])
    except Exception as exc:
        return fail("database", f"{type(exc).__name__}: {exc}")


def check_writable_dir(name: str, value: str) -> tuple[bool, str, str]:
    try:
        path = Path(value)
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".deploy_check"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return ok(name, str(path))
    except Exception as exc:
        return fail(name, f"{value}: {type(exc).__name__}: {exc}")


def check_embedding() -> tuple[bool, str, str]:
    provider = settings.embedding_provider.lower().strip()
    if provider == "hash":
        try:
            dim = len(embed_text_hash("deploy check"))
            return ok("embedding", f"hash dim={dim}")
        except Exception as exc:
            return fail("embedding", f"hash provider unavailable: {type(exc).__name__}: {exc}")
    if provider == "fastembed":
        result = check_local_embedding_ready()
        if result.get("ok"):
            return ok("embedding", f"{result.get('model')} dim={result.get('dim')}")
        return fail("embedding", f"fastembed model not ready: {result}")
    return fail("embedding", f"unsupported EMBEDDING_PROVIDER={settings.embedding_provider}")


def check_llm_config() -> tuple[bool, str, str]:
    provider = get_llm_provider()
    if not provider.available():
        return fail("llm", "DEEPSEEK_API_KEY is missing")
    return ok("llm", f"{provider.name} configured")


def main() -> int:
    checks = [
        ok("app_env", settings.app_env),
        check_llm_config(),
        check_database(),
        check_writable_dir("upload_dir", settings.knowledge_upload_staging_dir),
        check_writable_dir("chroma_dir", settings.chroma_persist_dir),
        check_writable_dir("embedding_cache_dir", settings.embedding_cache_dir),
        check_embedding(),
    ]
    failed = False
    for passed, name, detail in checks:
        marker = "OK" if passed else "FAIL"
        print(f"[{marker}] {name}: {detail}")
        failed = failed or not passed
    if failed:
        print("\nDeployment readiness check failed. Fix the FAIL item(s) above before moving to the server.", file=sys.stderr)
        return 1
    print("\nDeployment readiness check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
