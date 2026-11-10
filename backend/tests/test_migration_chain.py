"""
The database migrations form one unbroken line. Two files with the same
revision id, or two migrations both following the same one, leave Alembic
with more than one "head": `alembic upgrade head` then refuses to run, and
Railway's pre-deploy step fails, so nothing new reaches production. This
catches it before a push.
"""
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND = Path(__file__).resolve().parents[1]


def _script():
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    return ScriptDirectory.from_config(cfg)


def test_every_revision_id_is_used_once():
    ids = {}
    for f in (BACKEND / "alembic" / "versions").glob("*.py"):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.startswith("revision"):
                rid = line.split("=")[1].strip().strip("\"'")
                assert rid not in ids, f"{rid} is used by both {ids[rid]} and {f.name}"
                ids[rid] = f.name


def test_there_is_exactly_one_head():
    heads = _script().get_heads()
    assert len(heads) == 1, f"More than one latest migration: {heads}. Point one at the other with down_revision."
