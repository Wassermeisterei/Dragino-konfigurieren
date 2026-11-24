# Dragino-konfigurieren
## Worum gehts?
Wir wollen es jeder und jedem ermöglichen Bodenfeuchte zumessen.
Hier findest du ein Phyton Skript, um schnell und einfach DraginoRS485 LoRaWAN Funkmodule per AT-Befehlen über UART/USB-Seriell für [SN300 FDR](https://wassermeisterei.org/wp-content/uploads/2026/11/SN-3000-TR-N01_Soil-temperature-and-moisture-transmitter-485-type-manual-1.pdf) Bodenfeuchtesensoren zu konfigurieren.

Das Skript setzt AT Commands für die Messung der Bodenfeuchte für 12 Sensoren (ID 1-12) mit der BAUDRATE 9600 (müssen vorher konfiguriert werden)
Nötig ist ein FTDI FT232 - USB zu TTL UART Konverter.

## Anschluss am Dragino (von aussen nach innen):
Pin1: GND
PIN2: TXD (also RXD am Adapter)
PIN3: RXD (also TXD am Adapter)


<img width="600" height="800" alt="grafik" src="https://github.com/user-attachments/assets/2cba5322-ba9f-4137-b348-4213681436dd" />
