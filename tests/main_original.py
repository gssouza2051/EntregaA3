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
# suprime o aviso deprecatório do pkg_resources (setuptools)
warnings.filterwarnings("ignore", message=r".*pkg_resources is deprecated.*", category=UserWarning)
# opcional: suprimir DeprecationWarning gerais (usar com cuidado)
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
#from reset_planilha import verificar_e_resetar_planilha

# Chamar função para resetar planilha se desejado
#verificar_e_resetar_planilha()

# métricas (arquivo)
ARQUIVOS_METRICAS = Path("metricas.csv")
cars_exited = 0
total_spawned = 0

# --- INICIALIZAÇÃO DO PYGAME ---
pygame.init()

# --- CONSTANTES ---
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 800
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Simulador de Semáforo com Lógica Fuzzy")

# Cores e Fonte
COLOR_WHITE = (255, 255, 255)
COLOR_BLACK = (0, 0, 0)
COLOR_GRAY = (100, 100, 100)
COLOR_GREEN = (0, 200, 0)
COLOR_YELLOW = (255, 255, 0)
COLOR_RED = (200, 0, 0)
COLOR_DARK_GRAY = (50, 50, 50)
font = pygame.font.SysFont("Arial", 20)

# Controle de tempo
clock = pygame.time.Clock()
FPS = 60

# Zonas de parada (ajustadas e separadas por direção)
STOP_DOWN_MIN, STOP_DOWN_MAX = 320, 360   # vindo de cima (rect.bottom)
STOP_UP_MIN,   STOP_UP_MAX   = 440, 480   # vindo de baixo (rect.top)
STOP_RIGHT_MIN,STOP_RIGHT_MAX= 320, 360   # vindo da esquerda (rect.right)
STOP_LEFT_MIN, STOP_LEFT_MAX = 440, 480   # vindo da direita (rect.left)

# extensão da área considerada "fila" atrás da linha de parada (em pixels)
QUEUE_LENGTH = 160

# Constantes das faixas (reutilizadas pelo spawn dos pedestres)
CW_THICKNESS = 22
CW_GAP = 12

# limites das vias (usados por desenho e lógica para detectar faixas)
ROAD_X0, ROAD_X1 = 350, 450
ROAD_Y0, ROAD_Y1 = 350, 450

# flags globais para bloquear tráfego quando pedestres estão atravessando
PED_BLOCK_V = 0  # pedestres atravessando a via vertical (impactam tráfego vertical)
PED_BLOCK_H = 0  # pedestres atravessando a via horizontal (impactam tráfego horizontal)

# --- Variáveis ambientais randômicas (clima / fluxo / horário) ---
CLIMATES = ["Ensolarado", "Chuvoso", "Nublado"]
FLOW_LEVELS = ["Baixo", "Médio", "Alto"]

# mapeamento de níveis para multiplicadores de spawn (valores base serão multiplicados)
CAR_FLOW_MULT = {"Baixo": 0.25, "Médio": 0.6, "Alto": 1.3}
PED_FLOW_MULT = {"Baixo": 0.25, "Médio": 0.6, "Alto": 1.3}

import datetime

def generate_random_environment():
    """Gera um dicionário com clima, fluxo de carros, fluxo de pedestres e horário aleatório.
    Se a hora cair em período de pico (06:30-08:00 ou 18:00-19:00) força car_flow = 'Alto'.
    """
    clima = random.choice(CLIMATES)
    # horário aleatório do dia
    seconds = random.randint(0, 24*3600 - 1)
    hora_dt = (datetime.datetime.min + datetime.timedelta(seconds=seconds)).time()
    hora = hora_dt.strftime("%H:%M:%S")

    # escolha inicial com pesos para ter mais probabilidade de Médio
    carro_flow = random.choices(FLOW_LEVELS, weights=[1, 3, 2], k=1)[0]
    ped_flow = random.choices(FLOW_LEVELS, weights=[2, 3, 1], k=1)[0]

    # se estiver em horário de pico, força fluxo de carros Alto
    pico_manha_start = datetime.time(6, 30, 0)
    pico_manha_end   = datetime.time(8, 0, 0)
    pico_tarde_start = datetime.time(18, 0, 0)
    pico_tarde_end   = datetime.time(19, 0, 0)
    if (pico_manha_start <= hora_dt <= pico_manha_end) or (pico_tarde_start <= hora_dt <= pico_tarde_end):
        carro_flow = "Alto"

    return {"clima": clima, "car_flow": carro_flow, "ped_flow": ped_flow, "hora": hora}

# --- CÉREBRO FUZZY (Sem alterações) ---

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
        self.car_flow = ctrl.Antecedent(np.arange(0, 11, 1), 'car_flow')      # 0..10
        self.ped_flow = ctrl.Antecedent(np.arange(0, 11, 1), 'ped_flow')      # 0..10
        self.horario = ctrl.Antecedent(np.arange(0, 3, 1), 'horario')        # 0:Outro,1:Normal,2:Pico
        self.clima = ctrl.Antecedent(np.arange(0, 3, 1), 'clima')            # 0:Ensolarado,1:Nublado,2:Chuvoso

        # saída
        self.tempo_semaforo = ctrl.Consequent(np.arange(0, 31, 1), 'tempo_semaforo')  # 0..30 segundos

        # memberships - fluxo carros / pedestres (Baixo/Médio/Alto)
        self.car_flow['Baixo']  = fuzz.trimf(self.car_flow.universe, [0, 0, 4])
        self.car_flow['Médio']  = fuzz.trimf(self.car_flow.universe, [2, 5, 8])
        self.car_flow['Alto']   = fuzz.trimf(self.car_flow.universe, [6, 10, 10])

        self.ped_flow['Baixo']  = fuzz.trimf(self.ped_flow.universe, [0, 0, 4])
        self.ped_flow['Médio']  = fuzz.trimf(self.ped_flow.universe, [2, 5, 8])
        self.ped_flow['Alto']   = fuzz.trimf(self.ped_flow.universe, [6, 10, 10])

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
        rules = []

        # 1. SE (Fluxo de Carros é Alto) E (Horário é Pico) ENTÃO (Tempo é Alto).
        rules.append(ctrl.Rule(self.car_flow['Alto'] & self.horario['Pico'], self.tempo_semaforo['Alto']))

        # 2. SE (Fluxo de Carros é Médio) E (Fluxo de Pedestres é Médio) E (Horário é Normal) ENTÃO (Tempo é Médio).
        rules.append(ctrl.Rule(self.car_flow['Médio'] & self.ped_flow['Médio'] & self.horario['Normal'], self.tempo_semaforo['Médio']))

        # 3. SE (Fluxo de Carros é Baixo) OU (Fluxo de Pedestres é Baixo) ENTÃO (Tempo é Baixo).
        rules.append(ctrl.Rule(self.car_flow['Baixo'] | self.ped_flow['Baixo'], self.tempo_semaforo['Baixo']))

        # 4. SE (Fluxo de Carros é Alto) E (Fluxo de Pedestres é Alto) E (Horário é Normal) ENTÃO (Tempo é Médio).
        rules.append(ctrl.Rule(self.car_flow['Alto'] & self.ped_flow['Alto'] & self.horario['Normal'], self.tempo_semaforo['Médio']))

        # 5. SE (Fluxo de Carros é Alto) E (Fluxo de Pedestres é Alto) E (Horário é Pico) ENTÃO (Tempo é Alto).
        rules.append(ctrl.Rule(self.car_flow['Alto'] & self.ped_flow['Alto'] & self.horario['Pico'], self.tempo_semaforo['Alto']))

        # 6. SE (Fluxo de Carros é Alto) E (Clima é Chuvoso) ENTÃO (Tempo é Alto).
        rules.append(ctrl.Rule(self.car_flow['Alto'] & self.clima['Chuvoso'], self.tempo_semaforo['Alto']))

        # Regras adicionais conforme especificado:
        # - SE Fluxo de Carros é Baixo E Fluxo de Pedestres é Baixo E Horário Outro ENTÃO Tempo Baixo.
        rules.append(ctrl.Rule(self.car_flow['Baixo'] & self.ped_flow['Baixo'] & self.horario['Outro'], self.tempo_semaforo['Baixo']))

        # - SE Fluxo de Carros é Baixo E Fluxo de Pedestres é Alto ENTÃO Tempo Médio.
        rules.append(ctrl.Rule(self.car_flow['Baixo'] & self.ped_flow['Alto'], self.tempo_semaforo['Médio']))

        # - SE Fluxo de Carros é Médio E Horário é Outro ENTÃO Tempo Médio.
        rules.append(ctrl.Rule(self.car_flow['Médio'] & self.horario['Outro'], self.tempo_semaforo['Médio']))

        # monta sistema
        self.sistema = ctrl.ControlSystem(rules)
        self.sim = ctrl.ControlSystemSimulation(self.sistema)

        # armazenar descrições das regras na mesma ordem (para impressão)
        self.rules_descriptions = [
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
    def map_flow_label_to_value(label):
        return {'Baixo': 2.0, 'Médio': 5.0, 'Alto': 9.0}.get(label, 5.0)

    @staticmethod
    def map_clima_label_to_value(label):
        return {'Ensolarado': 0.0, 'Nublado': 1.0, 'Chuvoso': 2.0}.get(label, 1.0)

    @staticmethod
    def map_hora_label_to_value(hora_str):
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

    def compute_tempo_from_env(self, car_flow_label, ped_flow_label, hora_str, clima_label):
        """
        Recebe labels do ambiente (strings) e retorna tempo_recomendado (float segundos).
        Implementação mais resiliente: usa uma simulação local e tenta recuperar a saída
        mesmo que a chave não exista exatamente como 'tempo_semaforo'.
        """
        cf = self.map_flow_label_to_value(car_flow_label)
        pf = self.map_flow_label_to_value(ped_flow_label)
        hr = self.map_hora_label_to_value(hora_str)
        cl = self.map_clima_label_to_value(clima_label)

        try:
            # cria uma simulação local para evitar estado/resíduos entre chamadas
            sim_local = ctrl.ControlSystemSimulation(self.sistema)
            sim_local.input['car_flow'] = float(cf)
            sim_local.input['ped_flow'] = float(pf)
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
            print("Erro compute_tempo_from_env:", e)
            tempo = 12.0

        return tempo

    def compute_priority(self, num_carros_vermelha, tempo_verde, num_pedestres_esperando=0):
        """
        Método compatível usado pelo TrafficLightController.
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
            ("car_component", float(w_c * (c / 10.0))),
            ("time_component", float(w_t * (t / 30.0))),
            ("ped_component", float(w_p * (p / 6.0))),
        ]
        return prioridade, ativacoes

    def evaluate_rules(self, car_flow_label, ped_flow_label, hora_str, clima_label):
        """
        Retorna lista de (descricao_regra, grau_ativacao) para as regras implementadas.
        Usa interp_membership nas MF definidas e combina com min/max conforme AND/OR.
        """
        cf = self.map_flow_label_to_value(car_flow_label)
        pf = self.map_flow_label_to_value(ped_flow_label)
        hr = self.map_hora_label_to_value(hora_str)
        cl = self.map_clima_label_to_value(clima_label)

        u_car = self.car_flow.universe
        u_ped = self.ped_flow.universe
        u_hor = self.horario.universe
        u_cli = self.clima.universe

        # memberships carros
        car_baixo = fuzz.interp_membership(u_car, self.car_flow['Baixo'].mf, cf)
        car_medio = fuzz.interp_membership(u_car, self.car_flow['Médio'].mf, cf)
        car_alto  = fuzz.interp_membership(u_car, self.car_flow['Alto'].mf, cf)
        # pedestres
        ped_baixo = fuzz.interp_membership(u_ped, self.ped_flow['Baixo'].mf, pf)
        ped_medio = fuzz.interp_membership(u_ped, self.ped_flow['Médio'].mf, pf)
        ped_alto  = fuzz.interp_membership(u_ped, self.ped_flow['Alto'].mf, pf)
        # horario
        hor_outro  = fuzz.interp_membership(u_hor, self.horario['Outro'].mf, hr)
        hor_normal = fuzz.interp_membership(u_hor, self.horario['Normal'].mf, hr)
        hor_pico   = fuzz.interp_membership(u_hor, self.horario['Pico'].mf, hr)
        # clima
        cli_ensol = fuzz.interp_membership(u_cli, self.clima['Ensolarado'].mf, cl)
        cli_nub   = fuzz.interp_membership(u_cli, self.clima['Nublado'].mf, cl)
        cli_chuv  = fuzz.interp_membership(u_cli, self.clima['Chuvoso'].mf, cl)

        # calcula graus conforme regras definidas (mesma ordem das descrições)
        graus = []
        # 1
        graus.append( float(np.fmin(car_alto, hor_pico)) )
        # 2
        graus.append( float(np.fmin(np.fmin(car_medio, ped_medio), hor_normal)) )
        # 3
        graus.append( float(np.fmax(car_baixo, ped_baixo)) )
        # 4
        graus.append( float(np.fmin(np.fmin(car_alto, ped_alto), hor_normal)) )
        # 5
        graus.append( float(np.fmin(np.fmin(car_alto, ped_alto), hor_pico)) )
        # 6
        graus.append( float(np.fmin(car_alto, cli_chuv)) )
        # 7
        graus.append( float(np.fmin(np.fmin(car_baixo, ped_baixo), hor_outro)) )
        # 8
        graus.append( float(np.fmin(car_baixo, ped_alto)) )
        # 9
        graus.append( float(np.fmin(car_medio, hor_outro)) )

        ativacoes = list(zip(self.rules_descriptions, graus))
        return ativacoes

class TrafficLight:
    def __init__(self, x, y, orientation='vertical'):
        self.x, self.y, self.orientation = x, y, orientation
        self.state = 'red'
        # parâmetros visuais ajustáveis
        self.housing_w = 40 if orientation == 'vertical' else 110
        self.housing_h = 110 if orientation == 'vertical' else 40
        self.radius = 14
        self.padding = 8

    def draw(self):
        # posições base e retângulo da carcaça
        housing = pygame.Rect(self.x, self.y, self.housing_w, self.housing_h)
        inner = housing.inflate(-10, -10)

        # desenha sombra da carcaça
        shadow = pygame.Rect(housing.x + 4, housing.y + 6, housing.w, housing.h)
        pygame.draw.rect(screen, (15, 15, 15, 60), shadow, border_radius=8)

        # carcaça externa e placa interna
        pygame.draw.rect(screen, (20, 20, 20), housing, border_radius=8)
        pygame.draw.rect(screen, (40, 40, 40), inner, border_radius=6)

        # haste/pólo
        if self.orientation == 'vertical':
            pole = pygame.Rect(housing.centerx - 6, housing.bottom, 12, 60)
            pole_shadow = pygame.Rect(pole.x + 3, pole.y + 4, pole.w, pole.h)
        else:
            pole = pygame.Rect(housing.right, housing.centery - 6, 60, 12)
            pole_shadow = pygame.Rect(pole.x + 4, pole.y + 3, pole.w, pole.h)
        pygame.draw.rect(screen, (20, 20, 20), pole_shadow, border_radius=6)
        pygame.draw.rect(screen, (60, 60, 60), pole, border_radius=6)

        # calcula centros das lâmpadas na ordem (red, yellow, green)
        if self.orientation == 'vertical':
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
            'red': COLOR_RED,
            'yellow': COLOR_YELLOW,
            'green': COLOR_GREEN
        }
        states = ['red', 'yellow', 'green']

        # desenha cada lente com brilho/halo quando ligada
        for i, st in enumerate(states):
            center = centers[i]
            on = (self.state == st)
            base_color = col_on[st] if on else COLOR_DARK_GRAY

            # halo (apenas quando ligada)
            if on:
                glow_s = pygame.Surface((self.radius*6, self.radius*6), pygame.SRCALPHA)
                glow_col = (*col_on[st], 90)
                pygame.draw.circle(glow_s, glow_col, (self.radius*3, self.radius*3), int(self.radius*2.6))
                screen.blit(glow_s, (center[0] - self.radius*3, center[1] - self.radius*3))

            # lente com leve gradiente (simulado por dois círculos)
            pygame.draw.circle(screen, (10,10,10), center, self.radius+2)  # borda escura
            pygame.draw.circle(screen, base_color, center, self.radius)
            # highlight frontal pequeno
            highlight = pygame.Surface((self.radius*2, self.radius*2), pygame.SRCALPHA)
            pygame.draw.circle(highlight, (255,255,255,60), (int(self.radius*0.6), int(self.radius*0.6)), int(self.radius*0.6))
            screen.blit(highlight, (center[0]-self.radius, center[1]-self.radius))

        # pequeno detalhe: para vertical desenha um parafuso/placa
        screw_color = (30, 30, 30)
        if self.orientation == 'vertical':
            pygame.draw.circle(screen, screw_color, (housing.centerx - 12, housing.centery), 3)
            pygame.draw.circle(screen, screw_color, (housing.centerx + 12, housing.centery), 3)
        else:
            pygame.draw.circle(screen, screw_color, (housing.centerx, housing.centery - 12), 3)
            pygame.draw.circle(screen, screw_color, (housing.centerx, housing.centery + 12), 3)

class Car(pygame.sprite.Sprite):
    def __init__(self, x, y, direction):
        super().__init__()
        self.direction = direction
        w, h = (20, 40) if direction in ['up', 'down'] else (40, 20)
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        body_color = random.choice([(30,144,255), (220,20,60), (255,215,0), (60,179,113)])
        pygame.draw.rect(surf, body_color, (0, 0, w, h), border_radius=4)
        pygame.draw.rect(surf, (0,0,0), (0,0,w,h), 2, border_radius=4)  # contorno

        # janela frontal posicionada conforme a direção do movimento
        window_color = (200, 230, 255)
        if direction == 'up':
            # frente no topo
            pygame.draw.rect(surf, window_color, (3, 6, w-6, 12), border_radius=3)
        elif direction == 'down':
            # frente na parte inferior
            pygame.draw.rect(surf, window_color, (3, h-18, w-6, 12), border_radius=3)
        elif direction == 'left':
            # frente na lateral esquerda
            pygame.draw.rect(surf, window_color, (6, 3, 12, h-6), border_radius=3)
        else:  # right
            # frente na lateral direita
            pygame.draw.rect(surf, window_color, (w-18, 3, 12, h-6), border_radius=3)

        self.image = surf
        self.rect = self.image.get_rect(topleft=(x, y))
        self.speed = 2

    def update(self, cars_group, traffic_light_v, traffic_light_h):
        global cars_exited, PED_BLOCK_V, PED_BLOCK_H
        can_move = True
        # calcula deslocamento
        dx = (1 if self.direction == 'right' else -1 if self.direction == 'left' else 0) * self.speed
        dy = (1 if self.direction == 'down' else -1 if self.direction == 'up' else 0) * self.speed

        # --- Evitar parada SOBRE as faixas: calcula posições seguras de parada usando constantes de faixa ---
        # faixa norte (quem vem de cima - 'down')
        cross_north_top = STOP_DOWN_MIN - CW_GAP - CW_THICKNESS
        safe_stop_down = cross_north_top - 4  # margem para não invadir a faixa

        # faixa sul (quem vem de baixo - 'up')
        cross_south_top = STOP_UP_MIN + CW_GAP
        cross_south_bottom = cross_south_top + CW_THICKNESS
        safe_stop_up = cross_south_bottom + 4

        # faixa oeste (quem vem da esquerda - 'right')
        cross_west_left = STOP_RIGHT_MIN - CW_GAP - CW_THICKNESS
        safe_stop_right = cross_west_left - 4

        # faixa leste (quem vem da direita - 'left')
        cross_east_left = STOP_LEFT_MIN + CW_GAP
        cross_east_right = cross_east_left + CW_THICKNESS
        safe_stop_left = cross_east_right + 4

        # checa semáforo / posições de parada sem invadir faixas
        if self.direction == 'down' and traffic_light_v.state != 'green':
            # impede mover para dentro da área da faixa norte
            if (self.rect.bottom + dy) > safe_stop_down and self.rect.bottom <= STOP_DOWN_MAX:
                can_move = False

        if self.direction == 'up' and traffic_light_v.state != 'green':
            # impede mover para dentro da área da faixa sul
            if (self.rect.top + dy) < safe_stop_up and self.rect.top >= STOP_UP_MIN:
                can_move = False

        if self.direction == 'right' and traffic_light_h.state != 'green':
            # impede mover para dentro da área da faixa oeste
            if (self.rect.right + dx) > safe_stop_right and self.rect.right <= STOP_RIGHT_MAX:
                can_move = False

        if self.direction == 'left' and traffic_light_h.state != 'green':
            # impede mover para dentro da área da faixa leste
            if (self.rect.left + dx) < safe_stop_left and self.rect.left >= STOP_LEFT_MIN:
                can_move = False

        # bloqueio por pedestres: se houver pedestres atravessando impactando este eixo, bloqueia carros na área de fila
        # vertical cars (up/down) são impactados por PED_BLOCK_V
        if self.direction in ('up', 'down') and PED_BLOCK_V > 0:
            if (self.direction == 'down' and (self.rect.bottom <= STOP_DOWN_MAX and self.rect.bottom > STOP_DOWN_MAX - QUEUE_LENGTH)) or \
               (self.direction == 'up' and (self.rect.top >= STOP_UP_MIN and self.rect.top < STOP_UP_MIN + QUEUE_LENGTH)):
                can_move = False
        # horizontal cars (left/right) são impactados por PED_BLOCK_H
        if self.direction in ('left', 'right') and PED_BLOCK_H > 0:
            if (self.direction == 'right' and (self.rect.right <= STOP_RIGHT_MAX and self.rect.right > STOP_RIGHT_MAX - QUEUE_LENGTH)) or \
               (self.direction == 'left' and (self.rect.left >= STOP_LEFT_MIN and self.rect.left < STOP_LEFT_MIN + QUEUE_LENGTH)):
                can_move = False

        # checa colisão futura com outro carro (bloqueio)
        next_rect = self.rect.move(dx, dy)
        for other in cars_group:
            if other is self: continue
            if next_rect.colliderect(other.rect):
                can_move = False
                break

        # movimento
        if can_move:
            self.rect.move_ip(dx, dy)

        # remove fora da tela
        if not screen.get_rect().colliderect(self.rect):
            # conta como saída antes de remover
            cars_exited += 1
            self.kill()

class Pedestrian(pygame.sprite.Sprite):
    """
    Pedestre atravessa exatamente na localização das faixas.
    orientation:
       'h_n' = faixa superior vertical (U)  -> atravessa horizontalmente (left -> right)
       'h_s' = faixa inferior vertical (I)  -> atravessa horizontalmente (left -> right)
       'v_r' = faixa direita horizontal (O)  -> atravessa verticalmente (top -> bottom)
       'v_l' = faixa esquerda horizontal (P)-> atravessa verticalmente (top -> bottom)
    """
    def __init__(self, orientation):
        super().__init__()
        self.orientation = orientation
        self.speed = 1.6
        self.waiting = True
        self.crossing = False

        # limites das vias (para garantir faixas só sobre as vias)
        ROAD_X0, ROAD_X1 = 340, 460   # vertical: x-range da via
        ROAD_Y0, ROAD_Y1 = 340, 460   # horizontal: y-range da via

        # spawn e target calculados com base nas constantes das faixas
        if orientation == 'h_n':
            y = (STOP_DOWN_MIN - CW_GAP - CW_THICKNESS) + CW_THICKNESS//2
            self.pos = pygame.Vector2(ROAD_X0 - 30, y)
            self.target = pygame.Vector2(ROAD_X1 + 30, y)
            size = (10, 16)
        elif orientation == 'h_s':
            y = (STOP_UP_MIN + CW_GAP) + CW_THICKNESS//2
            self.pos = pygame.Vector2(ROAD_X0 - 30, y)
            self.target = pygame.Vector2(ROAD_X1 + 30, y)
            size = (10, 16)
        elif orientation == 'v_r':
            x = (STOP_LEFT_MIN + CW_GAP) + CW_THICKNESS//2
            self.pos = pygame.Vector2(x, ROAD_Y0 - 30)
            self.target = pygame.Vector2(x, ROAD_Y1 + 30)
            size = (16, 10)
        else:  # v_l
            x = (STOP_RIGHT_MIN - CW_GAP - CW_THICKNESS) + CW_THICKNESS//2
            self.pos = pygame.Vector2(x, ROAD_Y0 - 30)
            self.target = pygame.Vector2(x, ROAD_Y1 + 30)
            size = (16, 10)

        surf = pygame.Surface(size, pygame.SRCALPHA)
        COLOR_PEDESTRIAN = (240, 128, 128)
        pygame.draw.ellipse(surf, COLOR_PEDESTRIAN, surf.get_rect())
        self.image = surf
        self.rect = self.image.get_rect(center=(int(self.pos.x), int(self.pos.y)))

    def update(self, light_v, light_h):
        # decide se pode iniciar travessia: somente quando o tráfego perpendicular estiver parado (red)
        if self.waiting:
            if self.orientation in ('h_n', 'h_s'):
                # precisam que a via vertical esteja RED para poderem atravessar (pois atravessam a via vertical)
                if light_v.state == 'red':
                    self.waiting = False
                    self.crossing = True
            else:
                # v_* atravessam a via horizontal, precisam que light_h seja red
                if light_h.state == 'red':
                    self.waiting = False
                    self.crossing = True

        if self.crossing:
            # move em direção ao target
            dir_vec = (self.target - self.pos)
            if dir_vec.length() != 0:
                move = dir_vec.normalize() * self.speed
                # evita overshoot
                if move.length() > dir_vec.length():
                    self.pos = self.target
                else:
                    self.pos += move
                self.rect.center = (int(self.pos.x), int(self.pos.y))

            # fim da travessia -> remove
            if (self.pos - self.target).length() < 2:
                self.kill()

# --- AGENTE INTELIGENTE (Sem alterações) ---
class TrafficLightController:
    def __init__(self, light_v, light_h):
        self.light_v = light_v
        self.light_h = light_h
        self.fuzzy_brain = FuzzyControlador()
        self.light_v.state = 'red'
        self.light_h.state = 'green'
        self.timer = 0
        self.change_sequence = None
        self.last_priority_score = 0
        self.YELLOW_TIME = 2 * FPS

        # controle de frequência de impressão das ativações fuzzy
        self._last_fuzzy_print_time = 0.0
        self._fuzzy_print_interval = 1.5  # segundos

    def request_ped_cross(self, axis):
        """
        Solicita ao controlador que prepare a troca para permitir travessia de pedestres.
        axis: 'v' -> pedestres que atravessam a via vertical (impactam tráfego vertical => precisamos RED em vertical)
              'h' -> pedestres que atravessam a via horizontal (impactam tráfego horizontal)
        Isso inicia a sequência de amarelo para a via que estiver com green, garantindo que em poucos frames a via perpendicular fique vermelha.
        """
        # se axis == 'v' queremos que a via vertical fique RED -> vertical red happens when horizontal turns green? 
        # Implementação: se a via que atualmente está GREEN é a que atrapalha o pedestre, iniciamos amarelo nela para trocar.
        if axis == 'v':
            # pedestres atravessando horizontalmente (impactam tráfego vertical) =>
            # precisamos que light_v fique red (ou seja, tornar vertical RED / horizontal GREEN).
            if self.light_h.state == 'green' and not self.change_sequence:
                self.light_h.state = 'yellow'
                self.change_sequence = 'to_v'
                self.timer = 0
        elif axis == 'h':
            # pedestres atravessando verticalmente (impactam tráfego horizontal) =>
            # precisamos que light_h fique red (tornar horizontal RED / vertical GREEN)
            if self.light_v.state == 'green' and not self.change_sequence:
                self.light_v.state = 'yellow'
                self.change_sequence = 'to_h'
                self.timer = 0

    def update(self, cars_v, cars_h, env=None, ped_waiting_total=0):
        """
        Atualiza semáforos.
        Agora aceita 'env' (dicionário gerado por generate_random_environment) para cálculo
        do tempo recomendado via lógica fuzzy estendida.
        """
        # incrementa timer (frames desde início do verde)
        self.timer += 1

        # comportamento anterior mantido: tratamento de change_sequence/amarelo
        if self.change_sequence:
            if self.timer > self.YELLOW_TIME:
                if self.change_sequence == 'to_v':
                    self.light_h.state = 'red'
                    self.light_v.state = 'green'
                elif self.change_sequence == 'to_h':
                    self.light_v.state = 'red'
                    self.light_h.state = 'green'
                self.change_sequence = None
                self.timer = 0
            return

        # calcula prioridade original (mantendo compatibilidade)
        carros_na_vermelha = cars_v if self.light_h.state == 'green' else cars_h
        tempo_verde_segundos = self.timer / FPS
        priority, ativacoes = self.fuzzy_brain.compute_priority(carros_na_vermelha, tempo_verde_segundos)
        self.last_priority_score = float(priority)

        # imprime ativações conforme antes
        now = time.time()
        should_print = (now - self._last_fuzzy_print_time >= self._fuzzy_print_interval) or (priority >= 5.0)
        if should_print:
            print(f"[FUZZY-PRIOR] prioridade(defuzz)={priority:.2f} | entradas: carros_vermelha={carros_na_vermelha}, tempo_verde={tempo_verde_segundos:.2f}s, ped_esperando={ped_waiting_total}")
            for desc, grau in ativacoes:
                if grau > 0.01:
                    print(f"  - {desc} -> grau={grau:.3f}")
            print("-" * 40)
            self._last_fuzzy_print_time = now

        # --- Cálculo do tempo recomendado a partir do ambiente (se fornecido) ---
        tempo_recomendado = None
        regra_ativacoes = None
        if env is not None:
            try:
                tempo_recomendado = self.fuzzy_brain.compute_tempo_from_env(env['car_flow'], env['ped_flow'], env['hora'], env['clima'])
                # guarda para exibição/debug
                self.last_tempo_recomendado = float(tempo_recomendado)
                # avalia regras e obtém graus
                regra_ativacoes = self.fuzzy_brain.evaluate_rules(env['car_flow'], env['ped_flow'], env['hora'], env['clima'])
            except Exception as e:
                # não deve quebrar o loop de simulação
                print("Erro compute_tempo_from_env:", e)
                tempo_recomendado = None

        # imprime regras fuzzy do cálculo de tempo quando houver env (com throttle igual)
        now = time.time()
        if regra_ativacoes is not None and (now - self._last_fuzzy_print_time >= self._fuzzy_print_interval):
            print(f"[FUZZY-TEMPO] tempo_recomendado={tempo_recomendado:.2f}s | env: clima={env['clima']}, car_flow={env['car_flow']}, ped_flow={env['ped_flow']}, hora={env['hora']}")
            for desc, grau in regra_ativacoes:
                if grau > 0.01:
                    print(f"  - {desc} -> grau={grau:.3f}")
            print("-" * 60)
            self._last_fuzzy_print_time = now

        # --- Decisão de troca (mantém lógica por prioridade) ---
        # se a prioridade fuzzy exigir troca, executa sequência
        if priority >= 5.0:
            if self.light_h.state == 'green':
                self.light_h.state = 'yellow'
                self.change_sequence = 'to_v'
            else:
                self.light_v.state = 'yellow'
                self.change_sequence = 'to_h'
            self.timer = 0
            return

        # adicional: se o tempo verde atual exceder o tempo recomendado (quando disponível), inicia troca
        if tempo_recomendado is not None:
            if tempo_verde_segundos >= tempo_recomendado:
                if self.light_h.state == 'green':
                    self.light_h.state = 'yellow'
                    self.change_sequence = 'to_v'
                else:
                    self.light_v.state = 'yellow'
                    self.change_sequence = 'to_h'
                self.timer = 0

# --- AMBIENTE ---
def draw_environment():
    screen.fill(COLOR_GRAY)
    pygame.draw.rect(screen, COLOR_DARK_GRAY, (350, 0, 100, SCREEN_HEIGHT))   # via vertical
    pygame.draw.rect(screen, COLOR_DARK_GRAY, (0, 350, SCREEN_WIDTH, 100))    # via horizontal

    # linhas de divisão das vias (não desenhar dentro do quadrado do cruzamento)
    for y in range(0, SCREEN_HEIGHT, 40):
        if not 350 < y < 450:
            pygame.draw.rect(screen, COLOR_WHITE, (395, y, 10, 20))
    for x in range(0, SCREEN_WIDTH, 40):
        if not 350 < x < 450:
            pygame.draw.rect(screen, COLOR_WHITE, (x, 395, 20, 10))

    # --- Faixas de pedestre restritas às vias, um pouco antes do cruzamento ---
    # usa a constante global CW_THICKNESS para espessura (agora maior)
    cw_thickness = CW_THICKNESS    # espessura da faixa (altura das listras horizontais)
    stripe_w = 12        # largura de cada listra (aumentei para combinar com a espessura)
    stripe_gap = 7     # espaço entre listras (ajustado)
    stripe_margin = 8    # margem interna dentro da via (para não pintar rente às bordas)
    cw_gap = CW_GAP      # distância da linha de parada/área de stop

    # limites das vias (para garantir faixas só sobre as vias)
    road_x0, road_x1 = 350, 450   # vertical: x-range da via
    road_y0, road_y1 = 350, 450   # horizontal: y-range da via

    # -- Faixas para a via vertical (listras HORIZONTAIS atravessando a via vertical) --
    x_start = road_x0 + stripe_margin
    x_end = road_x1 - stripe_margin

    # norte: antes do cruzamento (para quem vem de cima -> 'down')
    north_y = STOP_DOWN_MIN - cw_gap - cw_thickness
    for x in range(x_start, x_end, stripe_w + stripe_gap):
        pygame.draw.rect(screen, COLOR_WHITE, (x, north_y, stripe_w, cw_thickness))

    # sul: antes do cruzamento (para quem vem de baixo -> 'up')
    south_y = STOP_UP_MIN + cw_gap
    for x in range(x_start, x_end, stripe_w + stripe_gap):
        pygame.draw.rect(screen, COLOR_WHITE, (x, south_y, stripe_w, cw_thickness))

    # -- Faixas para a via horizontal (listras VERTICAIS atravessando a via horizontal) --
    y_start = road_y0 + stripe_margin
    y_end = road_y1 - stripe_margin

    # oeste: antes do cruzamento (para quem vem da esquerda -> 'right')
    left_x = STOP_RIGHT_MIN - cw_gap - cw_thickness
    for y in range(y_start, y_end, stripe_w + stripe_gap):
        pygame.draw.rect(screen, COLOR_WHITE, (left_x, y, cw_thickness, stripe_w))

    # leste: antes do cruzamento (para quem vem da direita -> 'left')
    right_x = STOP_LEFT_MIN + cw_gap
    for y in range(y_start, y_end, stripe_w + stripe_gap):
        pygame.draw.rect(screen, COLOR_WHITE, (right_x, y, cw_thickness, stripe_w))

# Função auxiliar para detectar se um carro está "esperando"
def car_is_waiting(car, all_cars, controller):
    # calcula próximo rect (mesma lógica do update)
    dx = (1 if car.direction == 'right' else -1 if car.direction == 'left' else 0) * car.speed
    dy = (1 if car.direction == 'down' else -1 if car.direction == 'up' else 0) * car.speed
    next_rect = car.rect.move(dx, dy)

    # bloqueio por colisão imediata (outro carro à frente)
    blocked_by_car = False
    for other in all_cars:
        if other is car: continue
        if next_rect.colliderect(other.rect):
            blocked_by_car = True
            break

    # define área de fila (zona mais longa que a linha de parada)
    if car.direction == 'down':
        in_queue = (car.rect.bottom <= STOP_DOWN_MAX) and (car.rect.bottom > STOP_DOWN_MAX - QUEUE_LENGTH)
        light_red = controller.light_v.state != 'green'
    elif car.direction == 'up':
        in_queue = (car.rect.top >= STOP_UP_MIN) and (car.rect.top < STOP_UP_MIN + QUEUE_LENGTH)
        light_red = controller.light_v.state != 'green'
    elif car.direction == 'right':
        in_queue = (car.rect.right <= STOP_RIGHT_MAX) and (car.rect.right > STOP_RIGHT_MAX - QUEUE_LENGTH)
        light_red = controller.light_h.state != 'green'
    else:  # left
        in_queue = (car.rect.left >= STOP_LEFT_MIN) and (car.rect.left < STOP_LEFT_MIN + QUEUE_LENGTH)
        light_red = controller.light_h.state != 'green'

    # conta se está na área de fila e ou o semáforo está vermelho ou está bloqueado por outro carro
    return in_queue and (light_red or blocked_by_car)

# --- FUNÇÃO MAIN() - MODIFICADA ---
def main():
    global total_spawned, PED_BLOCK_V, PED_BLOCK_H
    light_v = TrafficLight(300, 150, 'vertical')
    light_h = TrafficLight(150, 300, 'horizontal')
    controller = TrafficLightController(light_v, light_h)
    all_cars = pygame.sprite.Group()
    all_pedestrians = pygame.sprite.Group()

    # Variáveis para alternar o lado do spawn manual
    horizontal_spawn_side = 'left'  # O próximo carro 'h' virá da esquerda
    vertical_spawn_side = 'top'    # O próximo carro 'v' virá de cima

    # logging CSV: cria arquivo e escreve header se necessário
    write_header = not ARQUIVOS_METRICAS.exists()
    metrics_f = open(ARQUIVOS_METRICAS, "a", newline="", encoding="utf-8")
    metrics_writer = csv.writer(metrics_f)
    if write_header:
        metrics_writer.writerow(["timestamp", "sim_time_s", "cars_alive", "total_spawned", "cars_exited", "waiting_v", "waiting_h", "ped_waiting", "priority"])
        metrics_f.flush()

    sim_time = 0.0
    LOG_INTERVAL = 1.0
    last_log = 0.0

    # ambiente inicial e controle de refresh
    env = generate_random_environment()
    ENV_REFRESH_INTERVAL = 30.0 # Teste com 30 segundos  # segundos (1 minuto) para regenerar variáveis ambientais aleatórias
    last_env_update = 0.0

    # alerta visual quando o ambiente muda
    env_alert_start = None
    ENV_ALERT_DURATION = 3.0  # segundos que o alerta permanece visível
    env_alert_text = ""

    try:
        while True:
            # controla dt e tempo simulado (usado para logging)
            dt_ms = clock.tick(FPS)
            dt = dt_ms / 1000.0
            sim_time += dt

            # atualiza ambiente aleatório periodicamente
            if sim_time - last_env_update >= ENV_REFRESH_INTERVAL:
                new_env = generate_random_environment()
                env = new_env
                last_env_update = sim_time
                # registra alerta para exibição na tela
                env_alert_text = f"Ambiente alterado: {env['clima']} | Carros: {env['car_flow']} | Pedestres: {env['ped_flow']} | Hora: {env['hora']}"
                env_alert_start = sim_time

            # Loop de eventos (apenas QUIT / ESC)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    raise KeyboardInterrupt
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    raise KeyboardInterrupt

            # --- SPAWN AUTOMÁTICO ALEATÓRIO (substitui spawn manual por teclas) ---
            # taxas base (por segundo)
            base_car_spawn_h = 0.6   # base carros por segundo na via horizontal
            base_car_spawn_v = 0.6   # base carros por segundo na via vertical
            base_ped_spawn_each = 0.06  # base probabilidade por segundo por faixa (cada uma das 4)

            # aplica multiplicadores gerados pelo "fluxo" do ambiente
            car_multiplier = CAR_FLOW_MULT.get(env["car_flow"], 1.0)
            ped_multiplier = PED_FLOW_MULT.get(env["ped_flow"], 1.0)

            car_spawn_rate_h = base_car_spawn_h * car_multiplier
            car_spawn_rate_v = base_car_spawn_v * car_multiplier
            ped_spawn_rate_each = base_ped_spawn_each * ped_multiplier

            # carros horizontais (alterna lado de spawn)
            if random.random() < car_spawn_rate_h * dt:
                if horizontal_spawn_side == 'left':
                    c = Car(-40, 370, 'right')  # vem da esquerda
                    horizontal_spawn_side = 'right'
                else:
                    c = Car(SCREEN_WIDTH, 410, 'left')  # vem da direita
                    horizontal_spawn_side = 'left'
                all_cars.add(c)
                total_spawned += 1

            # carros verticais (alterna topo/baixo)
            if random.random() < car_spawn_rate_v * dt:
                if vertical_spawn_side == 'top':
                    c = Car(370, -40, 'down')  # vem de cima
                    vertical_spawn_side = 'bottom'
                else:
                    c = Car(410, SCREEN_HEIGHT, 'up')  # vem de baixo
                    vertical_spawn_side = 'top'
                all_cars.add(c)
                total_spawned += 1

            # pedestres — cada faixa tem sua chance
            if random.random() < ped_spawn_rate_each * dt:
                all_pedestrians.add(Pedestrian('h_n'))
                controller.request_ped_cross('h')
            if random.random() < ped_spawn_rate_each * dt:
                all_pedestrians.add(Pedestrian('h_s'))
                controller.request_ped_cross('h')
            if random.random() < ped_spawn_rate_each * dt:
                all_pedestrians.add(Pedestrian('v_r'))
                controller.request_ped_cross('v')
            if random.random() < ped_spawn_rate_each * dt:
                all_pedestrians.add(Pedestrian('v_l'))
                controller.request_ped_cross('v')

            # --- PERCEPÇÃO DO AGENTE (SENSORES) ---
            # conta carros em fila por eixo
            cars_waiting_v = 0
            cars_waiting_h = 0
            for car in all_cars:
                if car_is_waiting(car, all_cars, controller):
                    if car.direction in ('down', 'up'):
                        cars_waiting_v += 1
                    else:
                        cars_waiting_h += 1

            # atualiza pedestres (decidem iniciar travessia) e conta esperando / atravessando
            ped_waiting_total = 0
            ped_crossing_v = 0  # pedestres atravessando sobre a via vertical (impactam tráfego vertical)
            ped_crossing_h = 0  # pedestres atravessando sobre a via horizontal (impactam tráfego horizontal)

            # atualiza estado dos pedestres (move quem já está crossing)
            for ped in list(all_pedestrians):
                ped.update(light_v, light_h)

            # computa contagens após update
            for ped in all_pedestrians:
                if ped.waiting:
                    ped_waiting_total += 1
                if ped.crossing:
                    if ped.orientation in ('h_n', 'h_s'):
                        ped_crossing_v += 1
                    else:
                        ped_crossing_h += 1

            # atualiza flags globais que bloqueiam carros nas áreas de fila
            PED_BLOCK_V = ped_crossing_v
            PED_BLOCK_H = ped_crossing_h

            # atualiza controlador com as contagens de carros esperando
            controller.update(cars_waiting_v, cars_waiting_h, env=env, ped_waiting_total=ped_waiting_total)

            # --- Atualiza movimento dos carros (depois de avaliar bloqueios por pedestres) ---
            all_cars.update(all_cars, light_v, light_h)

            # --- DESENHO ---
            draw_environment()
            all_cars.draw(screen)
            all_pedestrians.draw(screen)
            light_v.draw()
            light_h.draw()

            # textos informativos
            info_v = font.render(f"Carros esperando na Vertical: {cars_waiting_v}", True, COLOR_BLACK)
            info_h = font.render(f"Carros esperando na Horizontal: {cars_waiting_h}", True, COLOR_BLACK)
            ped_info = font.render(f"Pedestres esperando: {ped_waiting_total} | atravessando V:{ped_crossing_v} H:{ped_crossing_h}", True, COLOR_BLACK)
            priority_text = font.render(f"Prioridade (Fuzzy): {controller.last_priority_score:.2f}", True, COLOR_BLACK)

            # exibe variáveis aleatórias do ambiente
            env_clima = font.render(f"Clima: {env['clima']}", True, COLOR_BLACK)
            env_carflow = font.render(f"Fluxo Carros: {env['car_flow']}", True, COLOR_BLACK)
            env_pedflow = font.render(f"Fluxo Pedestres: {env['ped_flow']}", True, COLOR_BLACK)
            env_hora = font.render(f"Horário: {env['hora']}", True, COLOR_BLACK)

            screen.blit(info_v, (10, 10))
            screen.blit(info_h, (10, 35))
            screen.blit(ped_info, (10, 60))
            screen.blit(priority_text, (SCREEN_WIDTH // 2 - priority_text.get_width() // 2, 10))

            # posição de exibição das variáveis ambientais (canto superior direito)
            x_off = SCREEN_WIDTH - 10
            screen.blit(env_clima, (x_off - env_clima.get_width(), 10))
            screen.blit(env_carflow, (x_off - env_carflow.get_width(), 10 + env_clima.get_height() + 4))
            screen.blit(env_pedflow, (x_off - env_pedflow.get_width(), 10 + env_clima.get_height() + env_carflow.get_height() + 8))
            screen.blit(env_hora, (x_off - env_hora.get_width(), 10 + env_clima.get_height() + env_carflow.get_height() + env_pedflow.get_height() + 12))

            # --- Desenha alerta de alteração de ambiente (se ativo) ---
            if env_alert_start is not None:
                elapsed = sim_time - env_alert_start
                if elapsed <= ENV_ALERT_DURATION:
                    # quebra o texto em linhas para evitar overflow
                    wrap_width = 56
                    lines = textwrap.wrap(env_alert_text, wrap_width)
                    # calcula dimensões do overlay conforme o maior texto
                    overlay_w = max((font.size(line)[0] for line in lines), default=200) + 40
                    overlay_h = len(lines) * font.get_linesize() + 24
                    overlay_s = pygame.Surface((overlay_w, overlay_h), pygame.SRCALPHA)
                    overlay_s.fill((20, 20, 20, 220))  # fundo escuro translúcido
                    ox = SCREEN_WIDTH // 2 - overlay_w // 2
                    oy = 80
                    screen.blit(overlay_s, (ox, oy))
                    # desenha linhas centradas
                    for i, line in enumerate(lines):
                        line_surf = font.render(line, True, (255, 255, 255))
                        screen.blit(line_surf, (SCREEN_WIDTH // 2 - line_surf.get_width() // 2, oy + 12 + i * font.get_linesize()))
                else:
                    env_alert_start = None

            pygame.display.flip()

            # grava métricas a cada LOG_INTERVAL segundos
            if sim_time - last_log >= LOG_INTERVAL:
                timestamp = time.time()
                cars_alive = len(all_cars)
                metrics_writer.writerow([timestamp, f"{sim_time:.2f}", cars_alive, total_spawned, cars_exited, cars_waiting_v, cars_waiting_h, ped_waiting_total, f"{controller.last_priority_score:.2f}"])
                metrics_f.flush()
                last_log = sim_time

    except KeyboardInterrupt:
        # encerra limpo
        metrics_f.close()
        pygame.quit()
        sys.exit()

if __name__ == '__main__':
    main()

# --- PEDRESTES ---
class Pedestrian(pygame.sprite.Sprite):
    """
    Pedestre atravessa sobre as faixas; orientations:
     - 'h_n' = faixa superior vertical (U)  -> atravessa horizontalmente (left -> right)
     - 'h_s' = faixa inferior vertical (I)  -> atravessa horizontalmente (left -> right)
     - 'v_r' = faixa direita horizontal (O) -> atravessa verticalmente (top -> bottom)
     - 'v_l' = faixa esquerda horizontal (P)-> atravessa verticalmente (top -> bottom)
    """
    def __init__(self, orientation):
        super().__init__()
        self.orientation = orientation
        self.speed = 1.6
        self.waiting = True
        self.crossing = False

        # limites das vias (para garantir faixas só sobre as vias)
        road_x0, road_x1 = 340, 460   # vertical: x-range da via
        road_y0, road_y1 = 340, 460   # horizontal: y-range da via

        # spawn/target com base nos STOP_* e constantes de faixa
        if orientation == 'h_n':
            y = STOP_DOWN_MIN - CW_GAP - CW_THICKNESS + CW_THICKNESS // 2
            self.pos = pygame.Vector2(road_x0 - 30, y)
            self.target = pygame.Vector2(road_x1 + 30, y)
            size = (10, 16)
        elif orientation == 'h_s':
            y = STOP_UP_MIN + CW_GAP + CW_THICKNESS // 2
            self.pos = pygame.Vector2(road_x0 - 30, y)
            self.target = pygame.Vector2(road_x1 + 30, y)
            size = (10, 16)
        elif orientation == 'v_r':
            x = STOP_LEFT_MIN + CW_GAP + CW_THICKNESS // 2
            self.pos = pygame.Vector2(x, road_y0 - 30)
            self.target = pygame.Vector2(x, road_y1 + 30)
            size = (16, 10)
        else:  # v_l
            x = STOP_RIGHT_MIN - CW_GAP - CW_THICKNESS + CW_THICKNESS // 2
            self.pos = pygame.Vector2(x, road_y0 - 30)
            self.target = pygame.Vector2(x, road_y1 + 30)
            size = (16, 10)

        surf = pygame.Surface(size, pygame.SRCALPHA)
        pygame.draw.ellipse(surf, (240,128,128), surf.get_rect())
        self.image = surf
        self.rect = self.image.get_rect(center=(int(self.pos.x), int(self.pos.y)))

    def update(self, light_v, light_h):
        # decide se pode iniciar travessia: somente quando o tráfego PERPENDICULAR estiver RED
        if self.waiting:
            if self.orientation in ('h_n', 'h_s'):
                # esses atravessam a via vertical -> precisam que light_v seja RED
                if light_v.state == 'red':
                    self.waiting = False
                    self.crossing = True
            else:
                # atravessam a via horizontal -> precisam que light_h seja RED
                if light_h.state == 'red':
                    self.waiting = False
                    self.crossing = True

        if self.crossing:
            # move em direção ao target
            dir_vec = (self.target - self.pos)
            if dir_vec.length() != 0:
                move = dir_vec.normalize() * self.speed
                if move.length() > dir_vec.length():
                    self.pos = self.target
                else:
                    self.pos += move
                self.rect.center = (int(self.pos.x), int(self.pos.y))

            # remove ao terminar travessia
            if (self.pos - self.target).length() < 2:
                self.kill()