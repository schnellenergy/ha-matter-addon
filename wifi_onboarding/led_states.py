#!/usr/bin/env python3
"""Canonical LED state contract, shared by every writer and by the controller.

Why this file exists
--------------------
The LED is written by four independent places: run.sh at boot,
improved_ble_service.py (periodic network monitor, provisioning outcome,
signal handlers, auto-reconnect) and button_monitor.py (factory reset).
They all wrote to /tmp/led_status with last-write-wins semantics and no
notion of one state mattering more than another, which produced wrong
indications:

  * The network monitor runs every 0.5 s and recomputed the LED purely from
    interface state, so it erased 'factory_reset' within half a second — a
    long-press showed a flicker of red and then went back to solid green,
    looking as though nothing had happened.
  * NetworkManager reports wlan0 'connected' at association, before DHCP, so
    the monitor painted solid blue seconds before the hub had an IP and long
    before the app knew anything.
  * A bad state name was coerced to 'error' in improved_ble_service, ignored
    outright by led_controller, and unvalidated in button_monitor — the same
    mistake produced three different behaviours.

So: one list of states, one ranking, one arbiter. led_controller is the only
reader of the status file and is therefore the arbiter; a lower-ranked writer
can never overwrite a higher-ranked active state.

Channels
--------
STATUS_FILE   single slot, routine steady-state reports from the network monitor
EVENT_FILE    append-only queue, everything else — lossless and ordered
OVERLAY_FILE  Ethernet presence; decides what is DISPLAYED, never what the hub IS

A leading '!' on an event means "force": the owner of a transient state uses it
to release that state and hand the LED back. Only the code that entered a
transient state should force its way out of it.
"""

import os

STATUS_FILE = "/tmp/led_status"

# Every request that is NOT a routine steady-state report — factory reset,
# reset refused, provisioning, boot reconnect, and the releases that end them —
# is an EVENT, and events are appended to a lossless queue.
#
# They cannot go through STATUS_FILE. That is a single slot, and the network
# monitor rewrites it twice a second, so anything written there can be silently
# replaced before the controller's 50 ms poll reads it. A lost steady-state
# report is harmless (the next one is 500 ms away), but a lost event is not:
# a factory-reset indication would simply never appear, and a lost release would
# strand the LED on a state that outranks everything the monitor can request —
# permanently. Appending means nothing is ever overwritten, and the controller
# reads them in order.
EVENT_FILE = "/tmp/led_events"

# Ethernet is an OVERLAY, not a state that competes with the others.
#
# Whenever an Ethernet cable is connected the LED shows solid green, whatever
# else is happening — provisioning, a factory reset, a boot reconnect. None of
# that logic is affected; only what the LED displays. Unplug the cable and the
# LED immediately reveals the underlying state again.
#
# Modelling it as an overlay rather than a ranked state is what makes that work:
# a ranked state would have to either lose to a reset (wrong: green must win) or
# beat it (wrong: the reset would be forgotten when the cable came out).
OVERLAY_FILE = "/tmp/led_ethernet"

# Prefix meaning "accept this regardless of rank" — see module docstring.
FORCE_PREFIX = '!'

# Higher wins. Transient states (reset, provisioning) outrank the steady-state
# reporter so the periodic monitor cannot stomp them.
RANK = {
    # Deliberate power-down always wins.
    'shutdown': 100,

    # Physical user action — must never be masked by a background writer.
    'factory_reset': 90,
    'reset_refused': 90,

    # An app-driven provisioning attempt owns the LED until it resolves.
    'wifi_provisioning': 80,
    'setup_in_progress': 80,

    # Boot auto-reconnect to a saved network.
    'wifi_connecting': 60,

    # Hardware / startup fault (e.g. no Bluetooth adapter). Deliberately ranked
    # BELOW the steady network states: a hub with a broken radio but a working
    # Ethernet link should still show green rather than being stuck on the fault
    # indication forever, since run.sh sets this once at boot and never clears it.
    'error': 5,

    # Steady state, emitted by the periodic network monitor. Equal ranks so
    # these can freely transition between each other.
    'ethernet_connected': 10,
    'wifi_connected': 10,
    'internet_connected': 10,
    'dual_network': 10,
    'wifi_no_internet': 10,
    'ethernet_no_internet': 10,

    # Idle / ready to onboard — the floor.
    'ble_advertising': 0,
    'booting': 0,
}

VALID = frozenset(RANK)

# States that do not end on their own: whoever set one must release it with
# FORCE_PREFIX once the operation finishes.
TRANSIENT = frozenset({
    'factory_reset',
    'reset_refused',
    'wifi_provisioning',
    'setup_in_progress',
})


def rank(status: str) -> int:
    """Rank of `status`; unknown names sort to the floor."""
    return RANK.get(status, 0)


def parse(raw: str):
    """Split a status-file payload into (status, force).

    Returns (None, False) for anything not in VALID, so the controller can
    log and ignore it rather than guessing.
    """
    if not raw:
        return None, False
    raw = raw.strip()
    force = raw.startswith(FORCE_PREFIX)
    if force:
        raw = raw[len(FORCE_PREFIX):].strip()
    if raw not in VALID:
        return None, False
    return raw, force


def encode(status: str, force: bool = False) -> str:
    """Build the payload for `status`."""
    return (FORCE_PREFIX if force else '') + status


def write_request(status: str, force: bool = False, steady: bool = False) -> bool:
    """Ask the controller for `status`. The single entry point for every writer.

    `steady=True` marks a routine report from the periodic network monitor: those
    go to the single-slot STATUS_FILE, where being overwritten costs nothing
    because the next report is 500 ms away.

    Everything else is an event and is appended to the lossless queue, so it can
    never be dropped. See EVENT_FILE.

    Returns False if `status` is not a known state — refused rather than guessed.
    """
    if status not in VALID:
        return False
    if steady:
        with open(STATUS_FILE, 'w') as f:
            f.write(encode(status, False))
    else:
        with open(EVENT_FILE, 'a') as f:
            f.write(encode(status, force) + '\n')
    return True


def read_events(offset: int):
    """Consume queued events from `offset`. Controller-only.

    Returns (events, new_offset) where events is a list of (status, force).
    A file shorter than `offset` means it was cleared (a fresh boot), so we
    start over rather than reading garbage.
    """
    try:
        size = os.path.getsize(EVENT_FILE)
    except OSError:
        return [], 0
    if size < offset:
        offset = 0
    if size == offset:
        return [], offset
    try:
        with open(EVENT_FILE, 'r') as f:
            f.seek(offset)
            data = f.read()
            new_offset = f.tell()
    except Exception:
        return [], offset

    events = []
    for line in data.splitlines():
        status, force = parse(line)
        if status is not None:
            events.append((status, force))
    return events, new_offset


def set_overlay(active: bool) -> None:
    """Report whether an Ethernet cable is connected.

    Separate from the state request so the two never fight: the overlay decides
    what is DISPLAYED, the request decides what the hub IS.
    """
    try:
        with open(OVERLAY_FILE, 'w') as f:
            f.write('1' if active else '0')
    except Exception:
        pass


def read_overlay() -> bool:
    """True when Ethernet is connected. Controller-only."""
    try:
        with open(OVERLAY_FILE, 'r') as f:
            return f.read().strip() == '1'
    except Exception:
        return False


def clear_events() -> int:
    """Drop any queued events and return the starting offset. Controller-only.

    Used at startup so events left by a previous run are never replayed.
    """
    try:
        os.remove(EVENT_FILE)
    except Exception:
        pass
    return 0
