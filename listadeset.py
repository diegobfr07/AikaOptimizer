import os
import shutil
import struct
import sys
import threading
import time
from tkinter import filedialog, messagebox

import customtkinter as ctk


# Função vital para o Executável (.exe) encontrar o ícone do leão
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# =====================================================================
# 1. MOTOR DE TEXTURAS (JIT -> DDS/TGA)
# =====================================================================
DDSD_CAPS = 0x1; DDSD_HEIGHT = 0x2; DDSD_WIDTH = 0x4; DDSD_PITCH = 0x8
DDSD_PIXELFORMAT = 0x1000; DDSD_MIPMAPCOUNT = 0x20000; DDSD_LINEARSIZE = 0x80000
DDSCAPS_COMPLEX = 0x8; DDSCAPS_TEXTURE = 0x1000; DDSCAPS_MIPMAP = 0x400000
DDPF_FOURCC = 0x4

def build_dds_header(width, height, fourcc, mipmaps, linear_size):
    header = bytearray(128)
    header[0:4] = b"DDS "
    struct.pack_into("<I", header, 4, 124)
    flags = DDSD_CAPS | DDSD_HEIGHT | DDSD_WIDTH | DDSD_PIXELFORMAT | DDSD_LINEARSIZE
    if mipmaps > 1: flags |= DDSD_MIPMAPCOUNT
    struct.pack_into("<I", header, 8, flags)
    struct.pack_into("<I", header, 12, height)
    struct.pack_into("<I", header, 16, width)
    struct.pack_into("<I", header, 20, linear_size)
    struct.pack_into("<I", header, 24, 0)
    struct.pack_into("<I", header, 28, mipmaps)
    struct.pack_into("<I", header, 76, 32)
    struct.pack_into("<I", header, 80, DDPF_FOURCC)
    header[84:88] = fourcc
    caps = DDSCAPS_TEXTURE
    if mipmaps > 1:
        caps |= DDSCAPS_COMPLEX
        caps |= DDSCAPS_MIPMAP
    struct.pack_into("<I", header, 108, caps)
    return bytes(header)

def extrair_textura_jit(caminho_jit):
    try:
        if not os.path.exists(caminho_jit) or os.path.getsize(caminho_jit) < 24: return False, "Arquivo inválido."
        with open(caminho_jit, "rb") as f: data = f.read()

        base = os.path.splitext(caminho_jit)[0]
        achados = []
        for magic in [b'DDS ', b'JT31', b'JT33', b'JT35', b'JT20']:
            off = data.find(magic)
            if off != -1:
                if magic == b'DDS ':
                    achados.append((off, "DDS"))
                else:
                    if off + 12 <= len(data):
                        w = struct.unpack("<I", data[off+4:off+8])[0]
                        h = struct.unpack("<I", data[off+8:off+12])[0]
                        if 8 <= w <= 8192 and 8 <= h <= 8192: 
                            achados.append((off, magic.decode()))
        
        if achados:
            achados.sort(key=lambda x: x[0])
            offset, tipo = achados[0]
            
            if tipo in ["JT31", "JT33", "JT35"]:
                width = struct.unpack("<I", data[offset+4:offset+8])[0]
                height = struct.unpack("<I", data[offset+8:offset+12])[0]
                fourcc_map = {"JT31": (b"DXT1", 8), "JT33": (b"DXT3", 16), "JT35": (b"DXT5", 16)}
                fourcc, block_size = fourcc_map[tipo]
                blocks_x = max(1, (width + 3) // 4)
                blocks_y = max(1, (height + 3) // 4)
                base_size = blocks_x * blocks_y * block_size
                payload = data[offset + 12 : offset + 12 + base_size]
                dds_hdr = build_dds_header(width, height, fourcc, 1, base_size)
                out = base + ".dds"
                with open(out, "wb") as f:
                    f.write(dds_hdr)
                    f.write(payload)
                return True, ""

            elif tipo == "JT20":
                width = struct.unpack("<I", data[offset+4:offset+8])[0]
                height = struct.unpack("<I", data[offset+8:offset+12])[0]
                size_pixels = width * height
                palette = data[offset+12 : offset+12 + 1024]
                pixels = data[offset+12 + 1024 : offset+12 + 1024 + size_pixels]
                rgba = bytearray()
                for idx in pixels:
                    if idx * 4 + 3 < len(palette):
                        b, g, r, a = palette[idx*4], palette[idx*4+1], palette[idx*4+2], palette[idx*4+3]
                    else:
                        b, g, r, a = 0, 0, 0, 0
                    rgba.extend([b, g, r, a])
                tga = bytearray(18)
                tga[2] = 2
                struct.pack_into("<H", tga, 12, width)
                struct.pack_into("<H", tga, 14, height)
                tga[16], tga[17] = 32, 0x28
                out = base + ".tga"
                with open(out, "wb") as f: f.write(tga); f.write(rgba)
                return True, ""

            elif tipo == "DDS":
                out = base + ".dds"
                payload = data[offset:]
                with open(out, "wb") as f: f.write(payload)
                return True, ""

        offset_tga = -1
        for off in range(min(8192, len(data) - 18)):
            img_type = data[off + 2]
            if img_type in [1, 2, 3, 9, 10, 11]:
                bpp = data[off + 16]
                if bpp in [8, 15, 16, 24, 32]:
                    w = struct.unpack('<H', data[off+12:off+14])[0]
                    h = struct.unpack('<H', data[off+14:off+16])[0]
                    if 8 <= w <= 4096 and 8 <= h <= 4096:
                        offset_tga = off
                        break
        if offset_tga != -1:
            payload = data[offset_tga:]
            out = base + ".tga"
            with open(out, "wb") as f: f.write(payload)
            return True, ""

        return False, "Formato não suportado."
    except Exception as e: return False, str(e)


# =====================================================================
# 2. MOTOR DE GEOMETRIA (MSH -> OBJ)
# =====================================================================
def convert_msh_to_obj(input_file):
    try:
        output_file = os.path.splitext(input_file)[0] + ".obj"
        with open(input_file, 'rb') as f:
            header_data = f.read(36)
            if len(header_data) < 36: raise ValueError("Arquivo inválido.")
            unk01, unk02, unk03, count01, vert_size, unk06, bone_count, vert_count, face_count = struct.unpack('<9I', header_data)
            
            f.seek((0x40 * bone_count) + (4 * bone_count), 1)
            vertices = []; uvs = []
            
            for _ in range(vert_count):
                vx, vy, vz = struct.unpack('<3f', f.read(12))
                vertices.append((vx, vy, vz))
                if vert_size == 0x24: f.seek(16, 1) 
                elif vert_size == 0x28: f.seek(20, 1) 
                elif vert_size == 0x2C: f.seek(24, 1) 
                else: f.seek(vert_size - 20, 1)
                
                tu, tv = struct.unpack('<2f', f.read(8))
                uvs.append((tu, -tv)) 
                
            faces = []
            for _ in range(face_count // 3):
                f1, f2, f3 = struct.unpack('<3H', f.read(6))
                faces.append((f1 + 1, f2 + 1, f3 + 1))
                
        with open(output_file, 'w') as obj:
            obj.write("# Conversor MSH para OBJ\n")
            obj.writelines(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n" for v in vertices)
            obj.writelines(f"vt {uv[0]:.6f} {uv[1]:.6f}\n" for uv in uvs)
            obj.writelines(f"f {face[0]}/{face[0]} {face[1]}/{face[1]} {face[2]}/{face[2]}\n" for face in faces)
                
        return True, ""
    except Exception as e:
        return False, str(e)


# =====================================================================
# 3. INTERFACE GRÁFICA E THREADING (COM CORES DINÂMICAS)
# =====================================================================
ctk.set_appearance_mode("Dark")
ROXO_PRIMARIO = "#6200EA"
ROXO_HOVER = "#7C4DFF"
CINZA_FUNDO = "#1E1E2E"
COR_BOTAO_ATIVO = "#D32F2F"

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Aika Studio Pro - Organização & Conversão")
        self.geometry("700x550") 
        self.resizable(False, False)
        self.configure(fg_color=CINZA_FUNDO)

        # Aplicando a função resource_path para garantir o funcionamento no .exe
        try:
            self.iconbitmap(resource_path("leao.ico"))
        except:
            pass 

        # --- TÍTULO ---
        self.lbl_titulo = ctk.CTkLabel(self, text="Extremamente Brutal!!!", font=("Arial", 24, "bold"), text_color=ROXO_HOVER)
        self.lbl_titulo.pack(pady=20)

        # --- SEÇÃO ORIGEM ---
        self.lbl_origem = ctk.CTkLabel(self, text="1. Pasta Origem (Arquivos do Jogo):")
        self.lbl_origem.pack(anchor="w", padx=40)
        
        self.frame_origem = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_origem.pack(fill="x", padx=40, pady=(0, 15))
        self.entry_origem = ctk.CTkEntry(self.frame_origem, width=480, corner_radius=8)
        self.entry_origem.insert(0, r"C:\CBMgames\AikaOnlineBrasil") 
        self.entry_origem.pack(side="left", padx=(0, 10))
        self.btn_origem = ctk.CTkButton(self.frame_origem, text="Procurar", command=self.selecionar_origem, width=100, fg_color=ROXO_PRIMARIO, hover_color=ROXO_HOVER, corner_radius=8)
        self.btn_origem.pack(side="left")

        # --- SEÇÃO DESTINO ---
        self.lbl_destino = ctk.CTkLabel(self, text="2. Pasta Destino (Onde salvar os Sets extraídos):")
        self.lbl_destino.pack(anchor="w", padx=40)
        
        self.frame_destino = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_destino.pack(fill="x", padx=40, pady=(0, 15))
        self.entry_destino = ctk.CTkEntry(self.frame_destino, width=480, placeholder_text="Selecione onde salvar...", corner_radius=8)
        self.entry_destino.pack(side="left", padx=(0, 10))
        self.btn_destino = ctk.CTkButton(self.frame_destino, text="Procurar", command=self.selecionar_destino, width=100, fg_color=ROXO_PRIMARIO, hover_color=ROXO_HOVER, corner_radius=8)
        self.btn_destino.pack(side="left")

        # --- CAIXINHAS DE SELEÇÃO (O QUE EXTRAIR) ---
        self.frame_opcoes_extracao = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_opcoes_extracao.pack(fill="x", padx=40, pady=5)
        
        self.chk_3d = ctk.CTkCheckBox(self.frame_opcoes_extracao, text="Converter Modelos 3D (.msh para .obj)", fg_color=ROXO_PRIMARIO, hover_color=ROXO_HOVER)
        self.chk_3d.pack(side="left", padx=(0, 20))
        self.chk_3d.select() 

        self.chk_texturas = ctk.CTkCheckBox(self.frame_opcoes_extracao, text="Extrair Texturas (.jit para .dds / .tga)", fg_color=ROXO_PRIMARIO, hover_color=ROXO_HOVER)
        self.chk_texturas.pack(side="left")
        self.chk_texturas.select() 

        # --- SEÇÃO CONTROLES (Velocidade) ---
        self.frame_controles = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_controles.pack(fill="x", padx=40, pady=10)
        
        self.lbl_modo = ctk.CTkLabel(self.frame_controles, text="Modo de Desempenho:", font=("Arial", 13))
        self.lbl_modo.pack(side="left", padx=(0, 10))
        
        self.seletor_modo = ctk.CTkOptionMenu(self.frame_controles, values=["Brutal (Máxima Velocidade)", "Seguro (PC Fraco - Evita Travamentos)"], fg_color=ROXO_PRIMARIO, button_color=ROXO_HOVER, button_hover_color="#5000C0")
        self.seletor_modo.pack(side="left")

        # --- BARRA DE PROGRESSO ---
        self.lbl_progresso_texto = ctk.CTkLabel(self, text="Aguardando início...", font=("Arial", 12))
        self.lbl_progresso_texto.pack(pady=(10, 0))

        self.progressbar = ctk.CTkProgressBar(self, width=620, height=15, corner_radius=10, fg_color="#313143", progress_color="#555555")
        self.progressbar.set(0)
        self.progressbar.pack(pady=5)

        # --- BOTÃO EXECUTAR ---
        self.btn_executar = ctk.CTkButton(self, text="INICIAR EXTRAÇÃO TOTAL", height=45, font=("Arial", 16, "bold"), fg_color=ROXO_PRIMARIO, hover_color=ROXO_HOVER, corner_radius=12, command=self.iniciar_thread_processo)
        self.btn_executar.pack(pady=15)

    def selecionar_origem(self):
        pasta = filedialog.askdirectory()
        if pasta:
            self.entry_origem.delete(0, "end")
            self.entry_origem.insert(0, pasta)

    def selecionar_destino(self):
        pasta = filedialog.askdirectory()
        if pasta:
            self.entry_destino.delete(0, "end")
            self.entry_destino.insert(0, pasta)

    def calcular_cor_progresso(self, porcentagem):
        if porcentagem <= 0.5:
            p = porcentagem * 2
            r = 255
            g = int(50 + (150 * p)) 
            b = 50
        else:
            p = (porcentagem - 0.5) * 2
            r = int(255 - (255 * p)) 
            g = 200
            b = 50
        return f"#{r:02x}{g:02x}{b:02x}"

    def iniciar_thread_processo(self):
        origem = self.entry_origem.get()
        destino = self.entry_destino.get()

        if not origem or not os.path.exists(origem):
            messagebox.showerror("Erro", "Por favor, selecione uma pasta de origem válida.")
            return
        if not destino:
            messagebox.showerror("Erro", "Por favor, selecione uma pasta de destino.")
            return

        self.btn_executar.configure(text="⏳ PROCESSANDO... (Isso pode demorar)", fg_color=COR_BOTAO_ATIVO, state="disabled")
        
        self.btn_origem.configure(state="disabled")
        self.btn_destino.configure(state="disabled")
        self.chk_3d.configure(state="disabled")
        self.chk_texturas.configure(state="disabled")
        self.seletor_modo.configure(state="disabled")
        
        modo_seguro = "Seguro" in self.seletor_modo.get()
        extrair_3d = self.chk_3d.get() == 1
        extrair_tex = self.chk_texturas.get() == 1

        thread = threading.Thread(target=self.organizar_e_converter_aika, args=(origem, destino, modo_seguro, extrair_3d, extrair_tex))
        thread.start()

    def organizar_e_converter_aika(self, diretorio_origem, diretorio_destino, modo_seguro, extrair_3d, extrair_tex):
        try:
            if not os.path.exists(diretorio_destino): os.makedirs(diretorio_destino)

            mapa_armaduras = {"01": "Guerreiro", "02": "Templaria", "03": "Atirador", "04": "Dual", "05": "FC", "06": "Cleriga"}
            mapa_armas = {"FM": "Guerreiro", "FF": "Templaria", "SM": "Atirador", "SF": "Dual", "MM": "FC", "MF": "Cleriga"}
            pecas_do_set = ["03", "04", "05", "06", "07", "08"]

            stats = {"copiados": 0, "msh_convertidos": 0, "jit_extraidos": 0}

            self.atualizar_interface_segura(0, "Mapeando arquivos... aguarde.", 0)
            lista_arquivos = []
            for raiz, diretorios, arquivos in os.walk(diretorio_origem):
                for arquivo in arquivos:
                    lista_arquivos.append((raiz, arquivo))
            
            total_arquivos = len(lista_arquivos)
            if total_arquivos == 0:
                self.finalizar_processo_seguro(stats, "Nenhum arquivo encontrado na pasta de origem!")
                return

            for index, (raiz, arquivo) in enumerate(lista_arquivos):
                nome_base, extensao = os.path.splitext(arquivo)
                extensao = extensao.lower()
                caminho_pasta_item = None 

                if nome_base.upper().startswith('CH') and len(nome_base) >= 10:
                    classe_id = nome_base[2:4]
                    parte_id = nome_base[4:6]
                    set_id = nome_base[6:10]
                    if classe_id in mapa_armaduras and parte_id in pecas_do_set:
                        caminho_pasta_item = os.path.join(diretorio_destino, mapa_armaduras[classe_id], f"Set_Armadura_{set_id}")

                prefixo_arma = nome_base[:2].upper()
                if prefixo_arma in mapa_armas and len(nome_base) >= 10:
                    tipo_arma = nome_base[2:5] 
                    id_arma = nome_base[5:10]  
                    caminho_pasta_item = os.path.join(diretorio_destino, mapa_armas[prefixo_arma], "Armas", f"{tipo_arma}_{id_arma}")

                if caminho_pasta_item:
                    subpasta = ""
                    if extensao in ['.msh', '.obj']: subpasta = "Mesh"
                    elif extensao == '.jit': subpasta = "Texture"
                    elif extensao == '.ms3': subpasta = "Objects"
                    
                    if subpasta:
                        caminho_final = os.path.join(caminho_pasta_item, subpasta)
                        if not os.path.exists(caminho_final): os.makedirs(caminho_final)
                            
                        origem = os.path.join(raiz, arquivo)
                        destino = os.path.join(caminho_final, arquivo)
                        
                        if not os.path.exists(destino):
                            shutil.copy2(origem, destino)
                            stats["copiados"] += 1

                        if extensao == '.msh' and extrair_3d:
                            caminho_obj = os.path.splitext(destino)[0] + ".obj"
                            if not os.path.exists(caminho_obj): 
                                sucesso, msg = convert_msh_to_obj(destino)
                                if sucesso: stats["msh_convertidos"] += 1
                        
                        elif extensao == '.jit' and extrair_tex:
                            caminho_dds = os.path.splitext(destino)[0] + ".dds"
                            caminho_tga = os.path.splitext(destino)[0] + ".tga"
                            if not os.path.exists(caminho_dds) and not os.path.exists(caminho_tga):
                                sucesso, msg = extrair_textura_jit(destino)
                                if sucesso: stats["jit_extraidos"] += 1

                porcentagem = (index + 1) / total_arquivos
                texto_status = f"Processando: {index + 1} de {total_arquivos} arquivos ( {int(porcentagem * 100)}% )"
                self.atualizar_interface_segura(porcentagem, texto_status)

                if modo_seguro:
                    time.sleep(0.01) 

            self.finalizar_processo_seguro(stats)

        except Exception as e:
            self.finalizar_processo_seguro(stats, erro=str(e))

    def atualizar_interface_segura(self, porcentagem, texto, tempo_espera=0):
        cor_atual = self.calcular_cor_progresso(porcentagem)
        
        self.after(tempo_espera, lambda: self.progressbar.set(porcentagem))
        self.after(tempo_espera, lambda: self.progressbar.configure(progress_color=cor_atual))
        self.after(tempo_espera, lambda: self.lbl_progresso_texto.configure(text=texto))

    def finalizar_processo_seguro(self, stats, erro=None):
        def acao_final():
            self.btn_executar.configure(text="INICIAR EXTRAÇÃO TOTAL", state="normal", fg_color=ROXO_PRIMARIO)
            
            self.btn_origem.configure(state="normal")
            self.btn_destino.configure(state="normal")
            self.chk_3d.configure(state="normal")
            self.chk_texturas.configure(state="normal")
            self.seletor_modo.configure(state="normal")

            if erro:
                messagebox.showerror("Erro Crítico", f"Ocorreu um erro: {erro}")
            else:
                self.progressbar.set(1.0)
                self.progressbar.configure(progress_color="#4CAF50") 
                self.lbl_progresso_texto.configure(text="CONCLUÍDO 100%")
                relatorio = (
                    f"Processo Brutal Concluído!\n\n"
                    f"📁 Novos Arquivos Organizados: {stats.get('copiados', 0)}\n"
                    f"🧊 Novos Modelos 3D Gerados (.obj): {stats.get('msh_convertidos', 0)}\n"
                    f"🎨 Novas Texturas Extraídas (.dds/.tga): {stats.get('jit_extraidos', 0)}"
                )
                messagebox.showinfo("Sucesso Brutal", relatorio)

        self.after(0, acao_final)

if __name__ == "__main__":
    app = App()
    app.mainloop()