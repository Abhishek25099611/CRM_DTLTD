"""YAML -> Settings + logging (CRM)."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import yaml

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config.yaml"
LOCAL_CONFIG_PATH = BASE_DIR / "config.local.yaml"   # machine-specific overrides; never committed


@dataclass
class Settings:
    host: str = "127.0.0.1"
    port: int = 8016
    company_name: str = "Duztec Engineering Pvt. Ltd."
    tagline: str = "Clean up the Air · Sales CRM"
    company: dict[str, Any] = field(default_factory=dict)
    numbering: dict[str, Any] = field(default_factory=dict)
    quotation_defaults: dict[str, Any] = field(default_factory=dict)
    enquiry_types: list[str] = field(default_factory=lambda: ["Normal", "Tender", "Budgetary", "Supporting", "Repeat Order"])
    state_keywords: dict[str, str] = field(default_factory=dict)
    pincode_keywords: dict[str, str] = field(default_factory=dict)
    auth: dict[str, Any] = field(default_factory=dict)
    db: Path = BASE_DIR / "data" / "crm.db"
    logs: Path = BASE_DIR / "data" / "logs"
    backup: Path = BASE_DIR / "data" / "backup"
    mis_file: Path = BASE_DIR.parent / "MIS 2026-27.xlsx"

    def resolve(self, p) -> Path:
        p = Path(p).expanduser()
        return p if p.is_absolute() else (BASE_DIR / p).resolve()


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge `override` into `base` (override wins). Used for config.local.yaml."""
    out = dict(base)
    for k, v in (override or {}).items():
        out[k] = _deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_settings(path: Path = CONFIG_PATH) -> Settings:
    """config.yaml (in git) <- config.local.yaml (machine-specific) <- environment variables."""
    raw = _deep_merge(_read_yaml(path), _read_yaml(LOCAL_CONFIG_PATH))
    # Environment overrides — keeps secrets out of files entirely if preferred.
    env_map = {"DUZTEC_SMTP_HOST": "host", "DUZTEC_SMTP_PORT": "port", "DUZTEC_SMTP_USER": "username",
               "DUZTEC_SMTP_PASSWORD": "password", "DUZTEC_SMTP_FROM": "from_addr"}
    env_smtp = {key: os.environ[var] for var, key in env_map.items() if os.environ.get(var)}
    if env_smtp:
        raw = _deep_merge(raw, {"auth": {"smtp": env_smtp}})
    if os.environ.get("DUZTEC_PORT"):
        raw = _deep_merge(raw, {"app": {"port": int(os.environ["DUZTEC_PORT"])}})
    app, paths = raw.get("app") or {}, raw.get("paths") or {}
    s = Settings()
    s.host = app.get("host", s.host); s.port = int(app.get("port", s.port))
    s.company_name = app.get("company_name", s.company_name); s.tagline = app.get("tagline", s.tagline)
    s.company = raw.get("company") or {}
    s.numbering = raw.get("numbering") or {}
    s.quotation_defaults = raw.get("quotation_defaults") or {}
    s.enquiry_types = [str(x) for x in (raw.get("enquiry_types") or s.enquiry_types)]
    s.state_keywords = {str(k).lower(): str(v) for k, v in ((raw.get("geo") or {}).get("state_keywords") or {}).items()}
    s.pincode_keywords = {str(k).lower(): str(v) for k, v in ((raw.get("geo") or {}).get("pincode_keywords") or {}).items()}
    s.auth = raw.get("auth") or {}
    s.db = s.resolve(paths.get("db", s.db))
    s.logs = s.resolve(paths.get("logs", s.logs))
    s.backup = s.resolve(paths.get("backup", s.backup))
    s.mis_file = s.resolve(paths.get("mis_file", s.mis_file))
    return s


def setup_logging(s: Settings) -> logging.Logger:
    s.logs.mkdir(parents=True, exist_ok=True)
    lg = logging.getLogger("duztec_crm"); lg.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    names = {h.get_name() for h in lg.handlers}
    if "file" not in names:
        fh = RotatingFileHandler(s.logs / "app.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8")
        fh.set_name("file"); fh.setFormatter(fmt); lg.addHandler(fh)
    if "stream" not in names:
        sh = logging.StreamHandler(); sh.set_name("stream"); sh.setFormatter(fmt); lg.addHandler(sh)
    return lg


SETTINGS = load_settings()
LOGGER = setup_logging(SETTINGS)
