from __future__ import annotations

from telephony import ModemBase, SimulatedModem
from logger import get_logger


log = get_logger("drivers.modem.simulated")


def create_modem() -> ModemBase:
    log.info("Creating simulated modem")
    modem = SimulatedModem()
    log.debug("Simulated modem created", extra={"class": modem.__class__.__name__})
    return modem
