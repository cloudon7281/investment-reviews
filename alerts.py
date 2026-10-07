#!/usr/bin/env python3
"""
Nightly portfolio alerts.

Identifies stocks that need attention between monthly reviews:
- stocks approaching a doubling (profit-taking rule)
- stocks whose price moved sharply today

and hands them to `tier-4-notify`, which decides the channels and delivers.
"""

import html
import json
import logging
import os
import urllib.error
import urllib.request
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class AlertDeliveryError(Exception):
    """Raised when an alert email could not be delivered.

    Distinct from the pipeline's own failures: the spreadsheet update has already
    succeeded by the time alerts are sent, so this must not be conflated with it
    (see the exit-code contract in update_google_sheet.main).
    """

# 'Progress to 2x' above which a stock is treated as being in doubling territory
DOUBLING_THRESHOLD = 1.95

# Holdings worth less than this are left out of the alerts. A few stocks could not be sold in full
# and are effectively worthless, but still carry a fractional price whose daily swings are large and
# meaningless (investment-reviews#93: First Republic, worth £0, reported as -75%).
MIN_ALERT_VALUE = 100.0


def find_alerts(stocks: List[Dict], change_threshold_pct: float) -> Dict[str, List[Dict]]:
    """Select the stocks that warrant an alert.

    Args:
        stocks: Per-stock dictionaries from ConsoleOutputParser.parse_stocks
        change_threshold_pct: Daily change threshold in percent (e.g. 3.0)

    Returns:
        Dictionary with keys 'approaching_doubling' and 'big_movers', each a list
        of stock dictionaries: doublings by progress, highest first; movers by
        daily change, best first. Holdings worth under MIN_ALERT_VALUE (or with
        no value) are excluded from both.
    """
    change_threshold = change_threshold_pct / 100

    stocks = [s for s in stocks
              if s['current_value'] is not None and s['current_value'] >= MIN_ALERT_VALUE]

    approaching_doubling = [
        s for s in stocks
        if s['progress_to_2x'] is not None and s['progress_to_2x'] > DOUBLING_THRESHOLD
    ]
    approaching_doubling.sort(key=lambda s: s['progress_to_2x'], reverse=True)

    big_movers = [
        s for s in stocks
        if s['daily_change'] is not None and abs(s['daily_change']) >= change_threshold
    ]
    # Best performer first, worst last
    big_movers.sort(key=lambda s: s['daily_change'], reverse=True)

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

    Each section is a headed table, in plain text and in HTML. The HTML is what a mail
    reader shows; the plain text is the same content for one that prefers it.

    Args:
        alerts: Output of find_alerts (must contain at least one stock)
        change_threshold_pct: Daily change threshold in percent, quoted in the body

    Returns:
        Tuple of (subject, body, html)
    """
    approaching = alerts['approaching_doubling']
    movers = alerts['big_movers']

    parts = []
    if approaching:
        parts.append(f"{len(approaching)} near 2x")
    if movers:
        parts.append(f"{len(movers)} big mover{'s' if len(movers) != 1 else ''}")
    subject = f"Portfolio alerts {datetime.now().strftime('%Y-%m-%d')}: {', '.join(parts)}"

    sections = []

    if approaching:
        sections.append((
            f"Approaching a doubling (above {DOUBLING_THRESHOLD}x):",
            ['Name', 'Ticker', 'Tag', 'Current value', 'Progress to 2x'],
            [_identity(s) + [f"{s['progress_to_2x']:.2f}x"] for s in approaching],
        ))

    if movers:
        sections.append((
            f"Moved at least {change_threshold_pct}% today:",
            ['Name', 'Ticker', 'Tag', 'Current value', 'Change', 'Change %'],
            [_identity(s) + [_pounds(_absolute_change(s), signed=True),
                             f"{s['daily_change']*100:+.1f}%"] for s in movers],
        ))

    body = '\n\n'.join(f"{title}\n\n{_text_table(headers, rows)}" for title, headers, rows in sections)
    html_body = '\n'.join(f"<p>{html.escape(title)}</p>\n{_html_table(headers, rows)}"
                           for title, headers, rows in sections)

    return subject, body, html_body


# The first three columns of every table are text; the rest are figures, aligned right.
_TEXT_COLUMNS = 3


def _identity(stock: Dict) -> List[str]:
    """The cells that identify a stock and its current value."""
    return [stock['company'], stock['ticker'], stock['tag'], _pounds(stock['current_value'])]


def _absolute_change(stock: Dict) -> float:
    """Today's change in the holding's value, from its current value and percentage change."""
    return stock['current_value'] * stock['daily_change'] / (1 + stock['daily_change'])


def _pounds(value: float, signed: bool = False) -> str:
    sign = ('+' if value >= 0 else '-') if signed else ''
    return f"{sign}£{abs(value):,.0f}"


def _text_table(headers: List[str], rows: List[List[str]]) -> str:
    """A table with space-padded columns, for the plain-text part."""
    widths = [max(len(str(cell)) for cell in column) for column in zip(headers, *rows)]

    def line(cells):
        return '  '.join(str(cell).ljust(width) if i < _TEXT_COLUMNS else str(cell).rjust(width)
                         for i, (cell, width) in enumerate(zip(cells, widths))).rstrip()

    return '\n'.join([line(headers), line(['-' * width for width in widths])] + [line(r) for r in rows])


def _html_table(headers: List[str], rows: List[List[str]]) -> str:
    """The same table in HTML, for the part a mail reader shows."""
    def cell(tag, value, i):
        align = 'left' if i < _TEXT_COLUMNS else 'right'
        return (f'<{tag} style="text-align:{align};padding:2px 10px;border-bottom:1px solid #ddd">'
                f'{html.escape(str(value))}</{tag}>')

    head = '<tr>' + ''.join(cell('th', h, i) for i, h in enumerate(headers)) + '</tr>'
    body = ''.join('<tr>' + ''.join(cell('td', v, i) for i, v in enumerate(r)) + '</tr>' for r in rows)
    return f'<table style="border-collapse:collapse">{head}{body}</table>'


# These alerts are content, not faults: they say what the portfolio did, and nothing acts on them
# automatically. They still carry a severity because that is what selects a channel in
# tier-4-notify — and `info` deliberately reaches nobody there, so an alert that has to arrive
# cannot use it (devops-model#264, detection-and-response-model.md, "Notification").
PORTFOLIO_SEVERITY = 'warning'
FAILURE_SEVERITY = 'critical'

DELIVERY_TIMEOUT_SECONDS = 30


def send_alert(subject: str, body: str, severity: str, source: str,
               html_body: Optional[str] = None) -> None:
    """Hand an alert to tier-4-notify, which owns delivery and the Proton credential.

    This service composed its own SMTP before devops-model#264 — one of four independent
    implementations in the estate, three of which got the bridge's details wrong first time. Every
    one of those details is now somebody else's problem: the send-as address, the combined-address
    username, the bridge-generated password, and the STARTTLS certificate. What is left here is the
    part that is genuinely this service's own, which is deciding what to say.

    The endpoint is brokered, never written down: `consumesPorts: notify` resolves to
    CONSUMED_NOTIFY for this container's execution context (SDI, "Service-to-service endpoints").
    An unregistered deploy has nowhere to send and says so — there is deliberately no fallback
    address, because the previous one named `host.docker.internal` and sent a container out to the
    host and back to reach a container beside it (devops-model#205).

    Args:
        subject: Subject line
        body: Plain text body
        severity: `critical`, `warning` or `info`; tier-4-notify routes on it
        source: Who is speaking, as `<service>/<purpose>`
        html_body: Optional HTML rendering of `body`, which tier-4-notify mails as an
            alternative part beside it

    Raises:
        AlertDeliveryError: If the message could not be delivered. The caller turns that into
            exit 2 and `investment_reviews_alert_delivery_ok 0` — the spreadsheet has already
            been updated by this point, and conflating the two is what made a broken mail relay
            look like a broken portfolio pipeline for ten days (investment-reviews#20).
    """
    endpoint = os.environ.get('CONSUMED_NOTIFY', '').strip()
    if not endpoint:
        raise AlertDeliveryError(
            'no notification endpoint: registration has not brokered CONSUMED_NOTIFY into this '
            'container (declare `consumesPorts: notify` and re-register)')

    url = f'http://{endpoint}/notify'
    message = {'subject': subject, 'body': body, 'severity': severity, 'source': source}
    if html_body:
        message['html'] = html_body
    payload = json.dumps(message).encode()
    request = urllib.request.Request(
        url, data=payload, headers={'Content-Type': 'application/json'}, method='POST')

    try:
        with urllib.request.urlopen(request, timeout=DELIVERY_TIMEOUT_SECONDS) as response:
            outcome = json.load(response)
    except urllib.error.HTTPError as e:
        # 502 is tier-4-notify saying every channel failed, which is precisely the condition the
        # exit-code contract exists for; 400 is this service's own fault. Both are undeliverable.
        raise AlertDeliveryError(f'POST {url} returned {e.code}: {e.read().decode(errors="replace")[:200]}') from e
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise AlertDeliveryError(f'POST {url}: {type(e).__name__}: {e}') from e

    # A 200 with nothing delivered is what a severity that routes nowhere looks like. Treating it
    # as success would report a channel as healthy on the strength of a message nobody received.
    if not outcome.get('delivered'):
        raise AlertDeliveryError(f'{url} accepted the message and delivered it nowhere: {outcome}')

    logger.info(f"Alert delivered via {outcome['delivered']} by {url}: {subject}")
