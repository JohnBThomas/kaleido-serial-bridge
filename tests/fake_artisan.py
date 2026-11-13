#!/usr/bin/env python3
"""A stand-in for Artisan's Kaleido serial client, to be run (and killed) as a separate process.

Opens the port the way Artisan does (pyserial, exclusive), runs the handshake Artisan runs
(PI, TU, SC AR), then polls with RD. With --off it ends like Artisan's OFF and quit do:
it sends CL AR, waits for the answer and closes the port. Without it, it polls until killed.
"""

import argparse
import sys
import time

import serial


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('port')
    parser.add_argument('--polls', type=int, default=0, help='number of RD requests before ending (0: until killed)')
    parser.add_argument('--off', action='store_true', help='end with CL AR like Artisan does on OFF and on quit')
    parser.add_argument('--interval', type=float, default=0.1)
    args = parser.parse_args()

    port = serial.Serial(args.port, 57600, bytesize=8, parity='N', stopbits=1, timeout=1.0, exclusive=True)

    def ask(command: str) -> bytes:
        port.write(command.encode('ascii') + b'\n')
        return port.readline()

    answers = [ask('{[PI]}'), ask('{[TU C]}'), ask('{[SC AR]}')]
    print('READY', answers, flush=True)
    polls = 0
    while args.polls == 0 or polls < args.polls:
        print('RD', ask('{[RD A0]}'), flush=True)
        polls += 1
        time.sleep(args.interval)
    if args.off:
        print('CL', ask('{[CL AR]}'), flush=True)
    port.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
