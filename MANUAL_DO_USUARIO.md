# Manual do Usuário — VideoFactoryAI

Este documento segue a norma técnica simplificada ASD-STE100.
Ele contém instruções curtas, diretas e fáceis de entender.

---

## 1. Descrição do Sistema

O VideoFactoryAI é um produtor automático de vídeos documentários em alta resolução (1080p).
O sistema pesquisa fatos, escreve roteiros, gera narração por voz e adiciona legendas sincronizadas.
Ele também busca mídias livres de direitos autorais e renderiza o vídeo final.

---

## 2. Requisitos Básicos

Antes de começar, confirme estes itens:
- Computador com sistema Windows 10 ou Windows 11.
- Conexão ativa com a internet.
- Python versão 3.10 ou superior instalado.

---

## 3. Instalação em Um Clique

Siga estes passos para instalar o sistema:

1. Abra a pasta principal do projeto: `C:\Projeto_Ira_EUA`.
2. Dê um clique duplo no arquivo `install.bat`.
3. Aguarde a conclusão da instalação automática.
4. O instalador baixa todas as bibliotecas necessárias.
5. Ele também verifica o programa FFmpeg e a placa de vídeo.
6. Quando a mensagem `[OK] Pronto` aparecer, pressione qualquer tecla para fechar a janela.

---

## 4. Como Usar o Sistema

Você pode usar o VideoFactoryAI de duas maneiras diferentes.

### Modo A: Você já tem um roteiro escrito

Use este modo quando você tiver um arquivo de texto com o seu roteiro.

1. Salve o seu texto no arquivo `roteiro.txt` na pasta do programa.
2. Abra o terminal de comando (PowerShell ou Prompt de Comando).
3. Vá para a pasta do projeto:
   ```cmd
   cd C:\Projeto_Ira_EUA
   ```
4. Execute o comando:
   ```cmd
   python VideoFactoryAI/agent.py roteiro.txt
   ```
5. Aguarde o término do processo.

---

### Modo B: Você não tem um roteiro (Modo Produtor Completo)

O sistema pesquisa o tema na enciclopédia, escreve o roteiro e gera o vídeo completo.

1. Abra o terminal na pasta do projeto.
2. Execute o comando abaixo, substituindo o tema e a duração:
   ```cmd
   python VideoFactoryAI/agent.py --topic "A Guerra Fria" --duration 8
   ```
3. O parâmetro `--topic` define o assunto do documentário.
4. O parâmetro `--duration` define o tempo do vídeo em minutos.
5. O sistema salva o roteiro em `roteiros/` e produz o vídeo automaticamente.

---

## 5. Seleção de Canal e Estilo Visual

Você pode escolher o estilo visual e o ritmo do documentário.
Adicione o parâmetro `--channel` ao seu comando.

| Opção de Canal | Estilo e Ritmo | Tipo de Voz |
|---|---|---|
| `--channel documentario` | Estilo jornalístico e solene | Voz masculina grave |
| `--channel geopolitica` | Estilo analítico e ritmo rápido | Voz masculina firme |
| `--channel historia` | Estilo clássico com fotos de época | Voz profunda |
| `--channel tecnologia` | Estilo moderno e dinâmico | Voz feminina clara |

### Exemplo com canal:
```cmd
python VideoFactoryAI/agent.py --topic "A Crise dos Misseis de Cuba" --duration 5 --channel geopolitica
```

---

## 6. Onde Encontrar os Arquivos Finais

Após o término da execução, abra a pasta `saida/`.
Você encontrará os seguintes arquivos prontos:

| Nome do Arquivo | Conteúdo do Arquivo |
|---|---|
| `documentario_final.mp4` | O vídeo final completo em resolução 1080p |
| `thumbnail.jpg` | A imagem de capa com maior contraste visual |
| `thumbnail_v1.jpg` | Opção de capa baseada no início do vídeo |
| `thumbnail_v2.jpg` | Opção de capa baseada no meio do vídeo |
| `thumbnail_v3.jpg` | Opção de capa com desenho tipográfico |
| `youtube_metadata.json` | Título, descrição, etiquetas e capítulos prontos para o YouTube |
| `quality_report.json` | Relatório com os testes de qualidade do vídeo |

---

## 7. Como Retomar uma Produção Interrompida

Se a internet cair ou o computador desligar, você não perde o trabalho feito.
Execute o comando adicionando `--resume`:

```cmd
python VideoFactoryAI/agent.py roteiro.txt --resume
```

O sistema continua do ponto exato onde parou.
Ele não baixa novamente os arquivos que já estão salvos.

---

## 8. Solução de Problemas Comuns

### O comando `python` não é reconhecido
- Reinstale o Python.
- Marque a caixa de seleção `Add python.exe to PATH` durante a instalação.

### O sistema avisa que o FFmpeg não foi encontrado
- Execute o arquivo `install.bat`.
- O instalador baixa e instala o FFmpeg automaticamente.

### O vídeo final não foi gerado
- Abra o arquivo `saida/quality_report.json`.
- Leia a seção `critical`. Ela indica o motivo exato da falha.
