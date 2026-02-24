from __future__ import annotations

import logging
from datetime import datetime, timezone

import resend

from xge.config import NotificationsConfig
from xge.models_trading import Position

logger = logging.getLogger("xge.notifications.email")


class EmailNotifier:
    """Send trade notification emails via Resend."""

    def __init__(self, config: NotificationsConfig) -> None:
        self._from_email = config.from_email
        self._to_email = config.to_email
        resend.api_key = config.resend_api_key

    def send_trade_opened(self, position: Position) -> None:
        mode = "PAPER" if position.paper else "LIVE"
        subject = f"[{mode}] Trade Opened: {position.symbol} on {position.exchange}"

        opened_at = datetime.fromtimestamp(position.opened_at, tz=timezone.utc)

        html = (
            f"<h2>Trade Opened — {position.symbol}</h2>"
            f"<table>"
            f"<tr><td><b>Mode</b></td><td>{mode}</td></tr>"
            f"<tr><td><b>Exchange</b></td><td>{position.exchange}</td></tr>"
            f"<tr><td><b>Symbol</b></td><td>{position.symbol}</td></tr>"
            f"<tr><td><b>Direction</b></td><td>{position.direction}</td></tr>"
            f"<tr><td><b>Size</b></td><td>${position.size_usdt:.2f}</td></tr>"
            f"<tr><td><b>Spot Entry Price</b></td><td>{position.spot_entry_price}</td></tr>"
            f"<tr><td><b>Spot Quantity</b></td><td>{position.spot_quantity}</td></tr>"
            f"<tr><td><b>Perp Entry Price</b></td><td>{position.perp_entry_price}</td></tr>"
            f"<tr><td><b>Perp Quantity</b></td><td>{position.perp_quantity}</td></tr>"
            f"<tr><td><b>Funding Rate</b></td><td>{position.entry_funding_rate * 100:.4f}%</td></tr>"
            f"<tr><td><b>Annualized Rate</b></td><td>{position.entry_annualized_rate:.1f}%</td></tr>"
            f"<tr><td><b>Opened At</b></td><td>{opened_at:%Y-%m-%d %H:%M:%S UTC}</td></tr>"
            f"</table>"
        )

        try:
            resend.Emails.send({
                "from": self._from_email,
                "to": [self._to_email],
                "subject": subject,
                "html": html,
            })
            logger.info("Trade opened email sent for %s on %s", position.symbol, position.exchange)
        except Exception:
            logger.exception("Failed to send trade opened email for %s on %s", position.symbol, position.exchange)

    def send_trade_closed(self, position: Position) -> None:
        mode = "PAPER" if position.paper else "LIVE"
        pnl = position.realized_pnl
        pnl_emoji = "+" if pnl >= 0 else ""
        subject = f"[{mode}] Trade Closed: {position.symbol} on {position.exchange} — {pnl_emoji}${pnl:.4f}"

        opened_at = datetime.fromtimestamp(position.opened_at, tz=timezone.utc)
        closed_at = datetime.fromtimestamp(position.closed_at, tz=timezone.utc)
        duration = position.closed_at - position.opened_at
        hours = duration / 3600
        if hours >= 24:
            duration_str = f"{hours / 24:.1f} days"
        else:
            duration_str = f"{hours:.1f} hours"

        html = (
            f"<h2>Trade Closed — {position.symbol}</h2>"
            f"<table>"
            f"<tr><td><b>Mode</b></td><td>{mode}</td></tr>"
            f"<tr><td><b>Exchange</b></td><td>{position.exchange}</td></tr>"
            f"<tr><td><b>Symbol</b></td><td>{position.symbol}</td></tr>"
            f"<tr><td><b>Direction</b></td><td>{position.direction}</td></tr>"
            f"<tr><td><b>Size</b></td><td>${position.size_usdt:.2f}</td></tr>"
            f"<tr><td><b>Spot Entry</b></td><td>{position.spot_entry_price}</td></tr>"
            f"<tr><td><b>Spot Exit</b></td><td>{position.spot_exit_price}</td></tr>"
            f"<tr><td><b>Perp Entry</b></td><td>{position.perp_entry_price}</td></tr>"
            f"<tr><td><b>Perp Exit</b></td><td>{position.perp_exit_price}</td></tr>"
            f"<tr><td><b>Realized P&L</b></td><td><b>{pnl_emoji}${pnl:.4f}</b></td></tr>"
            f"<tr><td><b>Duration</b></td><td>{duration_str}</td></tr>"
            f"<tr><td><b>Opened At</b></td><td>{opened_at:%Y-%m-%d %H:%M:%S UTC}</td></tr>"
            f"<tr><td><b>Closed At</b></td><td>{closed_at:%Y-%m-%d %H:%M:%S UTC}</td></tr>"
            f"</table>"
        )

        try:
            resend.Emails.send({
                "from": self._from_email,
                "to": [self._to_email],
                "subject": subject,
                "html": html,
            })
            logger.info("Trade closed email sent for %s on %s", position.symbol, position.exchange)
        except Exception:
            logger.exception("Failed to send trade closed email for %s on %s", position.symbol, position.exchange)
