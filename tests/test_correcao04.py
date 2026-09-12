# -*- coding: utf-8 -*-
"""
CORREÇÃO CONTROLADA 04 — Testes não destrutivos do sistema de Áudio.

Cobre: detecção de formato pelo CONTEÚDO (não pela extensão), preview honesto,
compatibilidade WAV/WAV OGG/OGG MP3/MP3, recusa de formatos diferentes sem
conversor, backup obrigatório antes da escrita, falha de backup/escrita sem
corromper o original, restore por cliente correto, mensagens [ERRO] honestas.

NÃO toca: cliente AIKA real, áudio do usuário, Windows, Registry, processos.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import audio  # noqa: E402


# ============================================================
# ARQUIVOS SINTÉTICOS
# ============================================================
WAV_BYTES = (b"RIFF" + (36).to_bytes(4, "little") + b"WAVE" +
             b"fmt " + (16).to_bytes(4, "little") +
             b"\x01\x00\x01\x00" + b"\x44\xac\x00\x00" +
             b"\x88\x58\x01\x00" + b"\x02\x00\x10\x00" +
             b"data" + (0).to_bytes(4, "little"))
OGG_BYTES = b"OggS" + b"\x00\x02" + b"vorbis-exemplo" * 4
MP3_ID3 = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"mp3-frame-exemplo" * 8
MP3_RAW = b"\xFF\xFB\x90\x44" + b"mpeg-frame" * 8
M4A_BYTES = b"\x00\x00\x00\x18ftypM4A \x00\x00\x00\x00" + b"iso-bmff" * 8
UNKNOWN_BYTES = b"\x00\x11\x22\x33\x44\x55\x66\x77" + b"lixo" * 8


def criar(td, nome, conteudo):
    caminho = os.path.join(td, nome)
    with open(caminho, "wb") as f:
        f.write(conteudo)
    return caminho


# ============================================================
# 1) DETECÇÃO PELO CONTEÚDO
# ============================================================
class TestDeteccaoFormato(unittest.TestCase):
    def test_wav_dentro_de_bin(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(audio.detectar_formato_audio(criar(td, "som.bin", WAV_BYTES)), "WAV")

    def test_nao_confia_na_extensao_wav_com_mp3(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(audio.detectar_formato_audio(criar(td, "falso.wav", MP3_ID3)), "MP3")
            self.assertEqual(audio.detectar_formato_audio(criar(td, "falso2.wav", MP3_RAW)), "MP3")

    def test_ogg(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(audio.detectar_formato_audio(criar(td, "a.ogg", OGG_BYTES)), "OGG")

    def test_mp3_id3(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(audio.detectar_formato_audio(criar(td, "a.mp3", MP3_ID3)), "MP3")

    def test_m4a_ftyp(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(audio.detectar_formato_audio(criar(td, "a.m4a", M4A_BYTES)), "M4A")

    def test_unknown(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(audio.detectar_formato_audio(criar(td, "a.dat", UNKNOWN_BYTES)), "UNKNOWN")

    def test_arquivo_inexistente_e_unknown(self):
        self.assertEqual(audio.detectar_formato_audio(r"Z:\nao\existe.bin"), "UNKNOWN")


# ============================================================
# 2) PREVIEW HONESTO
# ============================================================
class TestPrevia(unittest.TestCase):
    def test_previa_wav_bin_gera_tmp_wav(self):
        with tempfile.TemporaryDirectory() as td:
            origem = criar(td, "musica.bin", WAV_BYTES)
            previa = audio.preparar_previa_audio(origem)
            try:
                self.assertIsNotNone(previa)
                self.assertTrue(previa.endswith(".wav"))
                with open(previa, "rb") as f:
                    self.assertEqual(f.read(), WAV_BYTES)
            finally:
                if previa and os.path.exists(previa):
                    os.remove(previa)
            with open(origem, "rb") as f:  # arquivo do jogo intocado
                self.assertEqual(f.read(), WAV_BYTES)

    def test_previa_ogg_e_mp3(self):
        with tempfile.TemporaryDirectory() as td:
            p_ogg = audio.preparar_previa_audio(criar(td, "a.bin", OGG_BYTES))
            p_mp3 = audio.preparar_previa_audio(criar(td, "b.bin", MP3_ID3))
            try:
                self.assertTrue(p_ogg.endswith(".ogg"))
                self.assertTrue(p_mp3.endswith(".mp3"))
            finally:
                for p in (p_ogg, p_mp3):
                    if p and os.path.exists(p):
                        os.remove(p)

    def test_previa_unknown_recusada(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertIsNone(audio.preparar_previa_audio(criar(td, "a.bin", UNKNOWN_BYTES)))


# ============================================================
# 3) SUBSTITUIÇÃO — COMPATIBILIDADE, BACKUP, ESCRITA
# ============================================================
class SubstituicaoBase(unittest.TestCase):
    def setUp(self):
        self._td_atual = None

        def backup_cliente(pasta_jogo, criar=True):
            """Namespace de backup POR CLIENTE, confinado ao td do teste atual."""
            if not self._td_atual:
                raise AssertionError("teste precisa definir _td_atual antes de usar backups")
            p = os.path.join(self._td_atual, "_backups", os.path.basename(pasta_jogo))
            if criar:
                os.makedirs(p, exist_ok=True)
            return p

        def caminho_seguro(base, caminho):
            base = os.path.normcase(os.path.abspath(base))
            alvo = os.path.normcase(os.path.abspath(caminho))
            return alvo == base or alvo.startswith(base + os.sep)

        def backup_rapido(origem, destino):
            try:
                os.makedirs(os.path.dirname(destino), exist_ok=True)
                if os.path.exists(destino):  # backup original jamais sobrescrito
                    return False
                with open(origem, "rb") as fo, open(destino, "wb") as fd:
                    fd.write(fo.read())
                return True
            except Exception:
                return False

        self._patches = [
            patch.object(audio, "normalizar_pasta_jogo", lambda p=None: os.path.abspath(p or ".")),
            patch.object(audio, "caminho_seguro", caminho_seguro),
            patch.object(audio, "obter_pasta_backup_cliente", backup_cliente),
            patch.object(audio, "fazer_backup_rapido", backup_rapido),
        ]
        for p in self._patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in self._patches])

    def _cenario(self, td, nome_original, bytes_original, bytes_novo):
        self._td_atual = td
        cliente = os.path.join(td, "ClienteA")
        pasta_sound = os.path.join(cliente, "Sound")
        os.makedirs(pasta_sound, exist_ok=True)
        alvo = criar(pasta_sound, nome_original, bytes_original)
        novo = criar(td, "novo", bytes_novo)
        return cliente, alvo, novo

    def _backup_path(self, td, cliente, alvo):
        return os.path.join(td, "_backups", os.path.basename(cliente),
                            "Sound", os.path.basename(alvo))


class TestSubstituicaoCompativel(SubstituicaoBase):
    def _substitui_e_verifica(self, td, bytes_original, bytes_novo, nome="sfx.bin"):
        cliente, alvo, novo = self._cenario(td, nome, bytes_original, bytes_novo)
        ok, msg = audio.substituir_audio_customizado(novo, alvo, cliente)
        self.assertTrue(ok, msg)
        with open(alvo, "rb") as f:  # destino com os NOVOS bytes (mesmo nome .bin)
            self.assertEqual(f.read(), bytes_novo)
        with open(self._backup_path(td, cliente, alvo), "rb") as f:  # backup = ORIGINAL
            self.assertEqual(f.read(), bytes_original)
        return alvo

    def test_wav_para_wav(self):
        with tempfile.TemporaryDirectory() as td:
            self._substitui_e_verifica(td, WAV_BYTES, WAV_BYTES + b"novo-wav")

    def test_ogg_para_ogg(self):
        with tempfile.TemporaryDirectory() as td:
            self._substitui_e_verifica(td, OGG_BYTES, OGG_BYTES + b"novo-ogg")

    def test_mp3_para_mp3(self):
        with tempfile.TemporaryDirectory() as td:
            self._substitui_e_verifica(td, MP3_ID3, MP3_RAW)

    def test_m4a_para_m4a(self):
        with tempfile.TemporaryDirectory() as td:
            self._substitui_e_verifica(td, M4A_BYTES, M4A_BYTES + b"novo-m4a")

    def test_restaurar_devolve_original(self):
        with tempfile.TemporaryDirectory() as td:
            alvo = self._substitui_e_verifica(td, WAV_BYTES, WAV_BYTES + b"mod")
            cliente = os.path.dirname(os.path.dirname(alvo))
            ok, _ = audio.restaurar_audio_original(alvo, cliente)
            self.assertTrue(ok)
            with open(alvo, "rb") as f:
                self.assertEqual(f.read(), WAV_BYTES)


class TestSubstituicaoIncompativel(SubstituicaoBase):
    def _recusa(self, bytes_original, bytes_novo, desc_alvo, desc_novo):
        with tempfile.TemporaryDirectory() as td:
            cliente, alvo, novo = self._cenario(td, "sfx.bin", bytes_original, bytes_novo)
            ok, msg = audio.substituir_audio_customizado(novo, alvo, cliente)
            self.assertFalse(ok)
            if desc_alvo:
                self.assertIn(desc_alvo, msg)
                self.assertIn(desc_novo, msg)
                self.assertIn("Converta", msg)
            with open(alvo, "rb") as f:  # original intocado
                self.assertEqual(f.read(), bytes_original)
            self.assertFalse(os.path.exists(self._backup_path(td, cliente, alvo)))

    def test_wav_para_mp3_recusado(self):
        self._recusa(WAV_BYTES, MP3_ID3, "WAV/PCM", "MP3")

    def test_mp3_para_wav_recusado(self):
        self._recusa(MP3_ID3, WAV_BYTES, "MP3", "WAV/PCM")

    def test_ogg_para_m4a_recusado(self):
        self._recusa(OGG_BYTES, M4A_BYTES, "OGG", "M4A/MP4")

    def test_novo_desconhecido_recusado(self):
        self._recusa(WAV_BYTES, UNKNOWN_BYTES, None, None)

    def test_original_desconhecido_bloqueado(self):
        self._recusa(UNKNOWN_BYTES, WAV_BYTES, None, None)


class TestFalhas(SubstituicaoBase):
    def test_falha_backup_impede_escrita(self):
        with tempfile.TemporaryDirectory() as td:
            cliente, alvo, novo = self._cenario(td, "sfx.bin", WAV_BYTES, WAV_BYTES + b"x")
            with patch.object(audio, "fazer_backup_rapido", return_value=False):
                ok, msg = audio.substituir_audio_customizado(novo, alvo, cliente)
            self.assertFalse(ok)
            self.assertIn("backup", msg.lower())
            with open(alvo, "rb") as f:  # original preservado
                self.assertEqual(f.read(), WAV_BYTES)

    def test_falha_escrita_mantem_original(self):
        with tempfile.TemporaryDirectory() as td:
            cliente, alvo, novo = self._cenario(td, "sfx.bin", WAV_BYTES, WAV_BYTES + b"x")
            with patch.object(audio, "_replace_atomico", side_effect=OSError("disco cheio")):
                ok, msg = audio.substituir_audio_customizado(novo, alvo, cliente)
            self.assertFalse(ok)
            self.assertIn("disco cheio", msg)
            with open(alvo, "rb") as f:  # original preservado após falha
                self.assertEqual(f.read(), WAV_BYTES)

    def test_fora_do_cliente_recusado(self):
        with tempfile.TemporaryDirectory() as td:
            self._td_atual = td
            cliente = os.path.join(td, "ClienteA")
            os.makedirs(cliente, exist_ok=True)
            alvo = criar(td, "fora.bin", WAV_BYTES)  # FORA do cliente
            novo = criar(td, "novo", WAV_BYTES)
            ok, msg = audio.substituir_audio_customizado(novo, alvo, cliente)
            self.assertFalse(ok)
            self.assertIn("fora do cliente", msg)

    def test_restore_sem_backup_falha_honesto(self):
        with tempfile.TemporaryDirectory() as td:
            cliente, alvo, _ = self._cenario(td, "sfx.bin", WAV_BYTES, WAV_BYTES)
            ok, msg = audio.restaurar_audio_original(alvo, cliente)
            self.assertFalse(ok)
            self.assertIn("backup", msg.lower())


class TestRestoreClienteCorreto(SubstituicaoBase):
    def test_restore_do_cliente_errado_nao_usa_backup_alheio(self):
        """Backup existe só no namespace do ClienteA; restore apontando ClienteB falha."""
        with tempfile.TemporaryDirectory() as td:
            self._td_atual = td
            raiz_a = os.path.join(td, "ClienteA")
            raiz_b = os.path.join(td, "ClienteB")
            som_a = os.path.join(raiz_a, "Sound")
            som_b = os.path.join(raiz_b, "Sound")
            os.makedirs(som_a, exist_ok=True)
            os.makedirs(som_b, exist_ok=True)
            alvo_a = criar(som_a, "sfx.bin", WAV_BYTES)
            novo = criar(td, "novo", WAV_BYTES + b"x")
            ok, _ = audio.substituir_audio_customizado(novo, alvo_a, raiz_a)
            self.assertTrue(ok)
            # restore apontando para o ClienteB (mesmo nome de arquivo) → sem backup nele
            alvo_b = criar(som_b, "sfx.bin", WAV_BYTES)
            ok, msg = audio.restaurar_audio_original(alvo_b, raiz_b)
            self.assertFalse(ok)
            self.assertIn("backup", msg.lower())
            with open(alvo_b, "rb") as f:  # ClienteB intocado
                self.assertEqual(f.read(), WAV_BYTES)
            # e o restore do ClienteA continua funcionando
            ok, _ = audio.restaurar_audio_original(alvo_a, raiz_a)
            self.assertTrue(ok)


# ============================================================
# 4) HANDLERS DE UI — MENSAGENS HONESTAS / THREADING
# ============================================================
class FakeSignal:
    def __init__(self):
        self.recebidos = []

    def emit(self, *args):
        self.recebidos.append(args)


class FakeSinais:
    def __init__(self):
        self.log_signal = FakeSignal()

    def textos(self):
        return [r[0] for r in self.log_signal.recebidos if r and isinstance(r[0], str)]


def janela_audio():
    import main
    win = main.AikaOptimizerPro.__new__(main.AikaOptimizerPro)
    win.sinais = FakeSinais()
    win._tarefas = []
    win.executar_em_background = lambda f, *a, **k: (win._tarefas.append(f), True)[1]
    return win


class TestHandlersUI(unittest.TestCase):
    def test_preview_original_unknown_gera_erro(self):
        win = janela_audio()
        win.player = MagicMock()
        win.arquivo_alvo_jogo = "qualquer.bin"
        with patch("main.opt") as opt_falso:
            opt_falso.preparar_previa_audio.return_value = None
            win.tocar_audio_jogo()
            self.assertTrue(any("não reconhecido" in t for t in win.sinais.textos()))
            opt_falso.preparar_previa_audio.assert_called_once_with("qualquer.bin")

    def test_falha_injecao_gera_erro_nunca_ok(self):
        win = janela_audio()
        win.arquivo_alvo_jogo = "alvo.bin"
        win.arquivo_audio_selecionado = "novo.mp3"
        with patch("main.opt") as opt_falso:
            opt_falso.obter_pasta_jogo_atual.return_value = "C:\\fake_cliente"
            opt_falso.substituir_audio_customizado.return_value = (False, "Converta o arquivo para WAV/PCM")
            win.acao_substituir_audio()
            for t in win._tarefas:
                t()
            textos = win.sinais.textos()
            self.assertTrue(any("[ERRO]" in t and "Converta" in t for t in textos))
            self.assertFalse(any("[OK]" in t for t in textos))

    def test_sucesso_injecao_gera_ok(self):
        win = janela_audio()
        win.arquivo_alvo_jogo = "alvo.bin"
        win.arquivo_audio_selecionado = "novo.wav"
        with patch("main.opt") as opt_falso:
            opt_falso.obter_pasta_jogo_atual.return_value = "C:\\fake_cliente"
            opt_falso.substituir_audio_customizado.return_value = (True, "Áudio substituído")
            win.acao_substituir_audio()
            for t in win._tarefas:
                t()
            self.assertTrue(any("[OK]" in t for t in win.sinais.textos()))

    def test_falha_restore_gera_erro(self):
        win = janela_audio()
        win.arquivo_alvo_jogo = "alvo.bin"
        with patch("main.opt") as opt_falso:
            opt_falso.obter_pasta_jogo_atual.return_value = "C:\\fake_cliente"
            opt_falso.restaurar_audio_original.return_value = (False, "Sem backup válido para este cliente.")
            win.acao_restaurar_audio()
            for t in win._tarefas:
                t()
            self.assertTrue(any("[ERRO]" in t and "backup" in t.lower() for t in win.sinais.textos()))

    def test_injecao_roda_via_background(self):
        """Operação de arquivo/hashing NÃO roda na GUI thread."""
        win = janela_audio()
        win.arquivo_alvo_jogo = "alvo.bin"
        win.arquivo_audio_selecionado = "novo.wav"
        with patch("main.opt"):
            win.acao_substituir_audio()
        self.assertEqual(len(win._tarefas), 1)  # tarefa delegada ao worker


if __name__ == "__main__":
    unittest.main(verbosity=2)
