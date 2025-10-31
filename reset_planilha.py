import tkinter as tk
from tkinter import messagebox
import os

def verificar_e_resetar_planilha():
    """
    Abre um modal de confirmação para o usuário. Se o usuário clicar em 'Sim',
    a função tentará excluir o arquivo 'metrics.csv'.
    """
    # Nome do arquivo que queremos gerenciar
    nome_arquivo = 'metrics.csv'
    
    # É necessário criar uma janela raiz do Tkinter, mas podemos ocultá-la
    # para que apenas o modal de diálogo apareça.
    root = tk.Tk()
    root.withdraw()  # Oculta a janela principal

    # Exibe a caixa de diálogo com a pergunta "Sim" ou "Não"
    # A função askyesno retorna True para 'Sim' e False para 'Não'
    resposta = messagebox.askyesno(
        title="Confirmar Reset",
        message=f"Deseja realmente resetar a planilha '{nome_arquivo}'?\n\nEsta ação não pode ser desfeita."
    )

    # Verifica a resposta do usuário
    if resposta:
        # Se a resposta for 'Sim' (True), prossiga com a exclusão
        try:
            # Verifica se o arquivo realmente existe antes de tentar excluí-lo
            if os.path.exists(nome_arquivo):
                os.remove(nome_arquivo)
                print(f"A planilha '{nome_arquivo}' foi resetada com sucesso (excluída).")
                # Opcional: mostrar um pop-up de sucesso
                messagebox.showinfo("Sucesso", f"A planilha '{nome_arquivo}' foi excluída.")
            else:
                print(f"A planilha '{nome_arquivo}' não foi encontrada. Nenhuma ação foi tomada.")
                # Opcional: mostrar um pop-up de aviso
                messagebox.showwarning("Aviso", f"A planilha '{nome_arquivo}' não foi encontrada.")

        except OSError as e:
            # Captura outros possíveis erros do sistema operacional (ex: falta de permissão)
            print(f"Erro ao tentar excluir o arquivo: {e}")
            messagebox.showerror("Erro", f"Não foi possível excluir o arquivo.\nErro: {e}")
    else:
        # Se a resposta for 'Não' (False), apenas informe o usuário
        print("Operação cancelada pelo usuário.")

