import time
import inspect
import math
import struct
from datetime import datetime
from pymodbus.client import ModbusTcpClient

# ============================================================
# SOLAREDGE LIVE MONITORING V4
# Falownik: SE10K-RWB48BFN4
# Bateria: Home Battery 48V - 5 modułów
# Zapytania tylko do odczytu!
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
# FUNKCJE MODBUS
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

    # Odfiltrowanie nieprawidłowych wartości zmiennoprzecinkowych SunSpec/Modbus
    if not math.isfinite(value) or abs(value) > 1e30:
        return None

    return value


def read_uint32(address):

    regs = read_registers(address, 2)

    if regs is None:
        return None

    return (regs[1] << 16) | regs[0]


# ------------------------------------------------------------
# FALOWNIK
# ------------------------------------------------------------

def get_inverter_power():

    regs = read_registers(40083, 2)

    if regs is None:
        return None

    power = signed16(regs[0])
    sf = signed16(regs[1])

    return power * (10 ** sf)


# ------------------------------------------------------------
# BATERIA
# ------------------------------------------------------------

STATUS_NAMES = {
    0: "Wyłączona",
    1: "Czuwanie",
    2: "Inicjalizacja",
    3: "Ładowanie",
    4: "Rozładowywanie",
    5: "Błąd",
    6: "Podtrzymanie naładowania",
    7: "Beczynna",
    10: "Tryb oszczędzania energii"
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
# LICZNIK - NA RAZIE TYLKO DANE SUROWE
# ------------------------------------------------------------

def get_meter_raw():

    return read_registers(40206, 5)


# ------------------------------------------------------------
# WYJŚCIE
# ------------------------------------------------------------

def display_value(label, value, unit=""):

    if value is None:
        print(f"{label:<30} Niedostępne")
    else:
        print(f"{label:<30} {value:.2f} {unit}")


def display_status(status):

    if status is None:
        print("Stan baterii:                  Niedostępne")
    else:
        name = STATUS_NAMES.get(
            status,
            f"Nieznany stan ({status})"
        )
        print(f"Stan baterii:                  {name}")


def monitor():

    print("\n" * 2)
    print("=" * 65)
    print(" SOLAREDGE LIVE MONITORING V4")
    print("=" * 65)
    print("Falownik:", INVERTER_IP)
    print("Bateria: SolarEdge Home Battery 48V")
    print("Interwał odpytywania:", CHECK_INTERVAL, "Sekunden")
    print("Zapytania Modbus tylko do odczytu")
    print("\nNaciśnij CTRL + C, aby zakończyć")

    if not client.connect():
        print("BŁĄD: Nie udało się połączyć z falownikiem!")
        return

    print("\nPołączenie udane!")

    while True:

        try:

            inverter_power = get_inverter_power()
            battery = get_battery_data()
            meter = get_meter_raw()

            print("\n")
            print("=" * 65)
            print(" ZEIT:", datetime.now().strftime("%d.%m.%Y %H:%M:%S"))
            print("=" * 65)

            print("\n--- FALOWNIK ---")

            display_value(
                "Moc AC falownika:",
                inverter_power,
                "W"
            )

            print("\n--- BATERIA ---")

            display_value(
                "Poziom energii baterii:",
                battery["soe"],
                "%"
            )

            display_value(
                "Moc baterii:",
                battery["power"],
                "W"
            )

            display_value(
                "Temperatura baterii:",
                battery["temperature"],
                "°C"
            )

            display_status(battery["status"])

            print("\n--- DANE TECHNICZNE BATERII ---")

            display_value(
                "Pojemność nominalna:",
                battery["capacity"],
                "Wh"
            )

            display_value(
                "Maks. moc ładowania:",
                battery["charge_limit"],
                "W"
            )

            display_value(
                "Maks. moc rozładowywania:",
                battery["discharge_limit"],
                "W"
            )

            print("\n--- LICZNIK ENERGII ---")

            if meter is not None:
                print("Dane surowe rejestrów 40206-40210:")
                print(meter)
                print("Interpretacja nie została jeszcze potwierdzona.")
            else:
                print("Nie odebrano danych z licznika energii.")

            print("\nNastępne odpytywanie za", CHECK_INTERVAL, "sekund.")

            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            print("\nMonitorowanie zostaje zatrzymane.")
            break

        except Exception as error:
            print("\nBłąd:", repr(error))
            time.sleep(CHECK_INTERVAL)


try:
    monitor()

finally:
    client.close()
    print("\nPołączenie Modbus zostało zamknięte.")
