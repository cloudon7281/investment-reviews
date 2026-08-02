#!/usr/bin/env python3
"""
Nightly portfolio alerts.

Identifies stocks that need attention between monthly reviews:
- stocks approaching a doubling (profit-taking rule)
- stocks whose price moved sharply today

and emails them via the Proton Bridge SMTP relay.
"""

import logging
import smtplib
from datetime import datetime
from email.message import EmailMessage
from typing import Dict, List

logger = logging.getLogger(__name__)

# 'Progress to 2x' above which a stock is treated as being in doubling territory
DOUBLING_THRESHOLD = 1.95


def find_alerts(stocks: List[Dict], change_threshold_pct: float) -> Dict[str, List[Dict]]:
    """Select the stocks that warrant an alert.

    Args:
        stocks: Per-stock dictionaries from ConsoleOutputParser.parse_stocks
        change_threshold_pct: Daily change threshold in percent (e.g. 3.0)

    Returns:
        Dictionary with keys 'approaching_doubling' and 'big_movers', each a list
        of stock dictionaries sorted with the most notable first
    """
    change_threshold = change_threshold_pct / 100

    approaching_doubling = [
        s for s in stocks
        if s['progress_to_2x'] is not None and s['progress_to_2x'] > DOUBLING_THRESHOLD
    ]
    approaching_doubling.sort(key=lambda s: s['progress_to_2x'], reverse=True)

    big_movers = [
        s for s in stocks
        if s['daily_change'] is not None and abs(s['daily_change']) >= change_threshold
    ]
    big_movers.sort(key=lambda s: abs(s['daily_change']), reverse=True)

    logger.info(
        f"Alert scan: {len(approaching_doubling)} stock(s) above {DOUBLING_THRESHOLD}x, "
        f"{len(big_movers)} stock(s) moved at least {change_threshold_pct}%"
    )

    return {
        'approaching_doubling': approaching_doubling,
        'big_movers': big_movers,
    }


def format_alert_email(alerts: Dict[str, List[Dict]], change_threshold_pct: float) -> tuple:
    """Build the subject and body for an alert email.

    Args:
        alerts: Output of find_alerts (must contain at least one stock)
        change_threshold_pct: Daily change threshold in percent, quoted in the body

    Returns:
        Tuple of (subject, body)
    """
    approaching = alerts['approaching_doubling']
    movers = alerts['big_movers']

    parts = []
    if approaching:
        parts.append(f"{len(approaching)} near 2x")
    if movers:
        parts.append(f"{len(movers)} big mover{'s' if len(movers) != 1 else ''}")
    subject = f"Portfolio alerts {datetime.now().strftime('%Y-%m-%d')}: {', '.join(parts)}"

    lines = []

    if approaching:
        lines.append(f"Approaching a doubling (above {DOUBLING_THRESHOLD}x):")
        lines.append("")
        for stock in approaching:
            lines.append(f"  {_describe(stock)} — {stock['progress_to_2x']:.2f}x")
        lines.append("")

    if movers:
        lines.append(f"Moved at least {change_threshold_pct}% today:")
        lines.append("")
        for stock in movers:
            lines.append(f"  {_describe(stock)} — {stock['daily_change']*100:+.1f}%")
        lines.append("")

    return subject, '\n'.join(lines)


def _describe(stock: Dict) -> str:
    """Format a stock's identity and current value for an alert line."""
    description = f"{stock['company']} ({stock['ticker']})"
    if stock['tag']:
        description += f" [{stock['tag']}]"
    if stock['current_value'] is not None:
        description += f", £{stock['current_value']:,.0f}"
    return description


def send_alert_email(alert_config: Dict, subject: str, body: str) -> None:
    """Send an alert email via the configured SMTP relay.

    Args:
        alert_config: 'notifications.alerts' section of config.yaml
        subject: Email subject
        body: Plain text email body

    Raises:
        OSError: If the message cannot be sent
    """
    to_addr = alert_config['to']
    from_addr = alert_config.get('from', 'investment-reviews@calumlabs.co.uk')
    smtp_host = alert_config.get('smtp_host', 'host.docker.internal')
    smtp_port = alert_config.get('smtp_port', 1025)

    message = EmailMessage()
    message['Subject'] = subject
    message['From'] = from_addr
    message['To'] = to_addr
    message.set_content(body)

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as smtp:
        smtp.send_message(message)

    logger.info(f"Alert email sent to {to_addr} via {smtp_host}:{smtp_port}: {subject}")
