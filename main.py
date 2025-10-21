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

# --- INICIALIZAÇÃO DO PYGAME ---
pygame.init()

# --- CONSTANTES ---
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 800
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Simulador de Semáforo com Spawn Manual")

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


# --- CÉREBRO FUZZY (Sem alterações) ---

class FuzzyController:
    """Encapsula toda a configuração e computação da Lógica Fuzzy."""
    def __init__(self):
        self.carros_via_vermelha = ctrl.Antecedent(np.arange(0, 11, 1), 'carros_via_vermelha')
        self.tempo_verde_atual = ctrl.Antecedent(np.arange(0, 21, 1), 'tempo_verde_atual')
        self.prioridade_troca = ctrl.Consequent(np.arange(0, 11, 1), 'prioridade_troca')

        self.carros_via_vermelha.automf(names=['poucos', 'medio', 'muitos'])
        self.tempo_verde_atual['curto'] = fuzz.trimf(self.tempo_verde_atual.universe, [0, 0, 7])
        self.tempo_verde_atual['medio'] = fuzz.trimf(self.tempo_verde_atual.universe, [5, 10, 15])
        self.tempo_verde_atual['longo'] = fuzz.trimf(self.tempo_verde_atual.universe, [12, 20, 20])
        self.prioridade_troca.automf(names=['baixa', 'media', 'alta'])

        regra1 = ctrl.Rule(self.carros_via_vermelha['muitos'] & self.tempo_verde_atual['longo'], self.prioridade_troca['alta'])
        regra2 = ctrl.Rule(self.carros_via_vermelha['muitos'] & self.tempo_verde_atual['medio'], self.prioridade_troca['alta'])
        regra3 = ctrl.Rule(self.carros_via_vermelha['medio'], self.prioridade_troca['media'])
        regra4 = ctrl.Rule(self.carros_via_vermelha['poucos'], self.prioridade_troca['baixa'])
        regra5 = ctrl.Rule(self.tempo_verde_atual['curto'], self.prioridade_troca['baixa'])
        
        self.sistema_controle = ctrl.ControlSystem([regra1, regra2, regra3, regra4, regra5])
        self.simulador = ctrl.ControlSystemSimulation(self.sistema_controle)

    def compute_priority(self, num_carros_vermelha, tempo_verde):
        self.simulador.input['carros_via_vermelha'] = num_carros_vermelha
        self.simulador.input['tempo_verde_atual'] = tempo_verde
        self.simulador.compute()
        return self.simulador.output['prioridade_troca']


# --- CLASSES DA SIMULAÇÃO (Sem alterações) ---
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
        can_move = True
        # calcula deslocamento
        dx = (1 if self.direction == 'right' else -1 if self.direction == 'left' else 0) * self.speed
        dy = (1 if self.direction == 'down' else -1 if self.direction == 'up' else 0) * self.speed

        # checa semáforo na zona de parada (usar faixas mais largas e inclusive)
        if self.direction == 'down' and traffic_light_v.state != 'green' and STOP_DOWN_MIN < self.rect.bottom <= STOP_DOWN_MAX:
            can_move = False
        if self.direction == 'up' and traffic_light_v.state != 'green' and STOP_UP_MIN <= self.rect.top < STOP_UP_MAX:
            can_move = False
        if self.direction == 'right' and traffic_light_h.state != 'green' and STOP_RIGHT_MIN < self.rect.right <= STOP_RIGHT_MAX:
            can_move = False
        if self.direction == 'left' and traffic_light_h.state != 'green' and STOP_LEFT_MIN <= self.rect.left < STOP_LEFT_MAX:
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
            self.kill()

# --- AGENTE INTELIGENTE (Sem alterações) ---
class TrafficLightController:
    def __init__(self, light_v, light_h):
        self.light_v = light_v
        self.light_h = light_h
        self.fuzzy_brain = FuzzyController()
        self.light_v.state = 'red'
        self.light_h.state = 'green'
        self.timer = 0
        self.change_sequence = None
        self.last_priority_score = 0
        self.YELLOW_TIME = 2 * FPS
    def update(self, cars_v, cars_h):
        # incrementa timer (frames desde início do verde)
        self.timer += 1
        
        # se estiver na sequência de amarelo espera terminar antes de trocar
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
        
        # calcula prioridade usando o cérebro fuzzy
        carros_na_vermelha = cars_v if self.light_h.state == 'green' else cars_h
        tempo_verde_segundos = self.timer / FPS
        priority = self.fuzzy_brain.compute_priority(carros_na_vermelha, tempo_verde_segundos)
        self.last_priority_score = float(priority)
        
        # threshold reduzido para 5.0 (ajustável)
        if priority >= 5.0:
            if self.light_h.state == 'green':
                self.light_h.state = 'yellow'
                self.change_sequence = 'to_v'
            else:
                self.light_v.state = 'yellow'
                self.change_sequence = 'to_h'
            self.timer = 0
        
        # debug (remova ou comente depois)
        # imprime quando prioridade elevada ou a cada 100 frames
        if priority >= 5.0 or self.timer % (FPS * 5) == 0:
            print(f"[DEBUG] red_wait={carros_na_vermelha} tempo_verde={tempo_verde_segundos:.1f}s prior={priority:.2f} estados(v={self.light_v.state}, h={self.light_h.state})")

def draw_environment():
    screen.fill(COLOR_GRAY)
    pygame.draw.rect(screen, COLOR_DARK_GRAY, (350, 0, 100, 800))
    pygame.draw.rect(screen, COLOR_DARK_GRAY, (0, 350, 800, 100))
    for y in range(0, 800, 40):
        if not 350 < y < 450: pygame.draw.rect(screen, COLOR_WHITE, (395, y, 10, 20))
    for x in range(0, 800, 40):
        if not 350 < x < 450: pygame.draw.rect(screen, COLOR_WHITE, (x, 395, 20, 10))


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
    light_v = TrafficLight(300, 150, 'vertical')
    light_h = TrafficLight(150, 300, 'horizontal')
    controller = TrafficLightController(light_v, light_h)
    all_cars = pygame.sprite.Group()

    # Variáveis para alternar o lado do spawn manual
    horizontal_spawn_side = 'left'  # O próximo carro 'h' virá da esquerda
    vertical_spawn_side = 'top'    # O próximo carro 'v' virá de cima

    while True:
        # Loop de eventos para capturar pressionamento de teclas
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            
            # DETECÇÃO DE TECLAS PARA SPAWN MANUAL
            if event.type == pygame.KEYDOWN:
                # Pressionou 'h' para carro Horizontal
                if event.key == pygame.K_h:
                    if horizontal_spawn_side == 'left':
                        all_cars.add(Car(-40, 370, 'right')) # Vem da esquerda
                        horizontal_spawn_side = 'right'      # O próximo virá da direita
                    else:
                        all_cars.add(Car(SCREEN_WIDTH, 410, 'left')) # Vem da direita
                        horizontal_spawn_side = 'left'               # O próximo virá da esquerda
                
                # Pressionou 'v' para carro Vertical
                if event.key == pygame.K_v:
                    if vertical_spawn_side == 'top':
                        all_cars.add(Car(370, -40, 'down')) # Vem de cima
                        vertical_spawn_side = 'bottom'     # O próximo virá de baixo
                    else:
                        all_cars.add(Car(410, SCREEN_HEIGHT, 'up')) # Vem de baixo
                        vertical_spawn_side = 'top'                 # O próximo virá de cima
        
        # --- PERCEPÇÃO DO AGENTE (SENSORES) - CÓDIGO CORRIGIDO ---
        cars_waiting_v = 0
        cars_waiting_h = 0
        for car in all_cars:
            if car_is_waiting(car, all_cars, controller):
                if car.direction in ('down', 'up'):
                    cars_waiting_v += 1
                else:
                    cars_waiting_h += 1
        
        controller.update(cars_waiting_v, cars_waiting_h)
        all_cars.update(all_cars, light_v, light_h)

        draw_environment()
        all_cars.draw(screen)
        light_v.draw()
        light_h.draw()
        controller.light_v.draw()
        controller.light_h.draw()
        
        info_v = font.render(f"Carros esperando na Vertical: {cars_waiting_v}", True, COLOR_BLACK)
        info_h = font.render(f"Carros esperando na Horizontal: {cars_waiting_h}", True, COLOR_BLACK)
        priority_text = font.render(f"Prioridade de Troca (Fuzzy): {controller.last_priority_score:.2f}", True, COLOR_BLACK, COLOR_WHITE)
        controls_text = font.render("Use 'H' para inserir carros na horizontal e 'V' para adicionar carros na vertical", True, COLOR_BLACK, COLOR_WHITE)
        screen.blit(info_v, (10, 10))
        screen.blit(info_h, (10, 35))
        screen.blit(priority_text, (SCREEN_WIDTH // 2 - priority_text.get_width() // 2, 10))
        screen.blit(controls_text, (SCREEN_WIDTH // 2 - controls_text.get_width() // 2, SCREEN_HEIGHT - 40))


        pygame.display.flip()
        clock.tick(FPS)

if __name__ == '__main__':
    main()