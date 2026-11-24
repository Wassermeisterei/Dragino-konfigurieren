#!/usr/bin/env python3
"""
SN-3000 Bodenfeuchtesensor (RS485 / Modbus RTU): Sensoren nacheinander konfigurieren.

Ablauf:
  Alle Sensoren werden ab Werk mit derselben Adresse ausgeliefert (meist 1).
  Deshalb immer nur EINEN Sensor an den RS485-Bus anschließen, das Skript
  sucht ihn, vergibt eine neue Adresse (und optional eine Baudrate), prüft
  das Ergebnis, und dann folgt der nächste Sensor.

Register (übliche SN-3000-Belegung, bitte mit deinem Datenblatt abgleichen):
  0x0000  Feuchte        (Wert / 10 = %)
  0x0001  Temperatur     (Wert / 10 = °C, vorzeichenbehaftet)
  0x07D0  Geräteadresse  (1–254)
  0x07D1  Baudrate       (0 = 2400, 1 = 4800, 2 = 9600)

Benötigt: pip install pyserial

Beispiele:
  python3 sn3000_konfig.py --port /dev/ttyUSB0 --start-adresse 1
  python3 sn3000_konfig.py --port /dev/ttyUSB0 --start-adresse 10 --ziel-baud 9600
  python3 sn3000_konfig.py --port COM3 --start-adresse 2 --vollscan
"""

import argparse
import struct
import sys
import time

try:
    import serial
except ImportError:
    sys.exit("pyserial fehlt. Bitte installieren: pip install pyserial")

REG_FEUCHTE = 0x0000
REG_TEMPERATUR = 0x0001
REG_ADRESSE = 0x07D0
REG_BAUD = 0x07D1

BAUD_CODES = {2400: 0, 4800: 1, 9600: 2}
BAUD_AUS_CODE = {v: k for k, v in BAUD_CODES.items()}
BAUDRATEN_SCAN = [4800, 9600, 2400]   # 4800 ist  Werkszustand
ABFRAGE_ADRESSE = 0xFF                 #  SN-3000 antworten auf 0xFF mit ihrer echten Adresse


def crc16(daten: bytes) -> bytes:
    """Modbus-RTU-CRC16, Low-Byte zuerst."""
    crc = 0xFFFF
    for b in daten:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return struct.pack("<H", crc)


class ModbusRTU:
    def __init__(self, port: str, baud: int, timeout: float = 0.5):
        self.ser = serial.Serial(port, baud, bytesize=8, parity="N",
                                 stopbits=1, timeout=timeout)

    def baud_setzen(self, baud: int):
        self.ser.baudrate = baud
        time.sleep(0.05)

    def schliessen(self):
        self.ser.close()

    def _senden(self, rahmen: bytes, antwort_laenge: int):
        rahmen += crc16(rahmen)
        self.ser.reset_input_buffer()
        self.ser.write(rahmen)
        self.ser.flush()
        antwort = self.ser.read(antwort_laenge)
        time.sleep(0.05)  # kurze Pause zwischen Telegrammen
        if len(antwort) < 5 or crc16(antwort[:-2]) != antwort[-2:]:
            return None
        if antwort[1] & 0x80:  # Modbus-Fehlerantwort
            return None
        return antwort

    def register_lesen(self, adresse: int, start: int, anzahl: int = 1):
        """Liefert (antwortende_adresse, [werte]) oder None."""
        rahmen = struct.pack(">BBHH", adresse, 0x03, start, anzahl)
        antwort = self._senden(rahmen, 5 + 2 * anzahl)
        if antwort is None or antwort[1] != 0x03 or antwort[2] != 2 * anzahl:
            return None
        werte = list(struct.unpack(">" + "H" * anzahl, antwort[3:3 + 2 * anzahl]))
        return antwort[0], werte

    def register_schreiben(self, adresse: int, register: int, wert: int) -> bool:
        rahmen = struct.pack(">BBHH", adresse, 0x06, register, wert)
        antwort = self._senden(rahmen, 8)
        return antwort is not None and antwort[1] == 0x06


def sensor_suchen(bus: ModbusRTU, vollscan: bool):
    """Sucht angeschlossenen Sensor. Gibt (baud, adresse) oder None zurück."""
    for baud in BAUDRATEN_SCAN:
        bus.baud_setzen(baud)
        print(f"  Suche bei {baud} Baud ...")

        # 1) Abfrage über die Sammeladresse 0xFF
        r = bus.register_lesen(ABFRAGE_ADRESSE, REG_ADRESSE)
        if r:
            return baud, r[1][0]

        # 2) Werksadresse 1
        r = bus.register_lesen(1, REG_ADRESSE)
        if r:
            return baud, 1

        # 3) optional alle Adressen durchprobieren
        if vollscan:
            for adr in range(2, 255):
                r = bus.register_lesen(adr, REG_ADRESSE)
                if r:
                    return baud, adr
    return None


def messwerte_lesen(bus: ModbusRTU, adresse: int):
    r = bus.register_lesen(adresse, REG_FEUCHTE, 2)
    if not r:
        return None
    feuchte, temp = r[1]
    if temp >= 0x8000:
        temp -= 0x10000
    return feuchte / 10.0, temp / 10.0


def einen_sensor_konfigurieren(bus, neue_adresse, ziel_baud, vollscan):
    gefunden = sensor_suchen(bus, vollscan)
    if not gefunden:
        print("  Kein Sensor gefunden. Verkabelung (A/B), Versorgung und Port prüfen.")
        return False

    akt_baud, akt_adresse = gefunden
    print(f"  Sensor gefunden: Adresse {akt_adresse}, {akt_baud} Baud")

    mw = messwerte_lesen(bus, akt_adresse)
    if mw:
        print(f"  Messwerte: Feuchte {mw[0]:.1f} %, Temperatur {mw[1]:.1f} °C")

    # --- Adresse setzen ---
    if akt_adresse != neue_adresse:
        print(f"  Setze Adresse {akt_adresse} -> {neue_adresse} ...")
        bus.register_schreiben(akt_adresse, REG_ADRESSE, neue_adresse)
        time.sleep(0.3)
        r = bus.register_lesen(neue_adresse, REG_ADRESSE)
        if not r or r[1][0] != neue_adresse:
            print("  FEHLER: Sensor antwortet nicht unter der neuen Adresse.")
            return False
        print("  Adresse OK.")
    else:
        print(f"  Adresse ist bereits {neue_adresse}.")

    # --- Baudrate setzen (optional) ---
    if ziel_baud and ziel_baud != akt_baud:
        print(f"  Setze Baudrate {akt_baud} -> {ziel_baud} ...")
        bus.register_schreiben(neue_adresse, REG_BAUD, BAUD_CODES[ziel_baud])
        input("  Neue Baudrate wird nach Neustart aktiv.\n"
              "  Rotes Sensorkabel abhängen, wieder anhängen und Enter drücken ...")
        bus.baud_setzen(ziel_baud)
        time.sleep(0.5)
        r = bus.register_lesen(neue_adresse, REG_BAUD)
        if not r or BAUD_AUS_CODE.get(r[1][0]) != ziel_baud:
            print("  FEHLER: Sensor antwortet nicht mit der neuen Baudrate.")
            return False
        print("  Baudrate OK.")

    mw = messwerte_lesen(bus, neue_adresse)
    if mw:
        print(f"  Kontrolle: Feuchte {mw[0]:.1f} %, Temperatur {mw[1]:.1f} °C")
    return True


def main():
    p = argparse.ArgumentParser(description="SN-3000 Sensoren nacheinander konfigurieren")
    p.add_argument("--port", default="/dev/ttyUSB0", help="Serieller Port (z. B. /dev/ttyUSB0 oder COM3)")
    p.add_argument("--start-adresse", type=int, default=1, help="Adresse für den ersten Sensor (1–254)")
    p.add_argument("--ziel-baud", type=int, choices=sorted(BAUD_CODES), default=9600, help="Neue Baudrate (Standard: 9600)")
    p.add_argument("--anzahl", type=int, help="Anzahl Sensoren (ohne Angabe: bis 'q')")
    p.add_argument("--vollscan", action="store_true", help="Falls nicht gefunden: alle Adressen 1–254 absuchen")
    args = p.parse_args()

    if not 1 <= args.start_adresse <= 254:
        sys.exit("Startadresse muss zwischen 1 und 254 liegen.")

    bus = ModbusRTU(args.port, BAUDRATEN_SCAN[0])
    adresse = args.start_adresse
    ergebnisse = []
    nr = 1

    try:
        while args.anzahl is None or nr <= args.anzahl:
            if adresse > 254:
                print("Maximale Adresse 254 erreicht.")
                break
            eingabe = input(f"\nSensor #{nr} "
                            f"anschließen und Enter drücken (q = Ende) ... ").strip().lower()
            if eingabe == "q":
                break

            ok = einen_sensor_konfigurieren(bus, adresse, args.ziel_baud, args.vollscan)
            if ok:
                ergebnisse.append((nr, adresse))
                print(f"  ✔ Sensor #{nr} fertig: Adresse {adresse}. Bitte beschriften und abklemmen.")
                adresse += 1
                nr += 1
            else:
                if input("  Nochmal versuchen? (j/n) ").strip().lower() != "j":
                    nr += 1  # Sensor überspringen, Adresse bleibt frei für den nächsten
    except KeyboardInterrupt:
        print("\nAbgebrochen.")
    finally:
        bus.schliessen()

    print("\n=== Zusammenfassung ===")
    for nr, adr in ergebnisse:
        print(f"  Sensor #{nr}: Adresse {adr}" + (f", {args.ziel_baud} Baud" if args.ziel_baud else ""))
    if not ergebnisse:
        print("  Keine Sensoren konfiguriert.")


if __name__ == "__main__":
    main()
