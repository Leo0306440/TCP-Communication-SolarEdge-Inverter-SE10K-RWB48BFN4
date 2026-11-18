import time
import inspect
import math
import struct
from datetime import datetime
from pymodbus.client import ModbusTcpClient

# ============================================================
# SOLAREDGE LIVE MONITORING V4
# Inverter: SE10K-RWB48BFN4
# Batteria: Home Battery 48V - 5 moduli
# Richieste in sola lettura!
# ============================================================

INVERTER_IP = "192.168.1.245"
MODBUS_PORT = 1502
SLAVE_ID = 1

BATTERY_BASE = 0xE100

CHECK_INTERVAL = 5
TIMEOUT = 3

client = ModbusTcpClient(
    INVERTER_IP,
    port=MODBUS_PORT,
    timeout=TIMEOUT,
    retries=0
)

# ------------------------------------------------------------
# FUNZIONI MODBUS
# ------------------------------------------------------------

def read_registers(address, count):

    params = inspect.signature(
        client.read_holding_registers
    ).parameters

    kwargs = {
        "address": address,
        "count": count
    }

    if "device_id" in params:
        kwargs["device_id"] = SLAVE_ID
    elif "slave" in params:
        kwargs["slave"] = SLAVE_ID
    else:
        kwargs["unit"] = SLAVE_ID

    try:
        result = client.read_holding_registers(**kwargs)

        if result.isError():
            return None

        return result.registers

    except Exception:
        return None


def signed16(value):
    return value - 65536 if value >= 32768 else value


def read_float(address):

    regs = read_registers(address, 2)

    if regs is None:
        return None

    raw = struct.pack(">HH", regs[1], regs[0])
    value = struct.unpack(">f", raw)[0]

    # Filtra i valori in virgola mobile SunSpec/Modbus non validi
    if not math.isfinite(value) or abs(value) > 1e30:
        return None

    return value


def read_uint32(address):

    regs = read_registers(address, 2)

    if regs is None:
        return None

    return (regs[1] << 16) | regs[0]


# ------------------------------------------------------------
# INVERTER
# ------------------------------------------------------------

def get_inverter_power():

    regs = read_registers(40083, 2)

    if regs is None:
        return None

    power = signed16(regs[0])
    sf = signed16(regs[1])

    return power * (10 ** sf)


# ------------------------------------------------------------
# BATTERIA
# ------------------------------------------------------------

STATUS_NAMES = {
    0: "Spenta",
    1: "Standby",
    2: "Inizializzazione",
    3: "In carica",
    4: "In scarica",
    5: "Errore",
    6: "Carica mantenuta",
    7: "Inattiva",
    10: "Modalità risparmio energetico"
}


def get_battery_data():

    return {
        "capacity": read_float(BATTERY_BASE + 0x42),
        "charge_limit": read_float(BATTERY_BASE + 0x44),
        "discharge_limit": read_float(BATTERY_BASE + 0x46),
        "temperature": read_float(BATTERY_BASE + 0x6C),
        "power": read_float(BATTERY_BASE + 0x74),
        "soe": read_float(BATTERY_BASE + 0x84),
        "status": read_uint32(BATTERY_BASE + 0x86)
    }


# ------------------------------------------------------------
# CONTATORE - PER ORA SOLO DATI GREZZI
# ------------------------------------------------------------

def get_meter_raw():

    return read_registers(40206, 5)


# ------------------------------------------------------------
# OUTPUT
# ------------------------------------------------------------

def display_value(label, value, unit=""):

    if value is None:
        print(f"{label:<30} Non disponibile")
    else:
        print(f"{label:<30} {value:.2f} {unit}")


def display_status(status):

    if status is None:
        print("Stato batteria:                Non disponibile")
    else:
        name = STATUS_NAMES.get(
            status,
            f"Stato sconosciuto ({status})"
        )
        print(f"Stato batteria:                {name}")


def monitor():

    print("\n" * 2)
    print("=" * 65)
    print(" SOLAREDGE LIVE MONITORING V4")
    print("=" * 65)
    print("Inverter:", INVERTER_IP)
    print("Batteria: SolarEdge Home Battery 48V")
    print("Intervallo di interrogazione:", CHECK_INTERVAL, "Sekunden")
    print("Richieste Modbus in sola lettura")
    print("\nPremi CTRL + C per uscire")

    if not client.connect():
        print("ERRORE: impossibile connettersi all’inverter!")
        return

    print("\nConnessione riuscita!")

    while True:

        try:

            inverter_power = get_inverter_power()
            battery = get_battery_data()
            meter = get_meter_raw()

            print("\n")
            print("=" * 65)
            print(" ZEIT:", datetime.now().strftime("%d.%m.%Y %H:%M:%S"))
            print("=" * 65)

            print("\n--- INVERTER ---")

            display_value(
                "Potenza CA inverter:",
                inverter_power,
                "W"
            )

            print("\n--- BATTERIA ---")

            display_value(
                "Stato energetico della batteria:",
                battery["soe"],
                "%"
            )

            display_value(
                "Potenza batteria:",
                battery["power"],
                "W"
            )

            display_value(
                "Temperatura batteria:",
                battery["temperature"],
                "°C"
            )

            display_status(battery["status"])

            print("\n--- DATI TECNICI BATTERIA ---")

            display_value(
                "Capacità nominale:",
                battery["capacity"],
                "Wh"
            )

            display_value(
                "Potenza massima di carica:",
                battery["charge_limit"],
                "W"
            )

            display_value(
                "Potenza massima di scarica:",
                battery["discharge_limit"],
                "W"
            )

            print("\n--- CONTATORE ENERGETICO ---")

            if meter is not None:
                print("Dati grezzi registri 40206-40210:")
                print(meter)
                print("Interpretazione non ancora confermata.")
            else:
                print("Nessun dato ricevuto dal contatore energetico.")

            print("\nProssima interrogazione tra", CHECK_INTERVAL, "secondi.")

            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            print("\nArresto del monitoraggio.")
            break

        except Exception as error:
            print("\nErrore:", repr(error))
            time.sleep(CHECK_INTERVAL)


try:
    monitor()

finally:
    client.close()
    print("\nConnessione Modbus chiusa.")
