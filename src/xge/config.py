from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv


@dataclass
class ExchangeConfig:
    id: str
    enabled: bool = True
    taker_fee_pct: float = 0.1


@dataclass
class RedisConfig:
    host: str = "localhost"
    port: int = 6379


@dataclass
class LoggingConfig:
    level: str = "INFO"
    heartbeat_interval: int = 5
    min_net_spread: float = -0.05


@dataclass
class FundingConfig:
    enabled: bool = False
    poll_interval: int = 300
    log_interval: int = 60
    min_annualized_pct: float = 5.0
    min_cross_spread_pct: float = 0.005
    excluded_exchanges: list[str] = field(default_factory=list)


@dataclass
class Settings:
    exchanges: list[ExchangeConfig] = field(default_factory=list)
    symbols: list[str] = field(default_factory=list)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    funding: FundingConfig = field(default_factory=FundingConfig)

    @property
    def enabled_exchanges(self) -> list[ExchangeConfig]:
        return [e for e in self.exchanges if e.enabled]


_ENV_VAR_PATTERN = re.compile(r"\$\{(\w+)(?::-(.*?))?\}")


def _resolve_env_vars(value: str) -> str:
    """Resolve ${VAR:-default} patterns in a string."""
    def replacer(match: re.Match) -> str:
        var_name = match.group(1)
        default = match.group(2) or ""
        return os.environ.get(var_name, default)
    return _ENV_VAR_PATTERN.sub(replacer, str(value))


def load_settings(config_path: str | Path | None = None) -> Settings:
    """Load settings from YAML config and environment variables."""
    load_dotenv()

    if config_path is None:
        config_path = Path(__file__).parent.parent.parent / "config" / "settings.yaml"
    config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path) as f:
        raw = yaml.safe_load(f)

    exchanges = [
        ExchangeConfig(
            id=e["id"],
            enabled=e.get("enabled", True),
            taker_fee_pct=float(e.get("taker_fee_pct", 0.1)),
        )
        for e in raw.get("exchanges", [])
    ]

    symbols = raw.get("symbols", [])
    if not symbols:
        raise ValueError("No symbols configured in settings.yaml")

    log_cfg = raw.get("logging", {})
    logging_config = LoggingConfig(
        level=log_cfg.get("level", "INFO"),
        heartbeat_interval=int(log_cfg.get("heartbeat_interval", 5)),
        min_net_spread=float(log_cfg.get("min_net_spread", -0.05)),
    )

    redis_raw = raw.get("redis", {})
    redis_config = RedisConfig(
        host=_resolve_env_vars(str(redis_raw.get("host", "localhost"))),
        port=int(_resolve_env_vars(str(redis_raw.get("port", 6379)))),
    )

    funding_raw = raw.get("funding", {})
    funding_config = FundingConfig(
        enabled=bool(funding_raw.get("enabled", False)),
        poll_interval=int(funding_raw.get("poll_interval", 300)),
        log_interval=int(funding_raw.get("log_interval", 60)),
        min_annualized_pct=float(funding_raw.get("min_annualized_pct", 5.0)),
        min_cross_spread_pct=float(funding_raw.get("min_cross_spread_pct", 0.005)),
        excluded_exchanges=list(funding_raw.get("excluded_exchanges", [])),
    )

    return Settings(
        exchanges=exchanges,
        symbols=symbols,
        logging=logging_config,
        redis=redis_config,
        funding=funding_config,
    )
