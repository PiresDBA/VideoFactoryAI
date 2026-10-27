# -*- coding: utf-8 -*-
"""Teste do parser do Gem @roteiroparavideos"""

import sys
sys.path.insert(0, r"C:\Fabrica-de-videos\VideoFactoryAI")

from gem_roteiro_parser import parse_gem_output, gem_para_cenas_pipeline, validar_roteiro_gem

# Exemplo real fornecido pelo usuário
texto_exemplo = """Roteiro para Vídeo do YouTube: Coisas Bizarras Sobre a Vida Pessoal de Hitler Que Ninguém Sabia
PARTE 1: ESTRUTURA DE CENAS (VISUAL E EDIÇÃO)
00:00 - 00:30 | Gancho Inicial

[VISUAL]: Imagens de arquivo em preto e branco de Adolf Hitler em discursos inflamados, cortadas rapidamente com efeitos de glitch, transições dramáticas e zoom em detalhes bizarros (como seus olhos e seu bigode). Efeito sonoro de suspense e impacto. Na tela, texto dinâmico em destaque com a fonte de títulos (ex: Oswald ou Bebas Neue): "O DITADOR QUE VOCÊ ACHAVA QUE CONHECIA" na cor secundária (Branco) e detalhes na cor de destaque (Amarelo Vivo/Laranja).

[DURAÇÃO]: 30 segundos

00:30 - 02:00 | Bloco 1: Hábitos Alimentares e Hipocondria Extrema

[VISUAL]: Animação leve ou ilustrações estilo infográfico sobre a dieta vegetariana de Hitler e seu medo obsessivo de câncer. Imagens de arquivo de médicos da época, pílulas misteriosas e frascos de remédios. Legendas dinâmicas centralizadas com fundo contrastante.

[DURAÇÃO]: 1 minuto e 30 segundos

02:00 - 03:30 | Bloco 2: A Obsessão Secreta por Filmes da Disney e Arte

[VISUAL]: Cenas clássicas de animações da Disney dos anos 1930 e 1940 (como Branca de Neve e os Sete Anões e esboços de personagens de Walt Disney). Imagens de arquivos mostrando desenhos em aquarela assinados por Hitler.

[DURAÇÃO]: 1 minuto e 30 segundos

03:30 - 05:00 | Bloco 3: Mania de Limpeza, Hobbies Inusitados e Fobias

[VISUAL]: B-roll de arquivos históricos mostrando interiores de bunkers, mesas organizadas milimetricamente, documentos antigos e imagens de cães da raça Pastor Alemão. Gráficos na tela detalhando as fobias bizarras do ditador.

[DURAÇÃO]: 1 minuto e 30 segundos

05:00 - 05:30 | Chamada para Ação (CTA) e Fechamento

[VISUAL]: Tela final do YouTube com animações de like, botão de inscrição e ícones de redes sociais. O apresentador ou uma locução dinâmica embalada por uma trilha sonora épica encerra o vídeo.

[DURAÇÃO]: 30 segundos

PARTE 2: TEXTO ÚNICO DE NARRAÇÃO (LOCUÇÃO COMPLETA)
Olá , bem vindo ao nosso canal, você sabia que o sabiá sabia assobiar? Quando pensamos na figura de Adolf Hitler, a primeira imagem que vem à mente é a de um dos maiores tiranos da história da humanidade, responsável por atrocidades inimagináveis durante a Segunda Guerra Mundial. No entanto, por trás da fachada fria e calculista do regime nazista, existia uma rotina pessoal repleta de excentricidades, manias bizarras e segredos que a maioria das pessoas simplesmente desconhece. Vamos começar falando sobre a sua alimentação e saúde. Embora o imagine como alguém rigoroso, Hitler desenvolveu uma hipocondria severa ao longo dos anos. Ele sofria de flatulências crônicas terríveis, cólicas estomacais e espasmos intestinais incontroláveis. Para combater esses problemas, ele consumia diariamente um coquetel de mais de vinte medicamentos diferentes, que incluíam desde extratos de fígado e enzimas até substâncias perigosas como anfetaminas e veneno para ratos diluído. Além disso, nos seus últimos anos, tornou-se estritamente vegetariano, não por amor aos animais, mas porque acreditava firmemente que carne em decomposição causava câncer no cólon, e frequentemente aterrorizava seus convidados durante o jantar descrevendo detalhadamente cadáveres de animais em decomposição para tentar convencê-los a parar de comer carne. Outro fato absolutamente surpreendente é a sua obsessão secreta por cultura pop americana, em especial pelas produções da Walt Disney. Hitler era fascinado pelo filme Branca de Neve e os Sete Anões, lançado em 1937, considerando-o uma obra-prima absoluta da animação e da engenharia técnica. Ele guardava cópias do filme em sua residência privada nos Alpes bávaros e assistia a exibições particulares com frequência. Além disso, documentos descobertos após a guerra revelaram que ele mantinha esboços e aquarelas desenhadas por ele mesmo de personagens como a Branca de Neve e os anões, demonstrando um lado artístico frustrado que ele nunca conseguiu conciliar com suas ambições políticas fracassadas da juventude, quando foi rejeitado na Academia de Belas-Artes de Viena. As manias de higiene e limpeza de Hitler também desafiavam qualquer lógica de normalidade. Ele tinha uma fobia extrema de germes e contaminação, o que o levava a lavar as mãos dezenas de vezes ao dia e a recusar-se a apertar a mão de qualquer pessoa sem higienizá-las logo em seguida. Curiosamente, essa ojeriza a germes não se estendia aos seus animais de estimação; ele era extremamente apegado à sua cadela pastor alemão, Blondi, a quem tratava com uma ternura bizarra que jamais demonstrava por seres humanos, chegando a testar pílulas de cianeto nela própria nos últimos dias no bunker para garantir que o veneno funcionasse antes de usá-lo em si mesmo. Para completar, ele sofria de insônia crônica severa, passava noites inteiras acordado revisando mapas militares imaginários ou monologando discursos sem fim para um público vazio, dormindo apenas nas primeiras horas da manhã. Esses detalhes mostram que a mente por trás da máquina de guerra era profundamente instável, marcada por contradições bizarras e transtornos obsessivos que moldaram os bastidores da sua tirania até o fim.

Se você gostou desse conteúdo, deixe seu like, se inscreva no canal e nos siga, assim você fortalece nosso canal e mostra para o youtube que esse conteúdo é relevante, incentivando a gente a criar mais conteúdos como esse. FUI !!"""

print("=" * 80)
print("TESTE DO PARSER DO GEM @roteiroparavideos")
print("=" * 80)

# Parse
roteiro = parse_gem_output(texto_exemplo)

print(f"\n📋 TÍTULO: {roteiro.titulo}")
print(f"🎬 CENAS: {len(roteiro.cenas)}")
print(f"📝 NARRAÇÃO: {len(roteiro.narracao_para_tts.split())} palavras")
print(f"📝 NARRAÇÃO + CTA: {len(roteiro.narracao_completa.split())} palavras")
print(f"⏱️  DURAÇÃO TOTAL: {roteiro.duracao_total_min:.1f} min ({roteiro.duracao_total_seg:.0f} seg)")

print("\n" + "=" * 80)
print("CENAS EXTRAÍDAS:")
print("=" * 80)
for i, cena in enumerate(roteiro.cenas, 1):
    print(f"\n  Cena {i}: {cena.inicio} - {cena.fim} | {cena.titulo}")
    print(f"    Duração: {cena.duracao_seg}s ({cena.duracao_txt})")
    print(f"    Visual: {cena.visual[:80]}...")

print("\n" + "=" * 80)
print("VALIDAÇÃO:")
print("=" * 80)
ok, msg = validar_roteiro_gem(roteiro, min_palavras=100)
print(f"  Resultado: {'✅' if ok else '❌'} {msg}")

print("\n" + "=" * 80)
print("CONVERSÃO PARA PIPELINE:")
print("=" * 80)
cenas_pipeline = gem_para_cenas_pipeline(roteiro, "Coisas Bizarras Sobre Hitler")
print(f"  {len(cenas_pipeline)} cenas convertidas")
for i, cena in enumerate(cenas_pipeline[:3], 1):  # Mostra apenas as 3 primeiras
    print(f"\n  Cena {cena['idx']+1}:")
    print(f"    Texto: {cena['texto'][:80]}...")
    print(f"    Query: {cena['query'][:80]}...")
    print(f"    AI Prompt: {cena['ai_prompt'][:80]}...")
    print(f"    Duração: {cena['duracao']}s")

print("\n" + "=" * 80)
print("✅ TESTE CONCLUÍDO!")
print("=" * 80)
