import json
import logging
from typing import Any
from typing import Dict

import bluetooth as bt
import click
import coloredlogs

from raspvan.workers.relay import RelayClient
from raspvan.workers.scheduler import LightTimer
from respeaker.pixels import Pixels


logger = logging.getLogger(__name__)
coloredlogs.install(logger=logger, level=logging.DEBUG)


pixels = Pixels()


class BLEServer:
    def __init__(
        self,
        uuid: str = "616d3aa1-689e-4e71-8fed-09f3c7c4ad91",
        server_name: str = "RPI-BT-Server",
        port: int = 1,
    ):
        # TODO: Change this UUID
        self.uuid = uuid
        self.server_name = server_name
        # init the relay controler
        self.relay_client = RelayClient()
        # init the Scheduler
        self.scheduler = LightTimer()
        # Advertise the server
        self.port = port
        self.server_sock = self._advertise()

    def _advertise(self):
        logger.debug(
            f"Advertising with: server name: {self.server_name} "
            f"| port: {self.port} "
            f"| uuid: {self.uuid}"
        )
        server_sock = bt.BluetoothSocket(bt.RFCOMM)
        server_sock.bind(("", bt.PORT_ANY))
        server_sock.listen(self.port)

        bt.advertise_service(
            server_sock,
            self.server_name,
            service_id=self.uuid,
            service_classes=[self.uuid, bt.SERIAL_PORT_CLASS],
            profiles=[bt.SERIAL_PORT_PROFILE],
        )
        return server_sock

    def _accept_connection(self) -> bt.BluetoothSocket:
        # Accept a connection
        client_sock, client_info = self.server_sock.accept()
        logger.info(f"Accepted connection from {client_info}")

        return client_sock

    def run(self):
        # Wait for an incoming connection
        _ = self.server_sock.getsockname()[self.port]
        client_sock = self._accept_connection()

        while True:
            try:
                data = client_sock.recv(1024)
                ret = self.process_request(data)

                logger.debug(f"request process returned: {ret}")
                client_sock.send(json.dumps(ret))
            except bt.BluetoothError as be:

                if be.errno == 104:
                    logger.warning(f"Connection reset by peer...")
                    client_sock.close()
                    # Accept a new connection
                    client_sock = self._accept_connection()
                else:
                    logger.debug(be.errno)
                    logger.error(f"Something wrong with bluetooth: {be}")
            except KeyboardInterrupt:
                logger.warning("\nDisconnected")
                return
            except Exception as e:
                logger.error(f"BT Server Unknown error: {e}")

    def process_request(self, data: Dict[str, Any]):
        pixels.wakeup()
        try:
            logger.debug(f"Rx data: {data}")
            payload = json.loads(data.decode("utf-8"))
            cmd = payload.get("cmd", None)

            if cmd == "/disconnect":
                logger.info("Client wanted to disconnect")
                raise KeyboardInterrupt

            elif cmd == "/switch":
                channels = payload.get("channels")
                s = int(payload.get("mode"))
                if channels is None or s is None:
                    return {"ok": False, "state": []}

                state = self.relay_client.switch(channels, s)
                return {"ok": True, "state": state}

            elif cmd == "/schedule":
                channels = payload.get("channels", [])
                mode = int(payload.get("mode", False))
                delay = payload.get("delay")
                if delay:
                    self.scheduler.put(
                        delay=delay,
                        func=self.relay_client.switch,
                        f_kwargs={"mode": mode, "channels": channels},
                    )
                    return {
                        "ok": True,
                        "state": self.relay_client.read(),
                        "scheduled": self.scheduler.get(),
                    }

                return {"ok": False, "error": "Invalid delay value"}

            elif cmd == "/read":
                # TODO: Format the scheduled task accordingly
                return {
                    "ok": True,
                    "state": self.relay_client.read(),
                    "scheduled": self.scheduler.get(),
                }
            else:
                return {"ok": False, "error": f"Unknown command '{cmd}'"}

        except Exception as e:
            logger.error(f"Error processing request to BT server: {e}")
            logger.exception(e)
            return {"ok": False, "error": str(e)}
        finally:
            pixels.off()


@click.command()
@click.option("--uuid", default="616d3aa1-689e-4e71-8fed-09f3c7c4ad91")
@click.option("--server-name", default="RPI-BT-Server")
@click.option("--port", default=1)
def main(uuid: str, server_name: str, port: int):
    ble = BLEServer(uuid, server_name, port)
    ble.run()


if __name__ == "__main__":
    """
    For an example for RFCOMM server from pybluez:
    # https://github.com/pybluez/pybluez/blob/master/examples/simple/rfcomm-server.py
    """
    main()
