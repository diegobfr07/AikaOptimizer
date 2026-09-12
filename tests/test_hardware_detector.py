# -*- coding: utf-8 -*-
"""Testes do servico puro de deteccao de hardware (V2.3A).

Todos os testes mockam a consulta PowerShell/WMI. Nunca dependem do
hardware real da maquina. A heuristica e testada sem executar WMI.
"""
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hardware_detector as hd


def _gpu(**kwargs):
    """Factory de GpuInfo com defaults seguros."""
    base = {
        "name": "NVIDIA GeForce GPU",
        "vendor": hd.VENDOR_UNKNOWN,
        "vram_mb": None,
        "integrated": None,
        "dedicated": None,
        "status_ok": True,
    }
    base.update(kwargs)
    return hd.GpuInfo(**base)


def _igpu(nome="Intel(R) UHD Graphics", vram_mb=None, status_ok=True):
    return _gpu(name=nome, vendor=hd.VENDOR_INTEL, vram_mb=vram_mb,
                integrated=True, dedicated=False, status_ok=status_ok)


def _dgpu(nome, vram_mb, status_ok=True, vendor=hd.VENDOR_NVIDIA):
    return _gpu(name=nome, vendor=vendor, vram_mb=vram_mb,
                integrated=False, dedicated=True, status_ok=status_ok)


class TestHeuristicaBasica(unittest.TestCase):
    def test_apenas_igpu_performance(self):
        r = hd.recomendar_perfil([_igpu()])
        self.assertEqual(r.recommended_profile, hd.PERFIL_PERFORMANCE)

    def test_dgpu_1gb_performance(self):
        r = hd.recomendar_perfil([_dgpu("NVIDIA GeForce GT 1030", 1024)])
        self.assertEqual(r.recommended_profile, hd.PERFIL_PERFORMANCE)

    def test_dgpu_2gb_performance(self):
        r = hd.recomendar_perfil([_dgpu("NVIDIA GeForce GTX 950", 2048)])
        self.assertEqual(r.recommended_profile, hd.PERFIL_PERFORMANCE)

    def test_dgpu_4gb_balanced(self):
        r = hd.recomendar_perfil([_dgpu("NVIDIA GeForce GTX 1650", 4096)])
        self.assertEqual(r.recommended_profile, hd.PERFIL_BALANCED)

    def test_dgpu_6gb_quality(self):
        r = hd.recomendar_perfil([_dgpu("NVIDIA GeForce RTX 3060", 6144)])
        self.assertEqual(r.recommended_profile, hd.PERFIL_QUALITY)

    def test_dgpu_8gb_quality(self):
        r = hd.recomendar_perfil([_dgpu("NVIDIA GeForce RTX 3080", 8192)])
        self.assertEqual(r.recommended_profile, hd.PERFIL_QUALITY)

    def test_hibrido_intel_nvidia_6gb_quality_confianca_media(self):
        r = hd.recomendar_perfil([
            _igpu("Intel(R) UHD Graphics"),
            _dgpu("NVIDIA GeForce RTX 3060", 6144),
        ])
        self.assertEqual(r.recommended_profile, hd.PERFIL_QUALITY)
        self.assertEqual(r.confidence, hd.CONFIANCA_MEDIA)

    def test_amd_nao_classifica_por_fabricante(self):
        # "AMD Radeon(TM) Graphics" (APU) e integrada, NAO dedicada
        r = hd.recomendar_perfil([
            _gpu(name="AMD Radeon(TM) Graphics", vendor=hd.VENDOR_AMD,
                 integrated=True, dedicated=False, status_ok=True)
        ])
        self.assertEqual(r.recommended_profile, hd.PERFIL_PERFORMANCE)

    def test_dgpu_vram_none_balanced(self):
        r = hd.recomendar_perfil([_dgpu("NVIDIA GeForce GPU", None)])
        self.assertEqual(r.recommended_profile, hd.PERFIL_BALANCED)

    def test_adapter_ram_zero_vira_none(self):
        self.assertIsNone(hd._normalizar_vram_mb(0))
        r = hd.recomendar_perfil([_dgpu("NVIDIA GeForce GTX 950", 0)])
        self.assertEqual(r.recommended_profile, hd.PERFIL_BALANCED)

    def test_adapter_ram_absurdo_vira_none(self):
        self.assertIsNone(hd._normalizar_vram_mb(10 ** 12))
        self.assertIsNone(hd._normalizar_vram_mb("abc"))
        self.assertIsNone(hd._normalizar_vram_mb(-5))

    def test_lista_vazia_balanced_baixa(self):
        r = hd.recomendar_perfil([])
        self.assertEqual(r.recommended_profile, hd.PERFIL_BALANCED)
        self.assertEqual(r.confidence, hd.CONFIANCA_BAIXA)


class TestColetaComMock(unittest.TestCase):
    def setUp(self):
        # Comportamento legado: fonte 64-bit indisponível -> WMI puro
        p = mock.patch.object(hd, "_vram_system_enriquecer", return_value=[])
        p.start()
        self.addCleanup(p.stop)

    def _mock_stdout(self, saida):
        p = mock.patch.object(hd, "_executar_powershell_oculto", return_value=saida)
        p.start()
        self.addCleanup(p.stop)

    def test_objeto_unico_json(self):
        item = {"Name": "NVIDIA GeForce RTX 3060",
                "PNPDeviceID": "PCI\\VEN_10DE&DEV_2503",
                "AdapterRAM": 6442450944,
                "Status": "OK", "VideoModeDescription": "1920 x 1080"}
        self._mock_stdout(json.dumps(item))
        gpus = hd.detectar_gpus()
        self.assertEqual(len(gpus), 1)
        self.assertEqual(gpus[0].vendor, hd.VENDOR_NVIDIA)
        self.assertEqual(gpus[0].vram_mb, 6144)
        self.assertIs(gpus[0].status_ok, True)

    def test_array_varias_gpus(self):
        itens = [
            {"Name": "Intel(R) UHD Graphics",
             "PNPDeviceID": "PCI\\VEN_8086&DEV_9BC4", "AdapterRAM": 0,
             "Status": "OK"},
            {"Name": "NVIDIA GeForce RTX 3060",
             "PNPDeviceID": "PCI\\VEN_10DE&DEV_2503", "AdapterRAM": 6442450944,
             "Status": "OK"},
        ]
        self._mock_stdout(json.dumps(itens))
        gpus = hd.detectar_gpus()
        self.assertEqual(len(gpus), 2)
        r = hd.recomendar_perfil(gpus)
        self.assertEqual(r.recommended_profile, hd.PERFIL_QUALITY)

    def test_json_invalido_balanced(self):
        self._mock_stdout("{invalido")
        r = hd.detectar_hardware()
        self.assertEqual(r.recommended_profile, hd.PERFIL_BALANCED)
        self.assertEqual(r.confidence, hd.CONFIANCA_BAIXA)

    def test_powershell_falha(self):
        self._mock_stdout(None)
        r = hd.detectar_hardware()
        self.assertEqual(r.recommended_profile, hd.PERFIL_BALANCED)

    def test_saida_vazia_balanced(self):
        self._mock_stdout("")
        r = hd.detectar_hardware()
        self.assertEqual(r.recommended_profile, hd.PERFIL_BALANCED)

    def test_vendor_amd_ven_1002(self):
        gpu = hd._parsear_item_gpu({"Name": "AMD Radeon RX 6600",
                                    "PNPDeviceID": "PCI\\VEN_1002&DEV_73FF"})
        self.assertEqual(gpu.vendor, hd.VENDOR_AMD)

    def test_vendor_intel_ven_8086(self):
        gpu = hd._parsear_item_gpu({"Name": "Intel(R) Arc A770",
                                    "PNPDeviceID": "PCI\\VEN_8086&DEV_56A0"})
        self.assertEqual(gpu.vendor, hd.VENDOR_INTEL)

    def test_vendor_desconhecido(self):
        gpu = hd._parsear_item_gpu({"Name": "Placa X",
                                    "PNPDeviceID": "PCI\\VEN_1234&DEV_0001"})
        self.assertEqual(gpu.vendor, hd.VENDOR_UNKNOWN)

    def test_status_nao_ok_impede_quality(self):
        gpu = _dgpu("NVIDIA GeForce RTX 3080", 8192, status_ok=False)
        r = hd.recomendar_perfil([gpu])
        self.assertNotEqual(r.recommended_profile, hd.PERFIL_QUALITY)

    def test_status_nao_ok_parse(self):
        item = {"Name": "NVIDIA GeForce RTX 3080",
                "PNPDeviceID": "PCI\\VEN_10DE&DEV_2206", "AdapterRAM": 8589934592,
                "Status": "Error"}
        gpu = hd._parsear_item_gpu(item)
        self.assertIs(gpu.status_ok, False)

    def test_multiplas_gpus_usa_mais_forte(self):
        gpus = [
            _igpu("Intel(R) UHD Graphics"),
            _dgpu("NVIDIA GeForce GTX 1650", 4096),
            _dgpu("NVIDIA GeForce RTX 3080", 8192),
        ]
        r = hd.recomendar_perfil(gpus)
        self.assertEqual(r.recommended_profile, hd.PERFIL_QUALITY)


class TestImportSemEfeitos(unittest.TestCase):
    def test_import_nao_executa_powershell(self):
        """Importar hardware_detector num interpretador limpo não executa WMI."""
        import subprocess
        raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        codigo = (
            "import sys; sys.path.insert(0, {raiz!r}); "
            "import hardware_detector; print('IMPORT_OK')"
        ).format(raiz=raiz)
        resultado = subprocess.run(
            [sys.executable, "-c", codigo],
            capture_output=True, text=True, timeout=30,
        )
        self.assertIn("IMPORT_OK", resultado.stdout)


class TestVramSistema64(unittest.TestCase):
    """Integracao WMI + Registro (VRAM 64-bit) (V2.3A.1)."""

    def _mock_wmi(self, itens):
        saida = json.dumps(itens)
        p = mock.patch.object(hd, "_executar_powershell_oculto", return_value=saida)
        p.start()
        self.addCleanup(p.stop)

    def _mock_sistema(self, adapters):
        p = mock.patch.object(hd, "_vram_system_enriquecer", return_value=adapters)
        p.start()
        self.addCleanup(p.stop)

    def test_wmi_4095_sistema_6144_quality(self):
        self._mock_wmi({"Name": "NVIDIA GeForce RTX 4050 Laptop GPU",
                        "PNPDeviceID": "PCI\\VEN_10DE&DEV_28A0",
                        "AdapterRAM": 4095 * 1024 * 1024, "Status": "OK"})
        self._mock_sistema([{"name": "NVIDIA GeForce RTX 4050 Laptop GPU",
                          "vendor": "nvidia", "vram_mb": 6144}])
        r = hd.detectar_hardware()
        self.assertEqual(r.recommended_profile, hd.PERFIL_QUALITY)
        self.assertEqual(r.confidence, hd.CONFIANCA_ALTA)

    def test_wmi_4095_sistema_6141_quality(self):
        # Caso real: placa 6 GB reporta ~6141 MB dedicados (reserva do driver)
        self._mock_wmi({"Name": "NVIDIA GeForce RTX 4050 Laptop GPU",
                        "PNPDeviceID": "PCI\\VEN_10DE&DEV_28A0",
                        "AdapterRAM": 4095 * 1024 * 1024, "Status": "OK"})
        self._mock_sistema([{"name": "NVIDIA GeForce RTX 4050 Laptop GPU",
                          "vendor": "nvidia", "vram_mb": 6141}])
        gpus = hd.detectar_gpus()
        self.assertEqual(gpus[0].vram_mb, 6141)  # valor reportado preservado
        self.assertEqual(gpus[0].vram_source, "system")
        r = hd.recomendar_perfil(gpus)
        self.assertEqual(r.recommended_profile, hd.PERFIL_QUALITY)
        self.assertEqual(r.confidence, hd.CONFIANCA_ALTA)

    def test_vram_nominal_mb(self):
        self.assertEqual(hd._vram_nominal_mb(None), None)
        self.assertEqual(hd._vram_nominal_mb(6144), 6144)
        self.assertEqual(hd._vram_nominal_mb(6141), 6144)   # 6 GB nominal
        self.assertEqual(hd._vram_nominal_mb(4093), 4096)   # 4 GB nominal
        self.assertEqual(hd._vram_nominal_mb(2048), 2048)
        self.assertEqual(hd._vram_nominal_mb(2045), 2048)   # 2 GB nominal
        self.assertEqual(hd._vram_nominal_mb(6000), 6000)   # nao nominal: mantido

    def test_wmi_4095_sistema_8192_quality(self):
        self._mock_wmi({"Name": "NVIDIA GeForce RTX 3080",
                        "PNPDeviceID": "PCI\\VEN_10DE&DEV_2206",
                        "AdapterRAM": 4095 * 1024 * 1024, "Status": "OK"})
        self._mock_sistema([{"name": "NVIDIA GeForce RTX 3080",
                          "vendor": "nvidia", "vram_mb": 8192}])
        r = hd.detectar_hardware()
        self.assertEqual(r.recommended_profile, hd.PERFIL_QUALITY)

    def test_wmi_2048_sistema_2048_performance(self):
        self._mock_wmi({"Name": "NVIDIA GeForce GTX 950",
                        "PNPDeviceID": "PCI\\VEN_10DE&DEV_1402",
                        "AdapterRAM": 2048 * 1024 * 1024, "Status": "OK"})
        self._mock_sistema([{"name": "NVIDIA GeForce GTX 950",
                          "vendor": "nvidia", "vram_mb": 2048}])
        r = hd.detectar_hardware()
        self.assertEqual(r.recommended_profile, hd.PERFIL_PERFORMANCE)

    def test_wmi_4095_sem_dxgi_conservador(self):
        self._mock_wmi({"Name": "NVIDIA GeForce RTX 4050 Laptop GPU",
                        "PNPDeviceID": "PCI\\VEN_10DE&DEV_28A0",
                        "AdapterRAM": 4095 * 1024 * 1024, "Status": "OK"})
        self._mock_sistema([])
        r = hd.detectar_hardware()
        # 4095 -> faixa intermediaria -> balanced; confianca MEDIA (teto suspeito)
        self.assertEqual(r.recommended_profile, hd.PERFIL_BALANCED)
        self.assertEqual(r.confidence, hd.CONFIANCA_MEDIA)

    def test_wmi_4095_sistema_ambiguo_nao_mistura(self):
        self._mock_wmi({"Name": "NVIDIA GeForce RTX 4050 Laptop GPU",
                        "PNPDeviceID": "PCI\\VEN_10DE&DEV_28A0",
                        "AdapterRAM": 4095 * 1024 * 1024, "Status": "OK"})
        # dois DXGI com o mesmo nome normalizado -> ambiguo, nao atribuir
        self._mock_sistema([
            {"name": "NVIDIA GeForce RTX 4050 Laptop GPU", "vendor": "nvidia", "vram_mb": 6144},
            {"name": "NVIDIA GeForce RTX 4050 Laptop GPU", "vendor": "nvidia", "vram_mb": 8192},
        ])
        gpus = hd.detectar_gpus()
        self.assertEqual(len(gpus), 1)
        self.assertEqual(gpus[0].vram_mb, 4095)  # mantem WMI
        self.assertEqual(gpus[0].vram_source, "wmi")
        r = hd.recomendar_perfil(gpus)
        self.assertEqual(r.recommended_profile, hd.PERFIL_BALANCED)

    def test_hibrido_intel_nvidia_sistema_associa_cada_uma(self):
        self._mock_wmi([
            {"Name": "Intel(R) UHD Graphics",
             "PNPDeviceID": "PCI\\VEN_8086&DEV_9BC4", "AdapterRAM": 0, "Status": "OK"},
            {"Name": "NVIDIA GeForce RTX 4050 Laptop GPU",
             "PNPDeviceID": "PCI\\VEN_10DE&DEV_28A0",
             "AdapterRAM": 4095 * 1024 * 1024, "Status": "OK"},
        ])
        self._mock_sistema([
            {"name": "Intel(R) UHD Graphics", "vendor": "intel", "vram_mb": 0},
            {"name": "NVIDIA GeForce RTX 4050 Laptop GPU", "vendor": "nvidia", "vram_mb": 6144},
        ])
        gpus = hd.detectar_gpus()
        por_nome = {g.name: g for g in gpus}
        self.assertEqual(por_nome["NVIDIA GeForce RTX 4050 Laptop GPU"].vram_mb, 6144)
        self.assertEqual(por_nome["NVIDIA GeForce RTX 4050 Laptop GPU"].vram_source, "system")
        r = hd.recomendar_perfil(gpus)
        self.assertEqual(r.recommended_profile, hd.PERFIL_QUALITY)
        self.assertEqual(r.confidence, hd.CONFIANCA_MEDIA)  # hibrido

    def test_duas_dgpu_mesmo_fabricante_nao_misturam(self):
        self._mock_wmi([
            {"Name": "NVIDIA GeForce GTX 1650",
             "PNPDeviceID": "PCI\\VEN_10DE&DEV_1F82",
             "AdapterRAM": 4096 * 1024 * 1024, "Status": "OK"},
            {"Name": "NVIDIA GeForce RTX 3080",
             "PNPDeviceID": "PCI\\VEN_10DE&DEV_2206",
             "AdapterRAM": 8192 * 1024 * 1024, "Status": "OK"},
        ])
        self._mock_sistema([
            {"name": "NVIDIA GeForce GTX 1650", "vendor": "nvidia", "vram_mb": 4096},
            {"name": "NVIDIA GeForce RTX 3080", "vendor": "nvidia", "vram_mb": 10240},
        ])
        gpus = hd.detectar_gpus()
        por_nome = {g.name: g for g in gpus}
        self.assertEqual(por_nome["NVIDIA GeForce GTX 1650"].vram_mb, 4096)
        self.assertEqual(por_nome["NVIDIA GeForce RTX 3080"].vram_mb, 10240)
        r = hd.recomendar_perfil(gpus)
        self.assertEqual(r.recommended_profile, hd.PERFIL_QUALITY)

    def test_sistema_falha_fallback_wmi(self):
        self._mock_wmi({"Name": "NVIDIA GeForce RTX 3080",
                        "PNPDeviceID": "PCI\\VEN_10DE&DEV_2206",
                        "AdapterRAM": 8192 * 1024 * 1024, "Status": "OK"})
        # Falha na leitura do Registro: o wrapper captura e retorna []
        p = mock.patch.object(hd, "_vram_system_adaptadores",
                              side_effect=Exception("registro indisponivel"))
        p.start()
        self.addCleanup(p.stop)
        r = hd.detectar_hardware()
        self.assertEqual(r.recommended_profile, hd.PERFIL_QUALITY)
        self.assertEqual(r.confidence, hd.CONFIANCA_ALTA)

    def test_sistema_zero_ignorado(self):
        self._mock_wmi({"Name": "NVIDIA GeForce GTX 1650",
                        "PNPDeviceID": "PCI\\VEN_10DE&DEV_1F82",
                        "AdapterRAM": 4096 * 1024 * 1024, "Status": "OK"})
        self._mock_sistema([{"name": "NVIDIA GeForce GTX 1650",
                          "vendor": "nvidia", "vram_mb": 0}])
        gpus = hd.detectar_gpus()
        self.assertEqual(gpus[0].vram_mb, 4096)  # mantem WMI
        self.assertEqual(gpus[0].vram_source, "wmi")

    def test_sistema_absurdo_ignorado(self):
        self._mock_wmi({"Name": "NVIDIA GeForce RTX 3080",
                        "PNPDeviceID": "PCI\\VEN_10DE&DEV_2206",
                        "AdapterRAM": 8192 * 1024 * 1024, "Status": "OK"})
        self._mock_sistema([{"name": "NVIDIA GeForce RTX 3080",
                          "vendor": "nvidia", "vram_mb": 500000}])  # absurdo
        gpus = hd.detectar_gpus()
        self.assertEqual(gpus[0].vram_mb, 8192)
        self.assertEqual(gpus[0].vram_source, "wmi")


if __name__ == "__main__":
    unittest.main()


