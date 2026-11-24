#!/usr/bin/env python3
"""Scanner Modbus TCP per il Magis Combo V2 via gateway Elfin EW11 (SOLA LETTURA).

Serve a validare sul campo il cablaggio e la mappa registri prima/dopo aver configurato
l'integrazione. Legge soltanto (FC 0x03 holding): non scrive mai nulla.

Esempi:
    # legge i registri noti e li stampa interpretati
    python tools/immergas_scan.py 192.168.1.50 --known

    # scansiona un intervallo (es. i sensori 3000-3099) e mostra solo i registri che rispondono
    python tools/immergas_scan.py 192.168.1.50 --scan 3000 3099

Nessuna dipendenza esterna.
"""
from __future__ import annotations

import argparse
import socket
import struct
import sys

KNOWN = {
    2000: ("Modo operativo (grezzo)", 1),
    2095: ("Setpoint sanitario", 0.1),
    2100: ("Codice guasto (grezzo)", 1),
    3000: ("Mandata impianto", 0.1),
    3001: ("Ritorno pompa di calore", 0.1),
    3002: ("Temperatura esterna", 0.1),
    3016: ("Accumulo sanitario", 0.1),
    3029: ("Ritorno unità interna", 0.1),
    3056: ("Liquido circuito chiller", 0.1),
}


def read_holding(sock: socket.socket, unit: int, address: int, count: int, tid: int) -> list[int] | str:
    pdu = struct.pack(">BHH", 0x03, address, count)
    sock.sendall(struct.pack(">HHHB", tid & 0xFFFF, 0, len(pdu) + 1, unit) + pdu)
    head = _recv(sock, 6)
    length = struct.unpack(">HHH", head)[2]
    body = _recv(sock, length)
    fc = body[1]
    if fc & 0x80:
        return f"eccezione {body[2]}"
    bc = body[2]
    return list(struct.unpack(">" + "H" * count, body[3 : 3 + bc]))


def _recv(sock: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("connessione chiusa dal gateway")
        buf += chunk
    return buf


def signed(v: int) -> int:
    return v - 0x10000 if v & 0x8000 else v


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("host", help="IP del gateway Elfin EW11")
    ap.add_argument("--port", type=int, default=502)
    ap.add_argument("--slave", type=int, default=11, help="indirizzo Modbus (default 11)")
    ap.add_argument("--known", action="store_true", help="leggi i registri noti interpretati")
    ap.add_argument("--scan", nargs=2, type=int, metavar=("START", "END"), help="scansiona un intervallo")
    ap.add_argument("--timeout", type=float, default=5)
    args = ap.parse_args()

    if not args.known and not args.scan:
        args.known = True

    with socket.create_connection((args.host, args.port), timeout=args.timeout) as sock:
        sock.settimeout(args.timeout)
        tid = 0
        if args.known:
            print(f"# Registri noti (slave {args.slave}) — mappa comunità, da validare")
            for addr, (name, scale) in KNOWN.items():
                tid += 1
                res = read_holding(sock, args.slave, addr, 1, tid)
                if isinstance(res, str):
                    print(f"  {addr:>5}  {name:<28} -> {res}")
                else:
                    raw = res[0]
                    val = round(signed(raw) * scale, 1) if scale != 1 else raw
                    print(f"  {addr:>5}  {name:<28} = {val}   (grezzo {raw})")
        if args.scan:
            start, end = args.scan
            print(f"# Scansione {start}-{end} (slave {args.slave}) — solo registri che rispondono")
            for addr in range(start, end + 1):
                tid += 1
                try:
                    res = read_holding(sock, args.slave, addr, 1, tid)
                except (OSError, struct.error) as err:
                    print(f"  {addr:>5}  errore: {err}")
                    continue
                if isinstance(res, list):
                    raw = res[0]
                    print(f"  {addr:>5} = {raw:>6}   (×0.1 -> {signed(raw) * 0.1:.1f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
