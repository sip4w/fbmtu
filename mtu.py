import os
import subprocess
import platform
import sys
from typing import Optional


def ping(host: str, size: int) -> bool:
    """Функция отправляет ICMP-запрос с указанным размером пакета, с учетом ОС."""
    system_name = platform.system()

    if system_name == "Windows":
        # Для Windows: ping -f -l <size> <host>
        # -f: установить флаг "Don't Fragment"
        # -l <size>: установить размер ICMP полезной нагрузки
        # По умолчанию Windows ping отправляет 4 пакета, поэтому используем -n 1
        cmd = [
            "ping",
            "-f",
            "-l", str(size),
            "-n", "1",
            host
        ]
    else:
        # Для Linux/Android/macOS
        # -M do: не фрагментировать пакеты
        # -c 1: количество пакетов
        # -s <size>: размер полезной нагрузки
        # -W <seconds>: таймаут
        cmd = [
            "ping",
            "-M", "do",
            "-c", "1",
            "-s", str(size),
            "-W", "1",
            host
        ]

    try:
        subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True
        )
        return True
    except subprocess.CalledProcessError:
        return False
    except Exception as e:
        print(f"Ошибка выполнения ping: {str(e)}", file=sys.stderr)
        return False


def get_current_mtu(interface: str) -> int:
    """Получает текущее значение MTU для указанного интерфейса (Linux/Android)."""
    # На Windows путь /sys/class/net недоступен.
    # Можно либо вернуть -1, либо использовать WMI (сложнее).
    system_name = platform.system()
    if system_name == "Windows":
        # Для простоты вернем -1
        return -1

    try:
        with open(f"/sys/class/net/{interface}/mtu", "r") as f:
            return int(f.read().strip())
    except Exception as e:
        print(f"Ошибка получения MTU: {str(e)}", file=sys.stderr)
        return -1


def get_default_interface() -> Optional[str]:
    """Определяет интерфейс с активным соединением (Linux/Android)."""
    system_name = platform.system()
    if system_name == "Windows":
        # На Windows возвратим None: здесь можно было бы использовать netsh.
        return None

    try:
        result = subprocess.run(
            ["ip", "route", "show", "default"],
            capture_output=True,
            text=True,
            check=True
        )
        for line in result.stdout.split("\n"):
            if "default" in line:
                parts = line.split()
                if "dev" in parts:
                    return parts[parts.index("dev") + 1]
    except Exception as e:
        print(f"Ошибка определения интерфейса: {str(e)}", file=sys.stderr)
    return None


def get_mtu_traceroute(host: str) -> None:
    """Выполняет трассировку и выводит MTU на промежуточных узлах (Linux/Android)."""
    system_name = platform.system()
    if system_name == "Windows":
        print("\nОпределение MTU по трассировке не реализовано для Windows.")
        return

    try:
        result = subprocess.run(["tracepath", "-n", host], capture_output=True, text=True, check=True)
        print("\nMTU на маршруте:")
        for line in result.stdout.split("\n"):
            if "pmtu" in line:
                print(line)
    except FileNotFoundError:
        print("Утилита tracepath не установлена. Установите: sudo apt install iputils-tracepath")
    except Exception as e:
        print(f"Ошибка выполнения tracepath: {str(e)}", file=sys.stderr)


def find_best_mtu(
    host: str,
    min_mtu: int = 576,        # Минимальный MTU для IPv4
    max_mtu: int = 1500,        # Стандартный Ethernet MTU
    wireguard_overhead: int = 80  # WG: 20(IP) + 8(UDP) + 32(encryption) + 20(padding)
) -> int:
    """Определяет оптимальное значение MTU с учетом overhead WireGuard"""
    adjusted_max = max_mtu - wireguard_overhead
    low, high = min_mtu, adjusted_max
    best_mtu = min_mtu
    
    print(f"Ищем оптимальный MTU в диапазоне {min_mtu}-{adjusted_max} байт")
    
    while low <= high:
        mid = (low + high) // 2
        print(f"Проверяем MTU {mid}...", end=" ", flush=True)
        
        if ping(host, mid):
            print("Успех")
            best_mtu = mid
            low = mid + 1
        else:
            print("Неудача")
            high = mid - 1
    
    return best_mtu + wireguard_overhead  # Возвращаем полный MTU

if __name__ == "__main__":
    system_name = platform.system()

    if system_name not in ("Linux", "Android", "Windows"):
        print("Скрипт предназначен для Linux/Termux (Android) и Windows!", file=sys.stderr)
        sys.exit(1)
    
    # Проверка прав для Linux
    if system_name == "Linux" and os.geteuid() != 0:
        print("Требуются права root! Запустите с sudo.", file=sys.stderr)
        sys.exit(1)

    target_host = "1.1.1.1"

    # На Windows не нужен root для выполнения.

    # Определение интерфейса (для Linux/Android)
    interface = get_default_interface()
    if interface:
        print(f"Определен сетевой интерфейс: {interface}")
        mtu_val = get_current_mtu(interface)
        if mtu_val != -1:
            print(f"Текущий MTU интерфейса {interface}: {mtu_val}")
    else:
        if system_name == "Windows":
            print("Работаем в Windows, интерфейс по умолчанию не определен.")
        else:
            print("Не удалось определить интерфейс!", file=sys.stderr)

    # Трассировка (не реализована для Windows)
    try:
        get_mtu_traceroute(target_host)
    except KeyboardInterrupt:
        print("\nПрервано пользователем.")

    # Поиск оптимального MTU
    try:
        mtu = find_best_mtu(target_host)
        print(f"\nРекомендуемое значение MTU для WireGuard: {mtu}")
        print("Учтите параметры вашего сетевого интерфейса!")
    except KeyboardInterrupt:
        print("\nПрервано пользователем")
        sys.exit(0)
