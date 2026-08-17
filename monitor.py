import socket
import time
import threading
import os
import psutil
from config import AIKA_GAME_EXES

_monitor_lock = threading.Lock()
_monitor_ativo = threading.Event()
_pid_jogo_cache = None

def parar_monitor():
    _monitor_ativo.clear()

def encontrar_ip_ativo_jogo():
    global _pid_jogo_cache
    if _pid_jogo_cache and psutil.pid_exists(_pid_jogo_cache):
        try:
            proc = psutil.Process(_pid_jogo_cache)
            for conn in proc.connections(kind='tcp'):
                if conn.status == 'ESTABLISHED' and conn.raddr:
                    return conn.raddr.ip, conn.raddr.port
        except Exception:
            _pid_jogo_cache = None

    try:
        for proc in psutil.process_iter(['name', 'pid']):
            nome_proc = proc.info['name']
            if nome_proc and nome_proc.lower() in AIKA_GAME_EXES:
                _pid_jogo_cache = proc.info['pid']
                for conn in proc.connections(kind='tcp'):
                    if conn.status == 'ESTABLISHED' and conn.raddr:
                        return conn.raddr.ip, conn.raddr.port
    except Exception:
        pass
    return None, None

def calcular_ping_real(ip, porta):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.0)
        inicio = time.time()
        res = s.connect_ex((ip, porta))
        s.close()
        if res == 0:
            return int((time.time() - inicio) * 1000)
    except Exception:
        pass
    return None

def iniciar_monitor(ip_fallback, porta_fallback, callback):
    if _monitor_ativo.is_set():
        return

    _monitor_ativo.set()
    sistema_drive = os.environ.get("SystemDrive", "C:") + "\\"

    def loop():
        while _monitor_ativo.is_set():
            ip_jogo, porta_jogo = encontrar_ip_ativo_jogo()
            ip_alvo = ip_jogo if ip_jogo else ip_fallback
            porta_alvo = porta_jogo if porta_jogo else porta_fallback

            p = calcular_ping_real(ip_alvo, porta_alvo)

            cor = "#ff4b4b"
            if p:
                if p <= 50: cor = "#00ff00"
                elif p <= 100: cor = "#ffff00"

            try:
                ram = psutil.virtual_memory().percent
                disco = psutil.disk_usage(sistema_drive).percent
                callback(p, cor, ram, disco)
            except Exception:
                pass

            time.sleep(3)

    threading.Thread(target=loop, daemon=True).start()