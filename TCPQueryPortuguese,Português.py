import time
import inspect
import math
import struct
from datetime import datetime
from pymodbus.client import ModbusTcpClient

# ============================================================
# SOLAREDGE LIVE MONITORING V4
# Inversor: SE10K-RWB48BFN4
# Bateria: Home Battery 48V - 5 módulos
# Consultas somente de leitura!
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
# FUNÇÕES MODBUS
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

    # Filtrar valores de ponto flutuante SunSpec/Modbus inválidos
    if not math.isfinite(value) or abs(value) > 1e30:
        return None

    return value


def read_uint32(address):

    regs = read_registers(address, 2)

    if regs is None:
        return None

    return (regs[1] << 16) | regs[0]


# ------------------------------------------------------------
# INVERSOR
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
    0: "Desligada",
    1: "Em espera",
    2: "Inicializando",
    3: "Carregando",
    4: "Descarregando",
    5: "Erro",
    6: "Carga mantida",
    7: "Inativa",
    10: "Modo de economia de energia"
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
# MEDIDOR - POR ENQUANTO, APENAS DADOS BRUTOS
# ------------------------------------------------------------

def get_meter_raw():

    return read_registers(40206, 5)


# ------------------------------------------------------------
# SAÍDA
# ------------------------------------------------------------

def display_value(label, value, unit=""):

    if value is None:
        print(f"{label:<30} Não disponível")
    else:
        print(f"{label:<30} {value:.2f} {unit}")


def display_status(status):

    if status is None:
        print("Estado da bateria:             Não disponível")
    else:
        name = STATUS_NAMES.get(
            status,
            f"Estado desconhecido ({status})"
        )
        print(f"Estado da bateria:             {name}")


def monitor():

    print("\n" * 2)
    print("=" * 65)
    print(" SOLAREDGE LIVE MONITORING V4")
    print("=" * 65)
    print("Inversor:", INVERTER_IP)
    print("Bateria: SolarEdge Home Battery 48V")
    print("Intervalo de consulta:", CHECK_INTERVAL, "Sekunden")
    print("Consultas Modbus somente de leitura")
    print("\nPrima CTRL + C para sair")

    if not client.connect():
        print("ERRO: Falha ao conectar ao inversor!")
        return

    print("\nLigação bem-sucedida!")

    while True:

        try:

            inverter_power = get_inverter_power()
            battery = get_battery_data()
            meter = get_meter_raw()

            print("\n")
            print("=" * 65)
            print(" ZEIT:", datetime.now().strftime("%d.%m.%Y %H:%M:%S"))
            print("=" * 65)

            print("\n--- INVERSOR ---")

            display_value(
                "Potência CA do inversor:",
                inverter_power,
                "W"
            )

            print("\n--- BATERIA ---")

            display_value(
                "Estado de energia da bateria:",
                battery["soe"],
                "%"
            )

            display_value(
                "Potência da bateria:",
                battery["power"],
                "W"
            )

            display_value(
                "Temperatura da bateria:",
                battery["temperature"],
                "°C"
            )

            display_status(battery["status"])

            print("\n--- DADOS TÉCNICOS DA BATERIA ---")

            display_value(
                "Capacidade nominal:",
                battery["capacity"],
                "Wh"
            )

            display_value(
                "Potência máx. de carregamento:",
                battery["charge_limit"],
                "W"
            )

            display_value(
                "Potência máx. de descarga:",
                battery["discharge_limit"],
                "W"
            )

            print("\n--- CONTADOR DE ENERGIA ---")

            if meter is not None:
                print("Dados brutos dos registos 40206-40210:")
                print(meter)
                print("Interpretação ainda não confirmada.")
            else:
                print("Não foram recebidos dados do contador de energia.")

            print("\nPróxima consulta em", CHECK_INTERVAL, "segundos.")

            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            print("\nA monitorização está a ser encerrada.")
            break

        except Exception as error:
            print("\nErro:", repr(error))
            time.sleep(CHECK_INTERVAL)


try:
    monitor()

finally:
    client.close()
    print("\nLigação Modbus encerrada.")
