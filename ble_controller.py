"""
ble_controller.py — Nordic nRF54LM20 DK BLE integration

The nRF54LM20 DK runs a GATT peripheral (Nordic UART Service).
Button 1 on the board → sends 0x01 (press) / 0x00 (release) over BLE notify.
This module connects as BLE central, listens for those events, and calls
on_press / on_release so main.py can gate the mic with push-to-talk.

LED status is sent back to the board via NUS RX:
    0x10 = idle (yellow)
    0x11 = listening (green)
    0x12 = thinking (blue)
    0x13 = speaking (white)
    0x14 = paused (red)

Falls back silently if the board isn't found — keyboard controls still work.
"""

import asyncio
import logging
import threading

logger = logging.getLogger(__name__)

# Nordic UART Service (NUS) — standard on all nRF dev kits
_NUS_SERVICE = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
_NUS_RX      = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # write → board
_NUS_TX      = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # notify → us

# The nRF54LM20 DK advertises with this name when flashed with the NUS sample
_BOARD_NAME  = "LilVro_DK"

# LED state bytes (board firmware maps these to LED colours)
LED_IDLE      = bytes([0x10])
LED_LISTENING = bytes([0x11])
LED_THINKING  = bytes([0x12])
LED_SPEAKING  = bytes([0x13])
LED_PAUSED    = bytes([0x14])


class BLEController:
    """
    Connects to the nRF54LM20 DK over BLE and routes button events to
    on_press / on_release callbacks (same interface as the keyboard watcher).

    Usage:
        ble = BLEController(on_press=_toggle_pause, on_release=lambda: None)
        threading.Thread(target=ble.start, daemon=True).start()
    """

    def __init__(self, on_press=None, on_release=None):
        self.on_press   = on_press   or (lambda: None)
        self.on_release = on_release or (lambda: None)
        self._client    = None
        self._loop      = None
        self.connected  = False

    # ------------------------------------------------------------------
    # Public helpers — call from any thread
    # ------------------------------------------------------------------

    def set_led(self, state_bytes: bytes):
        """Send an LED state update to the board (non-blocking, best-effort)."""
        if self._loop and self._client and self.connected:
            asyncio.run_coroutine_threadsafe(
                self._write(state_bytes), self._loop
            )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _handle_notify(self, _sender, data: bytearray):
        if data and data[0] == 0x01:
            self.on_press()
        elif data and data[0] == 0x00:
            self.on_release()

    async def _write(self, data: bytes):
        try:
            await self._client.write_gatt_char(_NUS_RX, data, response=False)
        except Exception:
            pass

    async def _run(self):
        try:
            from bleak import BleakScanner, BleakClient
        except ImportError:
            print("  [BLE] bleak not installed — pip install bleak")
            return

        print(f"  [BLE] Scanning for {_BOARD_NAME}…")
        device = await BleakScanner.find_device_by_name(_BOARD_NAME, timeout=10.0)
        if device is None:
            print(f"  [BLE] nRF54LM20 DK not found — keyboard controls active")
            return

        async with BleakClient(device) as client:
            self._client = client
            self.connected = True
            print(f"  [BLE] Connected to nRF54LM20 DK ({device.address})")
            await client.start_notify(_NUS_TX, self._handle_notify)
            await self._write(LED_IDLE)
            # Keep alive until disconnected
            while client.is_connected:
                await asyncio.sleep(0.5)
            self.connected = False
            print("  [BLE] nRF54LM20 DK disconnected")

    def start(self):
        """Blocking — run in a daemon thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._run())
