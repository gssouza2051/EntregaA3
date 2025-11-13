"""
Instalação e execução (Windows)
-------------------------------
1. Abrir terminal na pasta do projeto:
   cd "EntregaA3"

2. Criar e ativar venv:
   - python -m venv .venv
   - PowerShell: .\.venv\Scripts\Activate.ps1
   - CMD: .venv\Scripts\activate

3. Instalar dependências:
    pip install -r requirements.txt
   Ou manualmente:
   python -m pip install --upgrade pip setuptools wheel
   python -m pip install pygame scikit-fuzzy numpy

4. Rodar:
   python main.py
"""

import os
# oculta a mensagem de boas-vindas do pygame
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

import warnings
warnings.filterwarnings("ignore", message=r".*pkg_resources is deprecated.*", category=UserWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

import pygame
import random
import sys
import numpy as np
import skfuzzy as fuzz
from skfuzzy import control as ctrl
import csv
from pathlib import Path
import time
import textwrap
import datetime
#from reset_planilha import verificar_e_resetar_planilha

# Chamar função para resetar planilha se desejado
#verificar_e_resetar_planilha()

# métricas (arquivo)
ARQUIVOS_METRICAS = Path("metricas.csv")
carros_saíram = 0
total_gerado = 0

# --- INICIALIZAÇÃO DO PYGAME ---
pygame.init()

# --- CONSTANTES ---
LARGURA_TELA = 800
ALTURA_TELA = 800
tela = pygame.display.set_mode((LARGURA_TELA, ALTURA_TELA))
pygame.display.set_caption("Simulador de Semáforo com Lógica Fuzzy")

# Cores e Fonte
COR_BRANCA = (255, 255, 255)
COR_PRETA = (0, 0, 0)
COR_CINZA = (100, 100, 100)
COR_VERDE = (0, 200, 0)
COR_AMARELA = (255, 255, 0)
COR_VERMELHA = (200, 0, 0)
COR_CINZA_ESCURO = (50, 50, 50)
fonte = pygame.font.SysFont("Arial", 20)

# Controle de tempo
tempo = pygame.time.Clock()
FPS = 60

# Zonas de parada (ajustadas e separadas por direção)
PARADA_EMBAIXO_MIN, PARADA_EMBAIXO_MAX = 340, 340   # vindo de cima 
PARADA_CIMA_MIN, PARADA_CIMA_MAX = 440, 440   # vindo de baixo 
PARADA_DIREITA_MIN, PARADA_DIREITA_MAX = 340, 340   # vindo da esquerda 
PARADA_ESQUERDA_MIN, PARADA_ESQUERDA_MAX = 440, 440   # vindo da direita 4
# extensão da área considerada "fila" atrás da linha de parada (em pixels)
COMPRIMENTO_FILA = 160

# Constantes das faixas (reutilizadas pelo spawn dos pedestres)
CW_THICKNESS = 22
CW_GAP = 12

# limites das vias (usados por desenho e lógica para detectar faixas)
ESTRADA_X0, ESTRADA_X1 = 350, 450
ESTRADA_Y0, ESTRADA_Y1 = 350, 450

# flags globais para bloquear tráfego quando pedestres estão atravessando
BLOQUEIO_PEDESTRES_VERT = 0  # pedestres atravessando a via vertical (impactam tráfego vertical)
BLOQUEIO_PEDESTRES_HORI = 0  # pedestres atravessando a via horizontal (impactam tráfego horizontal)

# --- Variáveis ambientais randômicas (clima / fluxo / horário) ---
CLIMAS = ["Ensolarado", "Chuvoso", "Nublado"]
NIVEIS_DE_FLUXO = ["Baixo", "Médio", "Alto"]

# mapeamento de níveis para multiplicadores de spawn (valores base serão multiplicados)
FLUXO_CARROS_MULTIPLOS = {"Baixo": 0.25, "Médio": 0.6, "Alto": 1.3}
FLUXO_PEDESTRES_MULTIPLOS = {"Baixo": 0.25, "Médio": 0.6, "Alto": 1.3}


def gerar_ambiente_aleatorio():
    """Gera um dicionário com clima, fluxo de carros, fluxo de pedestres e horário aleatório.
    Se a hora cair em período de pico (06:30-08:00 ou 18:00-19:00) força fluxo_de_carros = 'Alto'.
    """
    clima = random.choice(CLIMAS)

    # horário aleatório do dia
    seconds = random.randint(0, 24*3600 - 1)
    hora_dt = (datetime.datetime.min + datetime.timedelta(seconds=seconds)).time()
    hora = hora_dt.strftime("%H:%M:%S")

    # escolha inicial com pesos para ter mais probabilidade de Médio
    fluxo_carros = random.choices(NIVEIS_DE_FLUXO, weights=[1, 3, 2], k=1)[0]
    fluxo_de_pedestres = random.choices(NIVEIS_DE_FLUXO, weights=[2, 3, 1], k=1)[0]

    # se estiver em horário de pico, força fluxo de carros Alto
    pico_manha_comeco = datetime.time(6, 30, 0)
    pico_manha_fim   = datetime.time(8, 0, 0)
    pico_manha_comeco = datetime.time(18, 0, 0)
    pico_manha_fim   = datetime.time(19, 0, 0)
    if (pico_manha_comeco <= hora_dt <= pico_manha_fim) or (pico_manha_comeco <= hora_dt <= pico_manha_fim):
        fluxo_carros = "Alto"

    return {"clima": clima, "fluxo_de_carros": fluxo_carros, "fluxo_de_pedestres": fluxo_de_pedestres, "hora": hora}

# --- Controlador Fuzzy ---

class FuzzyControlador:
    """
    FuzzyControlador estendido com variáveis linguísticas:
     - fluxo de carros (Baixo/Médio/Alto)
     - fluxo de pedestres (Baixo/Médio/Alto)
     - horário (Outro/Normal/Pico)  -- mapeado a partir de hora HH:MM:SS
     - clima (Ensolarado/Nublado/Chuvoso)
    Saída: tempo_recomendado (0..30s) para o semáforo.
    """
    def __init__(self):
        # entradas
        self.fluxo_de_carros = ctrl.Antecedent(np.arange(0, 11, 1), 'fluxo_de_carros')      # 0..10
        self.fluxo_de_pedestres = ctrl.Antecedent(np.arange(0, 11, 1), 'fluxo_de_pedestres')      # 0..10
        self.horario = ctrl.Antecedent(np.arange(0, 3, 1), 'horario')        # 0:Outro,1:Normal,2:Pico
        self.clima = ctrl.Antecedent(np.arange(0, 3, 1), 'clima')            # 0:Ensolarado,1:Nublado,2:Chuvoso

        # saída
        self.tempo_semaforo = ctrl.Consequent(np.arange(0, 31, 1), 'tempo_semaforo')  # 0..30 segundos

        # memberships - fluxo carros / pedestres (Baixo/Médio/Alto)
        self.fluxo_de_carros['Baixo']  = fuzz.trimf(self.fluxo_de_carros.universe, [0, 0, 4])
        self.fluxo_de_carros['Médio']  = fuzz.trimf(self.fluxo_de_carros.universe, [2, 5, 8])
        self.fluxo_de_carros['Alto']   = fuzz.trimf(self.fluxo_de_carros.universe, [6, 10, 10])

        self.fluxo_de_pedestres['Baixo']  = fuzz.trimf(self.fluxo_de_pedestres.universe, [0, 0, 4])
        self.fluxo_de_pedestres['Médio']  = fuzz.trimf(self.fluxo_de_pedestres.universe, [2, 5, 8])
        self.fluxo_de_pedestres['Alto']   = fuzz.trimf(self.fluxo_de_pedestres.universe, [6, 10, 10])

        # horario categórico: 0 Outro, 1 Normal, 2 Pico
        self.horario['Outro'] = fuzz.trimf(self.horario.universe, [0, 0, 1])
        self.horario['Normal'] = fuzz.trimf(self.horario.universe, [0, 1, 2])
        self.horario['Pico'] = fuzz.trimf(self.horario.universe, [1, 2, 2])

        # clima: 0 Ensolarado, 1 Nublado, 2 Chuvoso
        self.clima['Ensolarado'] = fuzz.trimf(self.clima.universe, [0, 0, 1])
        self.clima['Nublado']    = fuzz.trimf(self.clima.universe, [0, 1, 2])
        self.clima['Chuvoso']    = fuzz.trimf(self.clima.universe, [1, 2, 2])

        # saída tempo do semáforo (Baixo / Médio / Alto)
        self.tempo_semaforo['Baixo'] = fuzz.trimf(self.tempo_semaforo.universe, [0, 0, 8])
        self.tempo_semaforo['Médio'] = fuzz.trimf(self.tempo_semaforo.universe, [6, 15, 22])
        self.tempo_semaforo['Alto']  = fuzz.trimf(self.tempo_semaforo.universe, [18, 30, 30])

        # --- Regras solicitadas (implementadas aqui) ---
        regras = []

        # 1. SE (Fluxo de Carros é Alto) E (Horário é Pico) ENTÃO (Tempo é Alto).
        regras.append(ctrl.Rule(self.fluxo_de_carros['Alto'] & self.horario['Pico'], self.tempo_semaforo['Alto']))

        # 2. SE (Fluxo de Carros é Médio) E (Fluxo de Pedestres é Médio) E (Horário é Normal) ENTÃO (Tempo é Médio).
        regras.append(ctrl.Rule(self.fluxo_de_carros['Médio'] & self.fluxo_de_pedestres['Médio'] & self.horario['Normal'], self.tempo_semaforo['Médio']))

        # 3. SE (Fluxo de Carros é Baixo) OU (Fluxo de Pedestres é Baixo) ENTÃO (Tempo é Baixo).
        regras.append(ctrl.Rule(self.fluxo_de_carros['Baixo'] | self.fluxo_de_pedestres['Baixo'], self.tempo_semaforo['Baixo']))

        # 4. SE (Fluxo de Carros é Alto) E (Fluxo de Pedestres é Alto) E (Horário é Normal) ENTÃO (Tempo é Médio).
        regras.append(ctrl.Rule(self.fluxo_de_carros['Alto'] & self.fluxo_de_pedestres['Alto'] & self.horario['Normal'], self.tempo_semaforo['Médio']))

        # 5. SE (Fluxo de Carros é Alto) E (Fluxo de Pedestres é Alto) E (Horário é Pico) ENTÃO (Tempo é Alto).
        regras.append(ctrl.Rule(self.fluxo_de_carros['Alto'] & self.fluxo_de_pedestres['Alto'] & self.horario['Pico'], self.tempo_semaforo['Alto']))

        # 6. SE (Fluxo de Carros é Alto) E (Clima é Chuvoso) ENTÃO (Tempo é Alto).
        regras.append(ctrl.Rule(self.fluxo_de_carros['Alto'] & self.clima['Chuvoso'], self.tempo_semaforo['Alto']))

        # Regras adicionais conforme especificado:
        # - SE Fluxo de Carros é Baixo E Fluxo de Pedestres é Baixo E Horário Outro ENTÃO Tempo Baixo.
        regras.append(ctrl.Rule(self.fluxo_de_carros['Baixo'] & self.fluxo_de_pedestres['Baixo'] & self.horario['Outro'], self.tempo_semaforo['Baixo']))

        # - SE Fluxo de Carros é Baixo E Fluxo de Pedestres é Alto ENTÃO Tempo Médio.
        regras.append(ctrl.Rule(self.fluxo_de_carros['Baixo'] & self.fluxo_de_pedestres['Alto'], self.tempo_semaforo['Médio']))

        # - SE Fluxo de Carros é Médio E Horário é Outro ENTÃO Tempo Médio.
        regras.append(ctrl.Rule(self.fluxo_de_carros['Médio'] & self.horario['Outro'], self.tempo_semaforo['Médio']))

        # monta sistema
        self.sistema = ctrl.ControlSystem(regras)
        self.sim = ctrl.ControlSystemSimulation(self.sistema)

        # armazenar descrições das regras na mesma ordem (para impressão)
        self.descricoes_regra = [
            "1) SE (Fluxo de Carros é Alto) E (Horário é de Pico) ENTÃO (Tempo é Alto).",
            "2) SE (Fluxo de Carros é Médio) E (Fluxo de Pedestres é Médio) E (Horário é Normal) ENTÃO (Tempo é Médio).",
            "3) SE (Fluxo de Carros é Baixo) OU (Fluxo de Pedestres é Baixo) ENTÃO (Tempo é Baixo).",
            "4) SE (Fluxo de Carros é Alto) E (Fluxo de Pedestres é Alto) E (Horário é Normal) ENTÃO (Tempo é Médio).",
            "5) SE (Fluxo de Carros é Alto) E (Fluxo de Pedestres é Alto) E (Horário é de Pico) ENTÃO (Tempo é Alto).",
            "6) SE (Fluxo de Carros é Alto) E (Clima é Chuvoso) ENTÃO (Tempo é Alto).",
            "7) SE Fluxo de Carros é Baixo E Fluxo de Pedestres é Baixo E Horário Outro ENTÃO Tempo Baixo.",
            "8) SE Fluxo de Carros é Baixo E Fluxo de Pedestres é Alto ENTÃO Tempo Médio.",
            "9) SE Fluxo de Carros é Médio E Horário é Outro ENTÃO Tempo Médio."
        ]

    # mapeamentos auxiliares de rótulos para valores numéricos usados na entrada fuzzy
    @staticmethod
    def mapear_rotulo_de_fluxo_para_valor(label):
        return {'Baixo': 2.0, 'Médio': 5.0, 'Alto': 9.0}.get(label, 5.0)

    @staticmethod
    def mapear_rotulo_climatico_para_valor(label):
        return {'Ensolarado': 0.0, 'Nublado': 1.0, 'Chuvoso': 2.0}.get(label, 1.0)

    @staticmethod
    def mapear_rotulo_hora_para_valor(hora_str):
        # hora_str "HH:MM:SS"
        try:
            h = int(hora_str.split(":")[0])
        except Exception:
            return 1.0
        # pico: 07-09 e 17-19
        if 7 <= h <= 9 or 17 <= h <= 19:
            return 2.0  # Pico
        # normal: 10-16
        if 10 <= h <= 16:
            return 1.0  # Normal
        return 0.0      # Outro

    def calcular_tempo_a_partir_do_ambiente(self, rotulo_fluxo_carros, rotulo_fluxo_pedestres, hora_str, rotulo_clima):
        """
        Recebe labels do ambiente (strings) e retorna tempo_recomendado (float segundos).
        Implementação mais resiliente: usa uma simulação local e tenta recuperar a saída
        mesmo que a chave não exista exatamente como 'tempo_semaforo'.
        """
        cf = self.mapear_rotulo_de_fluxo_para_valor(rotulo_fluxo_carros)
        pf = self.mapear_rotulo_de_fluxo_para_valor(rotulo_fluxo_pedestres)
        hr = self.mapear_rotulo_hora_para_valor(hora_str)
        cl = self.mapear_rotulo_climatico_para_valor(rotulo_clima)

        try:
            # cria uma simulação local para evitar estado/resíduos entre chamadas
            sim_local = ctrl.ControlSystemSimulation(self.sistema)
            sim_local.input['fluxo_de_carros'] = float(cf)
            sim_local.input['fluxo_de_pedestres'] = float(pf)
            sim_local.input['horario'] = float(hr)
            sim_local.input['clima'] = float(cl)

            sim_local.compute()

            # tenta acessar pelo nome esperado; se não existir, pega o primeiro valor disponível
            if isinstance(sim_local.output, dict) and 'tempo_semaforo' in sim_local.output:
                tempo = float(sim_local.output['tempo_semaforo'])
            elif isinstance(sim_local.output, dict) and len(sim_local.output) > 0:
                tempo = float(next(iter(sim_local.output.values())))
            else:
                # fallback seguro
                tempo = 12.0
        except Exception as e:
            print("Erro calcular_tempo_a_partir_do_ambiente:", e)
            tempo = 12.0

        return tempo

    def prioridade_de_computacao(self, num_carros_vermelha, tempo_verde, num_pedestres_esperando=0):
        """
        Método compatível usado pelo ControladorSemaforo.
        Retorna: (prioridade_float [0..10], ativacoes_list).
        Implementação heurística simples para manter compatibilidade com a lógica existente.
        """
        # normaliza entradas (assume carros até 10, tempo até 30s, pedestres até 6)
        c = max(0.0, min(10.0, float(num_carros_vermelha)))
        t = max(0.0, min(30.0, float(tempo_verde)))
        p = max(0.0, min(6.0, float(num_pedestres_esperando)))

        # heurística: combina componentes (pesos ajustáveis)
        w_c, w_t, w_p = 0.6, 0.2, 0.2
        prioridade_norm = w_c * (c / 10.0) + w_t * (t / 30.0) + w_p * (p / 6.0)
        prioridade = float(max(0.0, min(10.0, prioridade_norm * 10.0)))

        ativacoes = [
            ("componente_carro", float(w_c * (c / 10.0))),
            ("componente_tempo", float(w_t * (t / 30.0))),
            ("componente_pedestres", float(w_p * (p / 6.0))),
        ]
        return prioridade, ativacoes

    def avaliar_regras(self, rotulo_fluxo_carros, rotulo_fluxo_pedestres, hora_str, rotulo_clima):
        """
        Retorna lista de (descricao_regra, grau_ativacao) para as regras implementadas.
        Usa interp_membership nas MF definidas e combina com min/max conforme AND/OR.
        """
        cf = self.mapear_rotulo_de_fluxo_para_valor(rotulo_fluxo_carros)
        pf = self.mapear_rotulo_de_fluxo_para_valor(rotulo_fluxo_pedestres)
        hr = self.mapear_rotulo_hora_para_valor(hora_str)
        cl = self.mapear_rotulo_climatico_para_valor(rotulo_clima)

        u_carro = self.fluxo_de_carros.universe
        u_pedestre = self.fluxo_de_pedestres.universe
        u_hora = self.horario.universe
        u_clima = self.clima.universe

        # carros
        carros_baixo = fuzz.interp_membership(u_carro, self.fluxo_de_carros['Baixo'].mf, cf)
        carros_medio = fuzz.interp_membership(u_carro, self.fluxo_de_carros['Médio'].mf, cf)
        carros_alto  = fuzz.interp_membership(u_carro, self.fluxo_de_carros['Alto'].mf, cf)
        # pedestres
        ped_baixo = fuzz.interp_membership(u_pedestre, self.fluxo_de_pedestres['Baixo'].mf, pf)
        ped_medio = fuzz.interp_membership(u_pedestre, self.fluxo_de_pedestres['Médio'].mf, pf)
        ped_alto  = fuzz.interp_membership(u_pedestre, self.fluxo_de_pedestres['Alto'].mf, pf)
        # horario
        hora_outro  = fuzz.interp_membership(u_hora, self.horario['Outro'].mf, hr)
        hora_normal = fuzz.interp_membership(u_hora, self.horario['Normal'].mf, hr)
        hora_pico   = fuzz.interp_membership(u_hora, self.horario['Pico'].mf, hr)
        # clima
        clima_ensolarado = fuzz.interp_membership(u_clima, self.clima['Ensolarado'].mf, cl)
        clima_nublado   = fuzz.interp_membership(u_clima, self.clima['Nublado'].mf, cl)
        clima_chuvoso  = fuzz.interp_membership(u_clima, self.clima['Chuvoso'].mf, cl)

        # calcula graus conforme regras definidas (mesma ordem das descrições)
        graus = []
        # 1
        graus.append( float(np.fmin(carros_alto, hora_pico)) )
        # 2
        graus.append( float(np.fmin(np.fmin(carros_medio, ped_medio), hora_normal)) )
        # 3
        graus.append( float(np.fmax(carros_baixo, ped_baixo)) )
        # 4
        graus.append( float(np.fmin(np.fmin(carros_alto, ped_alto), hora_normal)) )
        # 5
        graus.append( float(np.fmin(np.fmin(carros_alto, ped_alto), hora_pico)) )
        # 6
        graus.append( float(np.fmin(carros_alto, clima_chuvoso)) )
        # 7
        graus.append( float(np.fmin(np.fmin(carros_baixo, ped_baixo), hora_outro)) )
        # 8
        graus.append( float(np.fmin(carros_baixo, ped_alto)) )
        # 9
        graus.append( float(np.fmin(carros_medio, hora_outro)) )

        ativacoes = list(zip(self.descricoes_regra, graus))
        return ativacoes

class Semaforo:
    def __init__(self, x, y, orientacao='vertical'):
        self.x, self.y, self.orientacao = x, y, orientacao
        self.estado = 'vermelho'
        # parâmetros visuais ajustáveis
        self.housing_w = 40 if orientacao == 'vertical' else 110
        self.housing_h = 110 if orientacao == 'vertical' else 40
        self.radius = 14
        self.padding = 8

    def draw(self):
        # posições base e retângulo da carcaça
        housing = pygame.Rect(self.x, self.y, self.housing_w, self.housing_h)
        inner = housing.inflate(-10, -10)

        # desenha sombra da carcaça
        shadow = pygame.Rect(housing.x + 4, housing.y + 6, housing.w, housing.h)
        pygame.draw.rect(tela, (15, 15, 15, 60), shadow, border_radius=8)

        # carcaça externa e placa interna
        pygame.draw.rect(tela, (20, 20, 20), housing, border_radius=8)
        pygame.draw.rect(tela, (40, 40, 40), inner, border_radius=6)

        # haste/pólo
        if self.orientacao == 'vertical':
            pole = pygame.Rect(housing.centerx - 6, housing.bottom, 12, 60)
            pole_shadow = pygame.Rect(pole.x + 3, pole.y + 4, pole.w, pole.h)
        else:
            pole = pygame.Rect(housing.right, housing.centery - 6, 60, 12)
            pole_shadow = pygame.Rect(pole.x + 4, pole.y + 3, pole.w, pole.h)
        pygame.draw.rect(tela, (20, 20, 20), pole_shadow, border_radius=6)
        pygame.draw.rect(tela, (60, 60, 60), pole, border_radius=6)

        # calcula centros das lâmpadas na ordem (vermelho, amarelo, verde)
        if self.orientacao == 'vertical':
            centers = [
                (housing.centerx, housing.y + self.padding + self.radius),
                (housing.centerx, housing.y + housing.h//2),
                (housing.centerx, housing.y + housing.h - self.padding - self.radius)
            ]
        else:
            centers = [
                (housing.x + self.padding + self.radius, housing.centery),
                (housing.x + housing.w//2, housing.centery),
                (housing.x + housing.w - self.padding - self.radius, housing.centery)
            ]

        # cores efetivas (ligadas vs apagadas)
        col_on = {
            'vermelho': COR_VERMELHA,
            'amarelo': COR_AMARELA,
            'verde': COR_VERDE
        }
        estados_semaforo = ['vermelho', 'amarelo', 'verde']

        # desenha cada lente com brilho/halo quando ligada
        for i, st in enumerate(estados_semaforo):
            center = centers[i]
            on = (self.estado == st)
            base_cor = col_on[st] if on else COR_CINZA_ESCURO

            # halo (apenas quando ligada)
            if on:
                brilho_s = pygame.Surface((self.radius*6, self.radius*6), pygame.SRCALPHA)
                brilho_col = (*col_on[st], 90)
                pygame.draw.circle(brilho_s, brilho_col, (self.radius*3, self.radius*3), int(self.radius*2.6))
                tela.blit(brilho_s, (center[0] - self.radius*3, center[1] - self.radius*3))

            # lente com leve gradiente (simulado por dois círculos)
            pygame.draw.circle(tela, (10,10,10), center, self.radius+2)  # borda escura
            pygame.draw.circle(tela, base_cor, center, self.radius)
            # highlight frontal pequeno
            highlight = pygame.Surface((self.radius*2, self.radius*2), pygame.SRCALPHA)
            pygame.draw.circle(highlight, (255,255,255,60), (int(self.radius*0.6), int(self.radius*0.6)), int(self.radius*0.6))
            tela.blit(highlight, (center[0]-self.radius, center[1]-self.radius))

        # pequeno detalhe: para vertical desenha um parafuso/placa
        screw_color = (30, 30, 30)
        if self.orientacao == 'vertical':
            pygame.draw.circle(tela, screw_color, (housing.centerx - 12, housing.centery), 3)
            pygame.draw.circle(tela, screw_color, (housing.centerx + 12, housing.centery), 3)
        else:
            pygame.draw.circle(tela, screw_color, (housing.centerx, housing.centery - 12), 3)
            pygame.draw.circle(tela, screw_color, (housing.centerx, housing.centery + 12), 3)

class Carro(pygame.sprite.Sprite):
    def __init__(self, x, y, direcao):
        super().__init__()
        self.direcao = direcao
        w, h = (20, 40) if direcao in ['pra_cima', 'pra_baixo'] else (40, 20)
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        cor_carro = random.choice([(30,144,255), (220,20,60), (255,215,0), (60,179,113)])
        pygame.draw.rect(surf, cor_carro, (0, 0, w, h), border_radius=4)
        pygame.draw.rect(surf, (0,0,0), (0,0,w,h), 2, border_radius=4)  # contorno

        # janela frontal posicionada conforme a direção do movimento
        cor_janela_carro = (200, 230, 255)
        if direcao == 'pra_cima':
            # frente no topo
            pygame.draw.rect(surf, cor_janela_carro, (3, 6, w-6, 12), border_radius=3)
        elif direcao == 'pra_baixo':
            # frente na parte inferior
            pygame.draw.rect(surf, cor_janela_carro, (3, h-18, w-6, 12), border_radius=3)
        elif direcao == 'esquerda':
            # frente na lateral esquerda
            pygame.draw.rect(surf, cor_janela_carro, (6, 3, 12, h-6), border_radius=3)
        else:  # right
            # frente na lateral direita
            pygame.draw.rect(surf, cor_janela_carro, (w-18, 3, 12, h-6), border_radius=3)

        self.image = surf
        self.rect = self.image.get_rect(topleft=(x, y))
        self.velocidade = 2

    def update(self, cars_group, traffic_light_v, traffic_light_h):
        global carros_saíram, BLOQUEIO_PEDESTRES_VERT, BLOQUEIO_PEDESTRES_HORI
        pode_mover = True
        # calcula deslocamento
        dx = (1 if self.direcao == 'direita' else -1 if self.direcao == 'esquerda' else 0) * self.velocidade
        dy = (1 if self.direcao == 'pra_baixo' else -1 if self.direcao == 'pra_cima' else 0) * self.velocidade

        # --- Evitar parada SOBRE as faixas: calcula posições seguras de parada usando constantes de faixa ---
        # faixa norte (quem vem de cima - 'pra_baixo')
        topo_norte_cruzado = PARADA_EMBAIXO_MIN - CW_GAP - CW_THICKNESS
        # aproxima ponto de parada para ficar mais perto da faixa (reduz folga)
        parada_segura_embaixo = topo_norte_cruzado + 2  # antes: -4, agora mais próximo

        # faixa sul (quem vem de baixo - 'pra_cima')
        topo_cruzado_sul = PARADA_CIMA_MIN + CW_GAP
        cruz_sul_inferior = topo_cruzado_sul + CW_THICKNESS
        parada_segura_cima = cruz_sul_inferior + 4

        # faixa oeste (quem vem da esquerda - 'direita')
        cruz_oeste_esquerda = PARADA_DIREITA_MIN - CW_GAP - CW_THICKNESS
        # aproxima ponto de parada vindo da esquerda para alinhar com faixas da direita/baixo
        parada_segura_direita = cruz_oeste_esquerda + 2  # antes: -4, agora mais próximo

        # faixa leste (quem vem da direita - 'esquerda')
        cruz_leste_esquerda = PARADA_ESQUERDA_MIN + CW_GAP
        cruz_leste_direita = cruz_leste_esquerda + CW_THICKNESS
        parada_segura_esquerda = cruz_leste_direita + 4

        # checa semáforo / posições de parada sem invadir faixas
        if self.direcao == 'pra_baixo' and traffic_light_v.estado != 'verde':
            # impede mover para dentro da área da faixa norte
            if (self.rect.bottom + dy) > parada_segura_embaixo and self.rect.bottom <= PARADA_EMBAIXO_MAX:
                pode_mover = False

        if self.direcao == 'pra_cima' and traffic_light_v.estado != 'verde':
            # impede mover para dentro da área da faixa sul
            if (self.rect.top + dy) < parada_segura_cima and self.rect.top >= PARADA_CIMA_MIN:
                pode_mover = False

        if self.direcao == 'direita' and traffic_light_h.estado != 'verde':
            # impede mover para dentro da área da faixa oeste
            if (self.rect.right + dx) > parada_segura_direita and self.rect.right <= PARADA_DIREITA_MAX:
                pode_mover = False

        if self.direcao == 'esquerda' and traffic_light_h.estado != 'verde':
            # impede mover para dentro da área da faixa leste
            if (self.rect.left + dx) < parada_segura_esquerda and self.rect.left >= PARADA_ESQUERDA_MIN:
                pode_mover = False

        # bloqueio por pedestres: se houver pedestres atravessando impactando este eixo, bloqueia carros na área de fila
        # vertical cars (pra_cima/pra_baixo) são impactados por BLOQUEIO_PEDESTRES_VERT
        if self.direcao in ('pra_cima', 'pra_baixo') and BLOQUEIO_PEDESTRES_VERT > 0:
            if (self.direcao == 'pra_baixo' and (self.rect.bottom <= PARADA_EMBAIXO_MAX and self.rect.bottom > PARADA_EMBAIXO_MAX - COMPRIMENTO_FILA)) or \
               (self.direcao == 'pra_cima' and (self.rect.top >= PARADA_CIMA_MIN and self.rect.top < PARADA_CIMA_MIN + COMPRIMENTO_FILA)):
                pode_mover = False
        # horizontal cars (left/right) são impactados por BLOQUEIO_PEDESTRES_HORI
        if self.direcao in ('esquerda', 'direita') and BLOQUEIO_PEDESTRES_HORI > 0:
            if (self.direcao == 'direita' and (self.rect.right <= PARADA_DIREITA_MAX and self.rect.right > PARADA_DIREITA_MAX - COMPRIMENTO_FILA)) or \
               (self.direcao == 'esquerda' and (self.rect.left >= PARADA_ESQUERDA_MIN and self.rect.left < PARADA_ESQUERDA_MIN + COMPRIMENTO_FILA)):
                pode_mover = False

        # checa colisão futura com outro carro (bloqueio)
        proxima_reta = self.rect.move(dx, dy)
        for other in cars_group:
            if other is self: continue
            if proxima_reta.colliderect(other.rect):
                pode_mover = False
                break

        # movimento
        if pode_mover:
            self.rect.move_ip(dx, dy)

        # remove fora da tela
        if not tela.get_rect().colliderect(self.rect):
            # conta como saída antes de remover
            carros_saíram += 1
            self.kill()

class Pedestre(pygame.sprite.Sprite):
    """
    Pedestre atravessa sobre as faixas; orientações:
     - 'h_n' = faixa superior vertical (vem de cima)
     - 'h_s' = faixa inferior vertical (vem de baixo)
     - 'v_r' = faixa direita horizontal (vem da direita)
     - 'v_l' = faixa esquerda horizontal (vem da esquerda)
    """
    def __init__(self, orientacao):
        super().__init__()
        self.orientacao = orientacao
        self.velocidade = 1.6
        self.esperando = True
        self.atravessando = False

        # limites das vias (para garantir faixas só sobre as vias)
        estrada_x0, estrada_x1 = 340, 460
        estrada_y0, estrada_y1 = 340, 460

        # calcula posições de faixa consistentes com desenho_ambiente
        # norte: alinhar com PARADA_EMBAIXO_MAX
        norte_y = PARADA_EMBAIXO_MAX - CW_GAP - CW_THICKNESS + CW_THICKNESS // 2
        # sul: alinhar com PARADA_CIMA_MIN + CW_GAP
        sul_y = PARADA_CIMA_MIN + CW_GAP + CW_THICKNESS // 2
        # oeste: alinhar com PARADA_DIREITA_MAX
        oeste_x = PARADA_DIREITA_MAX - CW_GAP - CW_THICKNESS + CW_THICKNESS // 2
        # leste: alinhar com PARADA_ESQUERDA_MIN + CW_GAP
        leste_x = PARADA_ESQUERDA_MIN + CW_GAP + CW_THICKNESS // 2

        if orientacao == 'h_n':
            y = norte_y
            self.pos = pygame.Vector2(estrada_x0 - 30, y)
            self.alvo = pygame.Vector2(estrada_x1 + 30, y)
            tamanho = (10, 16)
        elif orientacao == 'h_s':
            y = sul_y
            self.pos = pygame.Vector2(estrada_x0 - 30, y)
            self.alvo = pygame.Vector2(estrada_x1 + 30, y)
            tamanho = (10, 16)
        elif orientacao == 'v_r':
            x = leste_x
            self.pos = pygame.Vector2(x, estrada_y0 - 30)
            self.alvo = pygame.Vector2(x, estrada_y1 + 30)
            tamanho = (16, 10)
        else:  # v_l
            x = oeste_x
            self.pos = pygame.Vector2(x, estrada_y0 - 30)
            self.alvo = pygame.Vector2(x, estrada_y1 + 30)
            tamanho = (16, 10)

        surf = pygame.Surface(tamanho, pygame.SRCALPHA)
        COLOR_PEDESTRIAN = (240, 128, 128)
        pygame.draw.ellipse(surf, COLOR_PEDESTRIAN, surf.get_rect())
        self.image = surf
        self.rect = self.image.get_rect(center=(int(self.pos.x), int(self.pos.y)))

    def update(self, luz_vertical, luz_horizontal):
        # decide se pode iniciar travessia: somente quando o tráfego PERPENDICULAR estiver RED
        if self.esperando:
            if self.orientacao in ('h_n', 'h_s'):
                # esses atravessam a via vertical -> precisam que luz_vertical seja RED
                if luz_vertical.estado == 'vermelho':
                    self.esperando = False
                    self.atravessando = True
            else:
                # atravessam a via horizontal -> precisam que luz_horizontal seja RED
                if luz_horizontal.estado == 'vermelho':
                    self.esperando = False
                    self.atravessando = True

        if self.atravessando:
            # move em direção ao alvo
            dir_vec = (self.alvo - self.pos)
            if dir_vec.length() != 0:
                move = dir_vec.normalize() * self.velocidade
                if move.length() > dir_vec.length():
                    self.pos = self.alvo
                else:
                    self.pos += move
                self.rect.center = (int(self.pos.x), int(self.pos.y))

            # remove ao terminar travessia
            if (self.pos - self.alvo).length() < 2:
                self.kill()

# --- AGENTE INTELIGENTE (Sem alterações) ---
class ControladorSemaforo:
    def __init__(self, luz_vertical, luz_horizontal):
        self.luz_vertical = luz_vertical
        self.luz_horizontal = luz_horizontal
        self.fuzzy_brain = FuzzyControlador()
        self.luz_vertical.estado = 'vermelho'
        self.luz_horizontal.estado = 'verde'
        self.timer = 0
        self.mudar_sequencia = None
        self.last_priority_score = 0
        self.YELLOW_TIME = 2 * FPS

        # controle de frequência de impressão das ativações fuzzy
        self._last_fuzzy_print_time = 0.0
        self._fuzzy_print_interval = 1.5  # segundos

    def requisicao_travessia_pedestre(self, axis):
        """
        Solicita ao controlador que prepare a troca para permitir travessia de pedestres.
        axis: 'v' -> pedestres que atravessam a via vertical (impactam tráfego vertical => precisamos RED em vertical)
              'h' -> pedestres que atravessam a via horizontal (impactam tráfego horizontal)
        Isso inicia a sequência de amarelo para a via que estiver com verde, garantindo que em poucos frames a via perpendicular fique vermelha.
        """
        # se axis == 'v' queremos que a via vertical fique RED -> vertical vermelho happens when horizontal turns verde? 
        # Implementação: se a via que atualmente está GREEN é a que atrapalha o pedestre, iniciamos amarelo nela para trocar.
        if axis == 'v':
            # pedestres atravessando horizontalmente (impactam tráfego vertical) =>
            # precisamos que luz_vertical fique vermelho (ou seja, tornar vertical RED / horizontal GREEN).
            if self.luz_horizontal.estado == 'verde' and not self.mudar_sequencia:
                self.luz_horizontal.estado = 'amarelo'
                self.mudar_sequencia = 'to_v'
                self.timer = 0
        elif axis == 'h':
            # pedestres atravessando verticalmente (impactam tráfego horizontal) =>
            # precisamos que luz_horizontal fique vermelho (tornar horizontal RED / vertical GREEN)
            if self.luz_vertical.estado == 'verde' and not self.mudar_sequencia:
                self.luz_vertical.estado = 'amarelo'
                self.mudar_sequencia = 'to_h'
                self.timer = 0

    def update(self, cars_v, cars_h, ambiente=None, pedestres_esperando_total=0):
        """
        Atualiza semáforos.
        Agora aceita 'ambiente' (dicionário gerado por gerar_ambiente_aleatorio) para cálculo
        do tempo recomendado via lógica fuzzy estendida.
        """
        # incrementa timer (frames desde início do verde)
        self.timer += 1

        # comportamento anterior mantido: tratamento de mudar_sequencia/amarelo
        if self.mudar_sequencia:
            if self.timer > self.YELLOW_TIME:
                if self.mudar_sequencia == 'to_v':
                    self.luz_horizontal.estado = 'vermelho'
                    self.luz_vertical.estado = 'verde'
                elif self.mudar_sequencia == 'to_h':
                    self.luz_vertical.estado = 'vermelho'
                    self.luz_horizontal.estado = 'verde'
                self.mudar_sequencia = None
                self.timer = 0
            return

        # calcula prioridade original (mantendo compatibilidade)
        carros_na_vermelha = cars_v if self.luz_horizontal.estado == 'verde' else cars_h
        tempo_verde_segundos = self.timer / FPS
        prioridade, ativacoes = self.fuzzy_brain.prioridade_de_computacao(carros_na_vermelha, tempo_verde_segundos)
        self.last_priority_score = float(prioridade)

        # imprime ativações conforme antes
        now = time.time()
        should_print = (now - self._last_fuzzy_print_time >= self._fuzzy_print_interval) or (prioridade >= 5.0)
        if should_print:
            print(f"[FUZZY-PRIOR] prioridade(defuzz)={prioridade:.2f} | entradas: carros_vermelha={carros_na_vermelha}, tempo_verde={tempo_verde_segundos:.2f}s, ped_esperando={pedestres_esperando_total}")
            for desc, grau in ativacoes:
                if grau > 0.01:
                    print(f"  - {desc} -> grau={grau:.3f}")
            print("-" * 40)
            self._last_fuzzy_print_time = now

        # --- Cálculo do tempo recomendado a partir do ambiente (se fornecido) ---
        tempo_recomendado = None
        regra_ativacoes = None
        if ambiente is not None:
            try:
                tempo_recomendado = self.fuzzy_brain.calcular_tempo_a_partir_do_ambiente(ambiente['fluxo_de_carros'], ambiente['fluxo_de_pedestres'], ambiente['hora'], ambiente['clima'])
                # guarda para exibição/debug
                self.last_tempo_recomendado = float(tempo_recomendado)
                # avalia regras e obtém graus
                regra_ativacoes = self.fuzzy_brain.avaliar_regras(ambiente['fluxo_de_carros'], ambiente['fluxo_de_pedestres'], ambiente['hora'], ambiente['clima'])
            except Exception as e:
                # não deve quebrar o loop de simulação
                print("Erro calcular_tempo_a_partir_do_ambiente:", e)
                tempo_recomendado = None

        # imprime regras fuzzy do cálculo de tempo quando houver ambiente (com throttle igual)
        now = time.time()
        if regra_ativacoes is not None and (now - self._last_fuzzy_print_time >= self._fuzzy_print_interval):
            print(f"[FUZZY-TEMPO] tempo_recomendado={tempo_recomendado:.2f}s | ambiente: clima={ambiente['clima']}, fluxo_de_carros={ambiente['fluxo_de_carros']}, fluxo_de_pedestres={ambiente['fluxo_de_pedestres']}, hora={ambiente['hora']}")
            for desc, grau in regra_ativacoes:
                if grau > 0.01:
                    print(f"  - {desc} -> grau={grau:.3f}")
            print("-" * 60)
            self._last_fuzzy_print_time = now

        # --- Decisão de troca (mantém lógica por prioridade) ---
        # se a prioridade fuzzy exigir troca, executa sequência
        if prioridade >= 5.0:
            if self.luz_horizontal.estado == 'verde':
                self.luz_horizontal.estado = 'amarelo'
                self.mudar_sequencia = 'to_v'
            else:
                self.luz_vertical.estado = 'amarelo'
                self.mudar_sequencia = 'to_h'
            self.timer = 0
            return

        # adicional: se o tempo verde atual exceder o tempo recomendado (quando disponível), inicia troca
        if tempo_recomendado is not None:
            if tempo_verde_segundos >= tempo_recomendado:
                if self.luz_horizontal.estado == 'verde':
                    self.luz_horizontal.estado = 'amarelo'
                    self.mudar_sequencia = 'to_v'
                else:
                    self.luz_vertical.estado = 'amarelo'
                    self.mudar_sequencia = 'to_h'
                self.timer = 0

# --- AMBIENTE ---
def desenho_ambiente():
    tela.fill(COR_CINZA)
    pygame.draw.rect(tela, COR_CINZA_ESCURO, (350, 0, 100, ALTURA_TELA))   # via vertical
    pygame.draw.rect(tela, COR_CINZA_ESCURO, (0, 350, LARGURA_TELA, 100))    # via horizontal

    # linhas de divisão das vias (não desenhar dentro do quadrado do cruzamento)
    for y in range(0, ALTURA_TELA, 40):
        if not 350 < y < 450:
            pygame.draw.rect(tela, COR_BRANCA, (395, y, 10, 20))
    for x in range(0, LARGURA_TELA, 40):
        if not 350 < x < 450:
            pygame.draw.rect(tela, COR_BRANCA, (x, 395, 20, 10))

    # --- Faixas de pedestre restritas às vias, posicionadas na SAÍDA da via ---
    cw_thickness = CW_THICKNESS
    faixa_w = 12
    faixa_brecha = 7
    faixa_margem = 8
    cw_gap = CW_GAP

    estrada_x0, estrada_x1 = ESTRADA_X0, ESTRADA_X1
    estrada_y0, estrada_y1 = ESTRADA_Y0, ESTRADA_Y1

    # Usar as coordenadas de "parada" (PARADA_*_MAX/MIN) de forma consistente:
    # - faixa norte (quem vem de cima -> 'pra_baixo'): alinhar com PARADA_EMBAIXO_MAX
    norte_y = PARADA_EMBAIXO_MAX - cw_gap - cw_thickness
    for x in range(estrada_x0 + faixa_margem, estrada_x1 - faixa_margem, faixa_w + faixa_brecha):
        pygame.draw.rect(tela, COR_BRANCA, (x, norte_y, faixa_w, cw_thickness))

    # - faixa sul (quem vem de baixo -> 'pra_cima'): continua alinhada com PARADA_CIMA_MIN + gap
    sul_y = PARADA_CIMA_MIN + cw_gap
    for x in range(estrada_x0 + faixa_margem, estrada_x1 - faixa_margem, faixa_w + faixa_brecha):
        pygame.draw.rect(tela, COR_BRANCA, (x, sul_y, faixa_w, cw_thickness))

    # - faixa oeste (quem vem da esquerda -> 'direita'): alinhar com PARADA_DIREITA_MAX
    esquerda_x = PARADA_DIREITA_MAX - cw_gap - cw_thickness
    for y in range(estrada_y0 + faixa_margem, estrada_y1 - faixa_margem, faixa_w + faixa_brecha):
        pygame.draw.rect(tela, COR_BRANCA, (esquerda_x, y, cw_thickness, faixa_w))

    # - faixa leste (quem vem da direita -> 'esquerda'): continua alinhada com PARADA_ESQUERDA_MIN + gap
    direita_x = PARADA_ESQUERDA_MIN + cw_gap
    for y in range(estrada_y0 + faixa_margem, estrada_y1 - faixa_margem, faixa_w + faixa_brecha):
        pygame.draw.rect(tela, COR_BRANCA, (direita_x, y, cw_thickness, faixa_w))

# Função auxiliar para detectar se um carro está "esperando"
def carros_esperando(car, todos_carros, controlador):
    # calcula próximo rect (mesma lógica do update)
    dx = (1 if car.direcao == 'direita' else -1 if car.direcao == 'esquerda' else 0) * car.velocidade
    dy = (1 if car.direcao == 'pra_baixo' else -1 if car.direcao == 'pra_cima' else 0) * car.velocidade
    proxima_reta = car.rect.move(dx, dy)

    # bloqueio por colisão imediata (outro carro à frente)
    bloqueador_por_carro = False
    for other in todos_carros:
        if other is car: continue
        if proxima_reta.colliderect(other.rect):
            bloqueador_por_carro = True
            break

    # define área de fila (zona mais longa que a linha de parada)
    if car.direcao == 'pra_baixo':
        na_fila = (car.rect.bottom <= PARADA_EMBAIXO_MAX) and (car.rect.bottom > PARADA_EMBAIXO_MAX - COMPRIMENTO_FILA)
        luz_vermelha = controlador.luz_vertical.estado != 'verde'
    elif car.direcao == 'pra_cima':
        na_fila = (car.rect.top >= PARADA_CIMA_MIN) and (car.rect.top < PARADA_CIMA_MIN + COMPRIMENTO_FILA)
        luz_vermelha = controlador.luz_vertical.estado != 'verde'
    elif car.direcao == 'direita':
        na_fila = (car.rect.right <= PARADA_DIREITA_MAX) and (car.rect.right > PARADA_DIREITA_MAX - COMPRIMENTO_FILA)
        luz_vermelha = controlador.luz_horizontal.estado != 'verde'
    else:  # left
        na_fila = (car.rect.left >= PARADA_ESQUERDA_MIN) and (car.rect.left < PARADA_ESQUERDA_MIN + COMPRIMENTO_FILA)
        luz_vermelha = controlador.luz_horizontal.estado != 'verde'

    # conta se está na área de fila e ou o semáforo está vermelho ou está bloqueado por outro carro
    return na_fila and (luz_vermelha or bloqueador_por_carro)

# --- FUNÇÃO MAIN() - MODIFICADA ---
def main():
    global total_gerado, BLOQUEIO_PEDESTRES_VERT, BLOQUEIO_PEDESTRES_HORI
    luz_vertical = Semaforo(300, 150, 'vertical')
    luz_horizontal = Semaforo(150, 300, 'horizontal')
    controlador = ControladorSemaforo(luz_vertical, luz_horizontal)
    todos_carros = pygame.sprite.Group()
    todos_pedestres = pygame.sprite.Group()

    # Variáveis para alternar o lado do spawn manual
    lado_de_spawn_horizontal = 'esquerda'  # O próximo carro 'h' virá da esquerda
    vertical_spawn_side = 'top'    # O próximo carro 'v' virá de cima

    # logging CSV: cria arquivo e escreve header se necessário
    metricas_cabecalho = not ARQUIVOS_METRICAS.exists()
    metricas_f = open(ARQUIVOS_METRICAS, "a", newline="", encoding="utf-8")
    metricas_escrever = csv.writer(metricas_f)
    if metricas_cabecalho:
        metricas_escrever.writerow(["timestamp", "sim_time_s", "carros_via", "total_gerado", "carros_saíram", "esperando_vertical", "esperando_horizontal", "pedestres_esperando", "prioridade"])
        metricas_f.flush()

    tempo_sim = 0.0
    INTERVALO_REGISTROS = 1.0
    ultimo_registro = 0.0

    # ambiente inicial e controle de refresh
    ambiente = gerar_ambiente_aleatorio()
    # NÃO usar auto-refresh: mudança será por botão/tecla
    INTERVALO_ATUALIZACAO_AMBIENTE = None
    ultima_atualizacao_ambiente = None

    # botão para alterar ambiente (canto superior direito)
    botao_ambiente_rect = pygame.Rect(LARGURA_TELA - 180, 50, 170, 34)
    botao_ambiente_cor = (50, 50, 60)
    botao_ambiente_texto = fonte.render("Alterar Ambiente (E)", True, COR_BRANCA)

    # alerta visual quando o ambiente muda
    alerta_comeco_ambiente = None
    ALERTA_ALTERACAO_AMBIENTE = 3.0  # segundos que o alerta permanece visível
    alerta_texto_ambiente = ""

    try:
        while True:
            # controla dt e tempo simulado (usado para logging)
            dt_ms = tempo.tick(FPS)
            dt = dt_ms / 1000.0
            tempo_sim += dt

            # atualiza ambiente aleatório periodicamente (apenas se INTERVALO_ATUALIZACAO_AMBIENTE for numérico)
            if INTERVALO_ATUALIZACAO_AMBIENTE is not None:
                # inicializa timestamp de referência na primeira passada
                if ultima_atualizacao_ambiente is None:
                    ultima_atualizacao_ambiente = tempo_sim
                if tempo_sim - ultima_atualizacao_ambiente >= INTERVALO_ATUALIZACAO_AMBIENTE:
                    novo_ambiente = gerar_ambiente_aleatorio()
                    ambiente = novo_ambiente
                    ultima_atualizacao_ambiente = tempo_sim

                    # --- RESET ao mudar ambiente: remove todos os carros e pedestres ---
                    todos_carros.empty()
                    todos_pedestres.empty()
                    # zera flags de bloqueio de pedestres (caso algum estivesse atravessando)
                    BLOQUEIO_PEDESTRES_VERT = 0
                    BLOQUEIO_PEDESTRES_HORI = 0

                    # registra alerta para exibição na tela
                    alerta_texto_ambiente = f"Ambiente alterado: {ambiente['clima']} | Carros: {ambiente['fluxo_de_carros']} | Pedestres: {ambiente['fluxo_de_pedestres']} | Hora: {ambiente['hora']}"
                    alerta_comeco_ambiente = tempo_sim

            # Loop de eventos (apenas QUIT / ESC)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    raise KeyboardInterrupt
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    raise KeyboardInterrupt
                # tecla rápida para alterar ambiente
                if event.type == pygame.KEYDOWN and event.key == pygame.K_e:
                    # gerar novo ambiente e resetar sprites
                    ambiente = gerar_ambiente_aleatorio()
                    todos_carros.empty()
                    todos_pedestres.empty()
                    BLOQUEIO_PEDESTRES_VERT = 0
                    BLOQUEIO_PEDESTRES_HORI = 0
                    alerta_texto_ambiente = f"Ambiente alterado: {ambiente['clima']} | Carros: {ambiente['fluxo_de_carros']} | Pedestres: {ambiente['fluxo_de_pedestres']} | Hora: {ambiente['hora']}"
                    alerta_comeco_ambiente = tempo_sim
                # clique no botão do mouse para alterar ambiente
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if botao_ambiente_rect.collidepoint(event.pos):
                        ambiente = gerar_ambiente_aleatorio()
                        todos_carros.empty()
                        todos_pedestres.empty()
                        BLOQUEIO_PEDESTRES_VERT = 0
                        BLOQUEIO_PEDESTRES_HORI = 0
                        alerta_texto_ambiente = f"Ambiente alterado: {ambiente['clima']} | Carros: {ambiente['fluxo_de_carros']} | Pedestres: {ambiente['fluxo_de_pedestres']} | Hora: {ambiente['hora']}"
                        alerta_comeco_ambiente = tempo_sim

            # --- SPAWN AUTOMÁTICO ALEATÓRIO ---
            # taxas base (por segundo)
            base_spam_carros_horizontal = 0.6   # base carros por segundo na via horizontal
            base_spam_carros_vertical = 0.6   # base carros por segundo na via vertical
            base_spam_pedestres_cada = 0.06  # base probabilidade por segundo por faixa (cada uma das 4)

            # aplica multiplicadores gerados pelo "fluxo" do ambiente
            carros_multiplicadores = FLUXO_CARROS_MULTIPLOS.get(ambiente["fluxo_de_carros"], 1.0)
            pedestres_multiplicadores = FLUXO_PEDESTRES_MULTIPLOS.get(ambiente["fluxo_de_pedestres"], 1.0)

            taxa_geracao_carros_horizontal = base_spam_carros_horizontal * carros_multiplicadores
            taxa_geracao_carros_vertical = base_spam_carros_vertical * carros_multiplicadores
            taxa_geracao_pedestres_cada = base_spam_pedestres_cada * pedestres_multiplicadores

            # carros horizontais (alterna lado de spawn)
            if random.random() < taxa_geracao_carros_horizontal * dt:
                if lado_de_spawn_horizontal == 'esquerda':
                    c = Carro(-40, 370, 'direita')  # vem da esquerda
                    lado_de_spawn_horizontal = 'direita'
                else:
                    c = Carro(LARGURA_TELA, 410, 'esquerda')  # vem da direita
                    lado_de_spawn_horizontal = 'esquerda'
                todos_carros.add(c)
                total_gerado += 1

            # carros verticais (alterna topo/baixo)
            if random.random() < taxa_geracao_carros_vertical * dt:
                if vertical_spawn_side == 'top':
                    c = Carro(370, -40, 'pra_baixo')  # vem de cima
                    vertical_spawn_side = 'bottom'
                else:
                    c = Carro(410, ALTURA_TELA, 'pra_cima')  # vem de baixo
                    vertical_spawn_side = 'top'
                todos_carros.add(c)
                total_gerado += 1

            # pedestres — cada faixa tem sua chance
            if random.random() < taxa_geracao_pedestres_cada * dt:
                todos_pedestres.add(Pedestre('h_n'))
                controlador.requisicao_travessia_pedestre('h')
            if random.random() < taxa_geracao_pedestres_cada * dt:
                todos_pedestres.add(Pedestre('h_s'))
                controlador.requisicao_travessia_pedestre('h')
            if random.random() < taxa_geracao_pedestres_cada * dt:
                todos_pedestres.add(Pedestre('v_r'))
                controlador.requisicao_travessia_pedestre('v')
            if random.random() < taxa_geracao_pedestres_cada * dt:
                todos_pedestres.add(Pedestre('v_l'))
                controlador.requisicao_travessia_pedestre('v')

            # --- PERCEPÇÃO DO AGENTE (SENSORES) ---
            # conta carros em fila por eixo
            carros_esperando_vertical = 0
            carros_esperando_horizontal = 0
            for car in todos_carros:
                if carros_esperando(car, todos_carros, controlador):
                    if car.direcao in ('pra_baixo', 'pra_cima'):
                        carros_esperando_vertical += 1
                    else:
                        carros_esperando_horizontal += 1

            # atualiza pedestres (decidem iniciar travessia) e conta esperando / atravessando
            pedestres_esperando_total = 0
            pedestres_atravessando_vertical = 0  # pedestres atravessando sobre a via vertical (impactam tráfego vertical)
            pedestres_atravessando_horizontal = 0  # pedestres atravessando sobre a via horizontal (impactam tráfego horizontal)

            # atualiza estado dos pedestres (move quem já está atravessando)
            for ped in list(todos_pedestres):
                ped.update(luz_vertical, luz_horizontal)

            # computa contagens após update
            for ped in todos_pedestres:
                if ped.esperando:
                    pedestres_esperando_total += 1
                if ped.atravessando:
                    if ped.orientacao in ('h_n', 'h_s'):
                        pedestres_atravessando_vertical += 1
                    else:
                        pedestres_atravessando_horizontal += 1

            # atualiza flags globais que bloqueiam carros nas áreas de fila
            BLOQUEIO_PEDESTRES_VERT = pedestres_atravessando_vertical
            BLOQUEIO_PEDESTRES_HORI = pedestres_atravessando_horizontal

            # atualiza controlador com as contagens de carros esperando
            controlador.update(carros_esperando_vertical, carros_esperando_horizontal, ambiente=ambiente, pedestres_esperando_total=pedestres_esperando_total)

            # --- Atualiza movimento dos carros (depois de avaliar bloqueios por pedestres) ---
            todos_carros.update(todos_carros, luz_vertical, luz_horizontal)

            # --- DESENHO ---
            desenho_ambiente()
            todos_carros.draw(tela)
            todos_pedestres.draw(tela)
            luz_vertical.draw()
            luz_horizontal.draw()

            # textos informativos
            info_v = fonte.render(f"Carros esperando na Vertical: {carros_esperando_vertical}", True, COR_PRETA)
            info_h = fonte.render(f"Carros esperando na Horizontal: {carros_esperando_horizontal}", True, COR_PRETA)
            ped_info = fonte.render(f"Pedestres esperando: {pedestres_esperando_total} | atravessando V:{pedestres_atravessando_vertical} H:{pedestres_atravessando_horizontal}", True, COR_PRETA)
            priority_text = fonte.render(f"Prioridade (Fuzzy): {controlador.last_priority_score:.2f}", True, COR_PRETA)

            # mostra tempo recomendado (se disponível no controlador) logo abaixo de pedestres esperando
            if hasattr(controlador, 'last_tempo_recomendado'):
                tempo_recomendado_text = fonte.render(f"Tempo recomendado: {controlador.last_tempo_recomendado:.2f}s", True, COR_PRETA)
            else:
                tempo_recomendado_text = fonte.render("Tempo recomendado: -", True, COR_PRETA)

            # posições de desenho dos textos (mantém espaçamento)
            tela.blit(info_v, (10, 10))
            tela.blit(info_h, (10, 35))
            tela.blit(ped_info, (10, 60))
            tela.blit(tempo_recomendado_text, (10, 60 + ped_info.get_height() + 6))  # abaixo de ped_info
            tela.blit(priority_text, (LARGURA_TELA // 2 - priority_text.get_width() // 2, 10))

            # exibe variáveis aleatórias do ambiente
            ambiente_clima = fonte.render(f"Clima: {ambiente['clima']}", True, COR_PRETA)
            ambiente_fluxo_carros = fonte.render(f"Fluxo Carros: {ambiente['fluxo_de_carros']}", True, COR_PRETA)
            ambiente_fluxo_pedestres = fonte.render(f"Fluxo Pedestres: {ambiente['fluxo_de_pedestres']}", True, COR_PRETA)
            ambiente_hora = fonte.render(f"Horário: {ambiente['hora']}", True, COR_PRETA)

            tela.blit(info_v, (10, 10))
            tela.blit(info_h, (10, 35))
            tela.blit(ped_info, (10, 60))
            tela.blit(tempo_recomendado_text, (10, 60 + ped_info.get_height() + 6))  # abaixo de ped_info
            tela.blit(priority_text, (LARGURA_TELA // 2 - priority_text.get_width() // 2, 10))

            # posição de exibição das variáveis ambientais (canto superior direito),
            # e posiciona o botão logo abaixo do "Horário"
            x_off = LARGURA_TELA - 10
            y0 = 10
            y_clima = y0
            y_fluxo_carros = y_clima + ambiente_clima.get_height() + 4
            y_fluxo_pedestres = y_fluxo_carros + ambiente_fluxo_carros.get_height() + 4
            y_hora = y_fluxo_pedestres + ambiente_fluxo_pedestres.get_height() + 4

            tela.blit(ambiente_clima, (x_off - ambiente_clima.get_width(), y_clima))
            tela.blit(ambiente_fluxo_carros, (x_off - ambiente_fluxo_carros.get_width(), y_fluxo_carros))
            tela.blit(ambiente_fluxo_pedestres, (x_off - ambiente_fluxo_pedestres.get_width(), y_fluxo_pedestres))
            tela.blit(ambiente_hora, (x_off - ambiente_hora.get_width(), y_hora))

            # posiciona o botão imediatamente abaixo do "Horário"
            padding_botao = 6
            botao_x = x_off - botao_ambiente_rect.width
            botao_y = y_hora + ambiente_hora.get_height() + padding_botao
            botao_ambiente_rect.topleft = (botao_x, botao_y)

            # desenha botão de alterar ambiente (agora posicionado dinamicamente)
            pygame.draw.rect(tela, botao_ambiente_cor, botao_ambiente_rect, border_radius=6)
            pygame.draw.rect(tela, (90,90,100), botao_ambiente_rect, 2, border_radius=6)
            tela.blit(botao_ambiente_texto, (botao_ambiente_rect.x + 10, botao_ambiente_rect.y + (botao_ambiente_rect.height - botao_ambiente_texto.get_height())//2))

            # --- Desenha alerta de alteração de ambiente (se ativo) ---
            if alerta_comeco_ambiente is not None:
                decorrido = tempo_sim - alerta_comeco_ambiente
                if decorrido <= ALERTA_ALTERACAO_AMBIENTE:
                    # quebra o texto em linhas para evitar overflow
                    wrap_width = 56
                    lines = textwrap.wrap(alerta_texto_ambiente, wrap_width)
                    # calcula dimensões do overlay conforme o maior texto
                    overlay_w = max((fonte.size(line)[0] for line in lines), default=200) + 40
                    overlay_h = len(lines) * fonte.get_linesize() + 24
                    overlay_s = pygame.Surface((overlay_w, overlay_h), pygame.SRCALPHA)
                    overlay_s.fill((20, 20, 20, 220))  # fundo escuro translúcido
                    ox = LARGURA_TELA // 2 - overlay_w // 2
                    oy = 80
                    tela.blit(overlay_s, (ox, oy))
                    # desenha linhas centradas
                    for i, line in enumerate(lines):
                        line_surf = fonte.render(line, True, (255, 255, 255))
                        tela.blit(line_surf, (LARGURA_TELA // 2 - line_surf.get_width() // 2, oy + 12 + i * fonte.get_linesize()))
                else:
                    alerta_comeco_ambiente = None

            # --- Botão para alterar ambiente (não usa refresh automático) ---
            pygame.draw.rect(tela, botao_ambiente_cor, botao_ambiente_rect, border_radius=6)
            # borda ligeiramente mais clara
            pygame.draw.rect(tela, (90,90,100), botao_ambiente_rect, 2, border_radius=6)
            tela.blit(botao_ambiente_texto, (botao_ambiente_rect.x + 10, botao_ambiente_rect.y + (botao_ambiente_rect.height - botao_ambiente_texto.get_height())//2))

            pygame.display.flip()

            # grava métricas a cada INTERVALO_REGISTROS segundos
            if tempo_sim - ultimo_registro >= INTERVALO_REGISTROS:
                timestamp = time.time()
                carros_via = len(todos_carros)
                metricas_escrever.writerow([timestamp, f"{tempo_sim:.2f}", carros_via, total_gerado, carros_saíram, carros_esperando_vertical, carros_esperando_horizontal, pedestres_esperando_total, f"{controlador.last_priority_score:.2f}"])
                metricas_f.flush()
                ultimo_registro = tempo_sim

    except KeyboardInterrupt:
        # encerra limpo
        metricas_f.close()
        pygame.quit()
        sys.exit()

if __name__ == '__main__':
    main()

# --- PEDRESTES ---
class Pedestre(pygame.sprite.Sprite):
    """
    Pedestre atravessa sobre as faixas; orientações:
     - 'h_n' = faixa superior vertical (vem de cima)
     - 'h_s' = faixa inferior vertical (vem de baixo)
     - 'v_r' = faixa direita horizontal (vem da direita)
     - 'v_l' = faixa esquerda horizontal (vem da esquerda)
    """
    def __init__(self, orientacao):
        super().__init__()
        self.orientacao = orientacao
        self.velocidade = 1.6
        self.esperando = True
        self.atravessando = False

        # limites das vias (para garantir faixas só sobre as vias)
        estrada_x0, estrada_x1 = 340, 460
        estrada_y0, estrada_y1 = 340, 460

        # calcula posições de faixa consistentes com desenho_ambiente
        # norte: alinhar com PARADA_EMBAIXO_MAX
        norte_y = PARADA_EMBAIXO_MAX - CW_GAP - CW_THICKNESS + CW_THICKNESS // 2
        # sul: alinhar com PARADA_CIMA_MIN + CW_GAP
        sul_y = PARADA_CIMA_MIN + CW_GAP + CW_THICKNESS // 2
        # oeste: alinhar com PARADA_DIREITA_MAX
        oeste_x = PARADA_DIREITA_MAX - CW_GAP - CW_THICKNESS + CW_THICKNESS // 2
        # leste: alinhar com PARADA_ESQUERDA_MIN + CW_GAP
        leste_x = PARADA_ESQUERDA_MIN + CW_GAP + CW_THICKNESS // 2

        if orientacao == 'h_n':
            y = norte_y
            self.pos = pygame.Vector2(estrada_x0 - 30, y)
            self.alvo = pygame.Vector2(estrada_x1 + 30, y)
            tamanho = (10, 16)
        elif orientacao == 'h_s':
            y = sul_y
            self.pos = pygame.Vector2(estrada_x0 - 30, y)
            self.alvo = pygame.Vector2(estrada_x1 + 30, y)
            tamanho = (10, 16)
        elif orientacao == 'v_r':
            x = leste_x
            self.pos = pygame.Vector2(x, estrada_y0 - 30)
            self.alvo = pygame.Vector2(x, estrada_y1 + 30)
            tamanho = (16, 10)
        else:  # v_l
            x = oeste_x
            self.pos = pygame.Vector2(x, estrada_y0 - 30)
            self.alvo = pygame.Vector2(x, estrada_y1 + 30)
            tamanho = (16, 10)

        surf = pygame.Surface(tamanho, pygame.SRCALPHA)
        COLOR_PEDESTRIAN = (240, 128, 128)
        pygame.draw.ellipse(surf, COLOR_PEDESTRIAN, surf.get_rect())
        self.image = surf
       
        self.rect = self.image.get_rect(center=(int(self.pos.x), int(self.pos.y)))

    def update(self, luz_vertical, luz_horizontal):
        # decide se pode iniciar travessia: somente quando o tráfego PERPENDICULAR estiver RED
        if self.esperando:
            if self.orientacao in ('h_n', 'h_s'):
                # esses atravessam a via vertical -> precisam que luz_vertical seja RED
                if luz_vertical.estado == 'vermelho':
                    self.esperando = False
                    self.atravessando = True
            else:
                # atravessam a via horizontal -> precisam que luz_horizontal seja RED
                if luz_horizontal.estado == 'vermelho':
                    self.esperando = False
                    self.atravessando = True

        if self.atravessando:
            # move em direção ao alvo
            dir_vec = (self.alvo - self.pos)
            if dir_vec.length() != 0:
                move = dir_vec.normalize() * self.velocidade
                if move.length() > dir_vec.length():
                    self.pos = self.alvo
                else:
                    self.pos += move
                self.rect.center = (int(self.pos.x), int(self.pos.y))

            # remove ao terminar travessia
            if (self.pos - self.alvo).length() < 2:
                self.kill()