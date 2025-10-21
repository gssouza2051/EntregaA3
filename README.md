# Simulador de Semáforo com Spawn Manual

Descrição
---------
Simulador 2D (pygame) de um cruzamento controlado por um controlador Fuzzy (scikit-fuzzy). Dois eixos lógicos (vertical e horizontal) controlam semáforos visuais; carros podem ser spawnados manualmente nas duas direções.

Como funciona (resumo)
----------------------
- Carros são sprites que se movem em linhas retas (up/down/left/right).  
- O controlador Fuzzy (classe `FuzzyController`) recebe:
  - número de carros esperando na via vermelha, e
  - tempo atual do verde (em segundos).
  - retorna uma "prioridade de troca" que o `TrafficLightController` usa para iniciar a sequência amarelo→troca.  
- A detecção de carros "esperando" considera uma área de fila (constante `QUEUE_LENGTH`) e bloqueio por colisão com o carro da frente.  
- Visual: ruas, faixas, semáforos e carros com desenho melhorado (classe `TrafficLight` e `Car`).

Controles
---------
- H: adiciona um carro na via horizontal (alternando esquerda/direita).  
- V: adiciona um carro na via vertical (alternando cima/baixo).  
- ESC / fechar janela: encerra.

Requisitos
----------
- Python 3.11 recomendado (algumas bibliotecas podem falhar em Python 3.12/3.13 devido a módulos legados).  
- Dependências: pygame, scikit-fuzzy, numpy

Instalação e execução (Windows)
-------------------------------
1. Abrir terminal na pasta do projeto:
   cd "EntregaA3"

2. Criar e ativar venv:
   - python -m venv .venv
   - PowerShell: .\.venv\Scripts\Activate.ps1
   - CMD: .venv\Scripts\activate

3. Instalar dependências:
   python -m pip install --upgrade pip setuptools wheel
   python -m pip install pygame scikit-fuzzy numpy

4. Rodar:
   python main.py

Observações e ajustes úteis
--------------------------
- Parâmetros relevantes no código:
  - STOP_* (zonas de parada), QUEUE_LENGTH (tamanho da fila visual),
  - FPS, MIN_GREEN / MAX_GREEN (se presentes), PRIORITY_THRESHOLD (limiar de troca fuzzy).  
  Ajuste esses valores conforme o comportamento observado.

- Se aparecerem erros como "No module named 'imp'" ou "No module named 'distutils'", recomende-se recriar a venv usando Python 3.11.

- Para remover a mensagem do pygame e warnings do pkg_resources, já estão aplicadas no topo do `main.py`:
  - os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
  - warnings.filterwarnings(...)

Arquitetura (rápido)
--------------------
- main.py:
  - Classes principais: `FuzzyController`, `TrafficLight`, `Car`, `TrafficLightController`.
  - `main()` contém loop principal: eventos → percepção (contagem de filas) → update controlador → update sprites → desenho → tick.

Contribuições / melhorias sugeridas
----------------------------------
- múltiplas faixas (lanes), curvas para left/right turns, tipos de veículo diferentes, chegada Poisson, semáforos para pedestres, UI para ajustar parâmetros em tempo real, gravação de métricas (CSV/plots).

Licença
-------
Uso acadêmico / pessoal. Ajuste conforme necessário.
