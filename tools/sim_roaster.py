#!/usr/bin/env python3
"""A simulated Kaleido roaster on a pseudo terminal, for trying the bridge without hardware.

It answers the requests Artisan sends over the serial protocol and records what a roaster
would observe: every command, whether a port is open on it ("link up") and how long it has
been since the last command. It does NOT model what the real firmware does with its safety
guard; it only shows what the roaster gets to see.

Run it, pass the printed device path to kaleido_bridge.py in place of the real port, and
point Artisan at the bridge endpoint:

    python sim_roaster.py
"""

from __future__ import annotations

import argparse
import math
import os
import select
import sys
import threading
import time


class SimRoaster:

    SERIAL_NUMBER = 'SIM000000001'

    def __init__(self, mute: bool = False, verbose: bool = False) -> None:
        self.mute = mute                # receive, but never answer (a link that is up and dead)
        self.verbose = verbose
        self.master, slave = os.openpty()
        self.device = os.ttyname(slave)  # what the bridge (or Artisan) opens as "the roaster"
        os.close(slave)
        os.set_blocking(self.master, False)
        self.events: list[tuple[float, str, str]] = []  # (time, kind, text); kinds: link, rx
        self.link_up = False
        self.guard_armed = False        # "SC AR" received and not yet "CL AR"
        self.last_command_at: float | None = None
        self._unsolicited = bytearray()
        self._lock = threading.Lock()
        self._stop_r, self._stop_w = os.pipe()
        self._started = time.time()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    # ---- what the tests and the command line look at

    def commands(self) -> list[str]:
        with self._lock:
            return [text for _, kind, text in self.events if kind == 'rx']

    def links(self) -> list[str]:
        with self._lock:
            return [text for _, kind, text in self.events if kind == 'link']

    def silence(self) -> float | None:
        """Seconds since the last command."""
        return None if self.last_command_at is None else time.time() - self.last_command_at

    def send_unsolicited(self, data: bytes) -> None:
        """Lets the roaster say something nobody asked for (a late answer)."""
        with self._lock:
            self._unsolicited += data

    def drop_link(self) -> None:
        """Simulates the loss of the upstream link: the port disappears under whoever holds it."""
        self.close()

    def close(self) -> None:
        if self._thread.is_alive():
            os.write(self._stop_w, b'x')
            self._thread.join(timeout=5)
        if self.master >= 0:
            os.close(self.master)
            self.master = -1

    # ---- the roaster

    def _event(self, kind: str, text: str) -> None:
        with self._lock:
            self.events.append((time.time(), kind, text))
        if self.verbose:
            stamp = time.strftime('%H:%M:%S') + f'.{int(time.time() % 1 * 1000):03d}'
            print(f'{stamp} sim roaster  {kind:4s} {text}', flush=True)

    def _answer(self, command: str) -> str | None:
        tag, _, value = command[2:-2].partition(' ') if command.startswith('{[') and command.endswith(']}') else ('', '', '')
        if tag == 'PI':
            return '{0}'
        if tag in {'SC', 'CL'}:
            return f'{{0,SN:{self.SERIAL_NUMBER}}}'
        if tag == 'RD':
            t = time.time() - self._started
            bt = 100.0 + 5.0 * math.sin(t / 7.0)   # slowly moving, so that live readings are recognizable
            et = 120.0 + 5.0 * math.cos(t / 9.0)
            return f'{{0,BT:{bt:.1f},ET:{et:.1f},AT:21.0,TS:0,HP:0,FC:30,RC:50,AH:0,HS:0}}'
        if tag:
            return f'{{0,{tag}:{value}}}'
        return None

    def _run(self) -> None:
        buffer = bytearray()
        while True:
            readable, _, _ = select.select([self._stop_r], [], [], 0.01)
            if readable:
                return
            try:
                data = os.read(self.master, 4096)
            except BlockingIOError:
                data = None      # a port is open on us, nothing to read
            except OSError:
                return
            if data == b'':      # nobody has the port open
                if self.link_up:
                    self.link_up = False
                    buffer.clear()
                    self._event('link', 'down')
                continue
            if not self.link_up:
                self.link_up = True
                self._event('link', 'up')
            with self._lock:
                unsolicited = bytes(self._unsolicited)
                self._unsolicited.clear()
            if unsolicited:
                self._write(unsolicited)
            if not data:
                continue
            buffer += data
            while b'\n' in buffer:
                raw, _, rest = bytes(buffer).partition(b'\n')
                buffer[:] = rest
                command = raw.decode('ascii', 'replace').strip()
                if not command:
                    continue
                self.last_command_at = time.time()
                if command == '{[SC AR]}':
                    self.guard_armed = True
                elif command == '{[CL AR]}':
                    self.guard_armed = False
                self._event('rx', command)
                answer = self._answer(command)
                if answer is not None and not self.mute:
                    self._write((answer + '\r\n').encode('ascii'))

    def _write(self, data: bytes) -> None:
        try:
            os.write(self.master, data)
        except OSError:
            pass  # nobody is listening


def main() -> int:
    parser = argparse.ArgumentParser(description='Simulated Kaleido roaster on a pseudo terminal.')
    parser.add_argument('--mute', action='store_true', help='receive commands but never answer')
    args = parser.parse_args()
    roaster = SimRoaster(mute=args.mute, verbose=True)
    print(f'simulated roaster ready. Use this as the real port of the bridge:\n\n    {roaster.device}\n\nCtrl-C to stop.', flush=True)
    try:
        while True:
            time.sleep(5)
            silence = roaster.silence()
            print(f"         sim roaster  state link={'up' if roaster.link_up else 'down'} guard={'armed' if roaster.guard_armed else 'not armed'} "
                  f"last command {'never' if silence is None else f'{silence:.1f} s ago'}", flush=True)
    except KeyboardInterrupt:
        roaster.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
