from __future__ import annotations

from telephony import ModemBase
from logger import get_logger


log = get_logger("drivers.modem.none")


class NullModem(ModemBase):
    def dial(self, number: str) -> None:
        log.info("Null modem dial ignored", extra={"number": str(number or "")})
        return None

    def hang_up(self) -> None:
        log.info("Null modem hang_up ignored")
        return None

    def send_text(self, peer: str, body: str):
        log.info(
            "Null modem send_text ignored",
            extra={"peer": str(peer or ""), "body_len": len(str(body or ""))},
        )
        return None


def create_modem() -> ModemBase:
    log.info("Null modem created")
    return NullModem()
