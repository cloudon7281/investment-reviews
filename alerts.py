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
import ssl
from datetime import datetime
from email.message import EmailMessage
from typing import Dict, List

logger = logging.getLogger(__name__)


class AlertDeliveryError(Exception):
    """Raised when an alert email could not be delivered.

    Distinct from the pipeline's own failures: the spreadsheet update has already
    succeeded by the time alerts are sent, so this must not be conflated with it
    (see the exit-code contract in update_google_sheet.main).
    """

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


def _read_smtp_password(alert_config: Dict) -> str:
    """Return the SMTP password, preferring a secret file over an inline value.

    Args:
        alert_config: 'notifications.alerts' section of config.yaml

    Returns:
        The password, or '' if neither a file nor an inline value is configured
    """
    password_file = alert_config.get('smtp_password_file')
    if password_file:
        try:
            with open(password_file) as handle:
                return handle.read().strip()
        except OSError as e:
            raise AlertDeliveryError(f"cannot read smtp_password_file {password_file}: {e}") from e
    return (alert_config.get('smtp_password') or '').strip()


def send_alert_email(alert_config: Dict, subject: str, body: str) -> None:
    """Send an alert email via the local Proton Bridge SMTP relay.

    Three details of the bridge are easy to get wrong, and each fails differently
    (investment-reviews#20, and monitoring#66 which hit the same wall independently):

    - `smtp_user` is the bridge account's PRIMARY address, not the send-as address.
      The bridge runs in combined-address mode and issues one username/password pair
      serving both SMTP and IMAP; authenticating as the send-as address fails.
    - `from` may be any address ON that account. An address the account does not own
      is accepted at MAIL FROM and then rejected at DATA with
      `554 5.0.0 Error: no such user` — which is what silently broke this nightly job
      from 2026-08-02 to 2026-08-12.
    - the password is the BRIDGE-GENERATED one from the bridge's own UI. Neither the
      Proton account password nor an SMTP-submission token (a different mechanism,
      aimed at smtp.protonmail.ch:587) will authenticate here.

    The bridge advertises STARTTLS with a self-signed certificate, hence the unverified
    context — defensible only because this connection never leaves the host loopback.

    Args:
        alert_config: 'notifications.alerts' section of config.yaml
        subject: Email subject
        body: Plain text email body

    Raises:
        AlertDeliveryError: If the message cannot be delivered
    """
    to_addr = alert_config['to']
    from_addr = alert_config.get('from', 'alerts@calumlabs.uk')
    smtp_host = alert_config.get('smtp_host', 'host.docker.internal')
    smtp_port = alert_config.get('smtp_port', 1025)
    smtp_user = alert_config.get('smtp_user', '')
    smtp_password = _read_smtp_password(alert_config)

    message = EmailMessage()
    message['Subject'] = subject
    message['From'] = from_addr
    message['To'] = to_addr
    message.set_content(body)

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as smtp:
            smtp.ehlo()
            if smtp.has_extn('starttls'):
                smtp.starttls(context=ssl._create_unverified_context())
                smtp.ehlo()
            if smtp_user:
                if not smtp_password:
                    raise AlertDeliveryError(
                        f"smtp_user {smtp_user} is set but no password is available; "
                        "seed the bridge-generated password into smtp_password_file"
                    )
                smtp.login(smtp_user, smtp_password)
            smtp.send_message(message)
    except AlertDeliveryError:
        raise
    except (OSError, smtplib.SMTPException) as e:
        raise AlertDeliveryError(f"{type(e).__name__}: {e}") from e

    logger.info(f"Alert email sent to {to_addr} via {smtp_host}:{smtp_port}: {subject}")
