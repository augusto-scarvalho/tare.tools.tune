"""The teacher's corpus for the Portuguese voice banks (tools/build_speech.py).

60 calibration sentences (tools/teacher_calibration.py), 180 written ones, and the rest from a small grammar of game
dialogue: deterministic, phonetically varied. None of tools/intelligibility.py's test sentences.
"""
import random
import re

SUJ_M = ["o cavaleiro", "o velho mago", "o ferreiro", "o capitão", "o rei", "o mercador", "o caçador", "o bardo",
         "o guarda da ponte", "o menino", "o pescador", "o padre", "o ladrão", "o dragão", "o lobo cinzento",
         "o gigante", "o alquimista", "o príncipe", "o lenhador", "o monge", "o pirata", "o soldado", "o anão",
         "o feiticeiro", "o prefeito", "o fazendeiro", "o carteiro", "o estalajadeiro", "o mendigo", "o general"]
SUJ_F = ["a rainha", "a feiticeira", "a menina", "a curandeira", "a capitã", "a princesa", "a caçadora",
         "a padeira", "a bruxa", "a elfa", "a guerreira", "a taberneira", "a sacerdotisa", "a costureira",
         "a pastora", "a cozinheira", "a professora", "a cigana", "a ferreira", "a arqueira"]
OBJ = ["a espada", "o escudo", "a chave dourada", "o mapa antigo", "a poção azul", "o livro proibido",
       "a coroa", "o anel de prata", "a lanterna", "o machado", "a flauta", "o colar de pérolas", "a carta",
       "o baú", "a tocha", "o arco", "as flechas", "os cristais", "o ovo de dragão", "a armadura", "o pergaminho",
       "o queijo", "o vinho", "o pão quente", "a carroça", "o cavalo", "as moedas", "o tesouro", "a bússola",
       "o cajado", "a capa vermelha", "o elmo", "a corda", "o barco", "a lança", "o tambor", "a harpa",
       "o relógio quebrado", "a semente mágica", "o espelho", "a máscara", "o sino", "a vela", "o martelo"]
LUGAR = ["na floresta", "no castelo", "na caverna", "perto do rio", "no mercado", "na torre", "no porto",
         "atrás da cachoeira", "no fundo do lago", "na taverna", "na praça", "no deserto", "na montanha",
         "debaixo da ponte", "no cemitério", "na biblioteca", "no moinho", "na aldeia", "no pântano",
         "na ilha", "no templo", "na fazenda", "no acampamento", "na estrada do norte", "no jardim do palácio",
         "na mina abandonada", "no vale", "na fronteira", "no navio", "na prisão"]
T_PASS = ["ontem à noite", "hoje cedo", "na semana passada", "durante a tempestade", "depois da batalha",
          "no inverno passado", "há muitos anos", "anteontem", "ao amanhecer", "logo depois do jantar"]
T_FUT = ["amanhã", "antes do anoitecer", "quando a lua subir", "daqui a três dias", "no próximo verão",
         "depois do festival", "ao meio-dia", "logo mais", "na lua cheia", "assim que puder"]
NEG = ["Não toque em", "Não venda", "Não esconda", "Não abra", "Não quebre", "Não leve", "Não use", "Não perca",
       "Não esqueça", "Não jogue fora"]
V_PASS = ["encontrou", "perdeu", "escondeu", "roubou", "quebrou", "vendeu", "comprou", "levou", "trouxe",
          "consertou", "guardou", "jogou", "achou", "deixou", "procurou", "protegeu", "abriu", "fechou",
          "pintou", "carregou", "esqueceu", "limpou", "enterrou", "trocou", "pegou", "segurou", "desenhou"]
V_INF = ["buscar", "proteger", "vender", "esconder", "consertar", "levar", "encontrar", "destruir", "limpar",
         "trocar", "devolver", "carregar", "abrir", "guardar", "usar", "experimentar", "examinar", "polir"]
V_PRES = ["mora", "trabalha", "dorme", "canta", "espera", "descansa", "treina", "reza", "pesca", "cozinha",
          "estuda", "vigia", "se esconde", "vive", "dança", "caça"]
ADJ = ["perigoso", "estranho", "lindo", "enorme", "antigo", "pesado", "barulhento", "assustador", "brilhante",
       "frio", "escuro", "tranquilo", "mágico", "esquisito", "valioso", "silencioso"]
PLURAL = ["poções", "flechas", "moedas", "ervas", "pedras", "maçãs", "velas", "cogumelos", "pergaminhos",
          "escudos", "sacos de trigo", "garrafas", "cristais", "penas de grifo", "peles de lobo"]
NUM = ["duas", "três", "quatro", "cinco", "seis", "sete", "oito", "nove", "dez", "doze", "vinte", "trinta",
       "quarenta", "cem"]
VOC = ["viajante", "amigo", "senhor", "senhora", "minha filha", "meu jovem", "companheiro", "majestade",
       "aventureiro", "forasteiro"]
INTERJ = ["Olha só", "Puxa", "Escuta", "Ei", "Nossa", "Ah", "Bom", "Calma", "Veja", "Hmm"]


def sentences(n: int, seed: int = 7) -> list[str]:
    r = random.Random(seed)

    def suj():
        return r.choice(SUJ_M + SUJ_F)

    def cap(s):
        return s[0].upper() + s[1:]

    templates = [
        lambda: f"{cap(suj())} {r.choice(V_PASS)} {r.choice(OBJ)} {r.choice(LUGAR)}.",
        lambda: f"{cap(suj())} vai {r.choice(V_INF)} {r.choice(OBJ)} {r.choice(T_FUT)}.",
        lambda: f"Você {r.choice(V_PASS)} {r.choice(OBJ)} {r.choice(LUGAR)}?",
        lambda: f"Quem {r.choice(V_PASS)} {r.choice(OBJ)}?",
        lambda: f"Onde {suj()} {r.choice(V_PRES)}?",
        lambda: f"Por que {suj()} {r.choice(V_PASS)} {r.choice(OBJ)}?",
        lambda: f"Cuidado com {r.choice(OBJ)}, {r.choice(VOC)}!",
        lambda: f"{r.choice(INTERJ)}, {suj()} {r.choice(V_PRES)} {r.choice(LUGAR)}.",
        lambda: f"Preciso de {r.choice(NUM)} {r.choice(PLURAL)} {r.choice(T_FUT)}.",
        lambda: f"Se você {r.choice(['quiser', 'puder', 'conseguir'])} {r.choice(V_INF)} {r.choice(OBJ)}, "
                f"{suj()} vai ficar feliz.",
        lambda: f"Bom dia, {r.choice(VOC)}! {cap(suj())} {r.choice(V_PRES)} {r.choice(LUGAR)}.",
        lambda: f"Esse lugar é muito {r.choice(ADJ)}, {r.choice(VOC)}.",
        lambda: f"{cap(r.choice(OBJ))} está {r.choice(LUGAR)}, não está?",
        lambda: f"Ninguém sabe quem {r.choice(V_PASS)} {r.choice(OBJ)} {r.choice(T_PASS)}.",
        lambda: f"Quanto custa {r.choice(OBJ)}?",
        lambda: f"Que {r.choice(ADJ)}! Nunca vi nada assim {r.choice(LUGAR)}.",
        lambda: f"{cap(suj())} me contou que {suj()} {r.choice(V_PASS)} {r.choice(OBJ)}.",
        lambda: f"Traga {r.choice(NUM)} {r.choice(PLURAL)} e {r.choice(OBJ)}, por favor.",
        lambda: f"{r.choice(NEG)} {r.choice(OBJ)} sem falar comigo!",
        lambda: f"{r.choice(INTERJ)}! {cap(r.choice(OBJ))} sumiu {r.choice(T_PASS)}.",
    ]
    out, seen = [], set()
    while len(out) < n:
        s = re.sub(r"\bem (o|a|os|as)\b", lambda m: "n" + m.group(1), r.choice(templates)())
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


EXTRA_PT = [
    "Bom dia, senhor! O que deseja comprar hoje?", "As maçãs vermelhas custam duas moedas cada.",
    "O capitão mandou fechar os portões da cidade.", "Minha mãe sempre dizia para ter coragem.",
    "Os irmãos trabalham juntos na fazenda do avô.", "Ninguém volta vivo daquela torre maldita.",
    "Esse pergaminho fala de um tesouro escondido.", "A lenda diz que o herói voltará um dia.",
    "Atravesse o rio pela ponte de pedra.", "Os lobos uivam quando a lua aparece.",
    "Compre três flechas e um arco novo.", "O alquimista transformou chumbo em prata.",
    "Por que você está tão preocupado?", "Eles fugiram antes do amanhecer.",
    "O velho sábio mora no alto da colina.", "Guarde bem esta pedra brilhante.",
    "As crianças brincam na praça principal.", "O trem chegou atrasado à estação.",
    "Quantos dragões você já derrotou?", "Ele quebrou o braço lutando contra o troll.",
    "Já está na hora de partir, amigos.", "A floresta proibida fica ao sul do vilarejo.",
    "O cozinheiro preparou uma sopa de legumes.", "Ela perdeu o colar de pérolas no jardim.",
    "Não confie no mercador de olhos verdes.", "O inverno chegou cedo neste ano.",
    "Os guardas trocam de turno à meia-noite.", "Precisamos atravessar o deserto em dois dias.",
    "O monstro dorme no fundo do lago gelado.", "Que bom ver você de novo, minha filha!",
    "Ouvi dizer que o rei ficou doente.", "A biblioteca guarda livros muito raros.",
    "O sacerdote abençoou as armas dos soldados.", "Dez cavaleiros partiram, só um voltou.",
    "A cigana leu a minha sorte nas cartas.", "Cuidado com as armadilhas no corredor.",
    "O ouro do reino desapareceu do cofre.", "Quero um quarto para passar a noite.",
    "O vulcão acordou depois de cem anos.", "Os anões cavam túneis debaixo da montanha.",
    "A elfa atirou uma flecha certeira.", "Traga lenha seca para a fogueira.",
    "O barqueiro cobra uma moeda de prata.", "Escondi o mapa embaixo da cama.",
    "Ele jurou proteger a princesa para sempre.", "Ganhei esta cicatriz numa batalha antiga.",
    "Vocês ouviram aquele grito na floresta?", "Siga a trilha até encontrar o moinho velho.",
    "O pão de hoje saiu quentinho do forno.", "As velas iluminam o salão do trono.",
    "A tropa marchou durante a noite inteira.", "Um corvo negro pousou na janela.",
    "A espada mágica brilha perto dos inimigos.", "Bebam água fresca da fonte sagrada.",
    "O bardo cantou uma canção muito triste.", "Ela tem medo de aranhas gigantes.",
    "A ilha dos piratas aparece no nevoeiro.", "O príncipe chegou montado num cavalo branco.",
    "Desculpe, mas a loja já está fechada.", "Quem roubou as joias da coroa?",
    "Os sinos tocam quando alguém se casa.", "O caçador seguiu as pegadas do urso.",
    "Ainda falta muito para chegar à capital?", "Vamos dividir o tesouro em partes iguais.",
    "A magia do gelo congela qualquer inimigo.", "O mestre ensinou o golpe secreto.",
    "Meus pés doem depois de tanto andar.", "Nunca vi uma tempestade tão forte.",
    "As joaninhas vivem perto das flores.", "O feiticeiro lançou uma maldição terrível.",
    "Sente-se perto do fogo e descanse.", "Há um portal escondido atrás da cachoeira.",
    "Os mineiros encontraram cristais azuis.", "Meu escudo rachou com o último golpe.",
    "A taberneira serve vinho e cerveja.", "O exército inimigo cercou o castelo.",
    "Leia o livro antes de usar a varinha.", "A estátua de bronze parece se mover.",
    "O nevoeiro esconde o caminho da serra.", "Fique quieto, os guardas estão chegando.",
    "Os peixes pulam no rio ao entardecer.", "Ele tropeçou e caiu na lama.",
    "Uma serpente enorme saiu da gruta.", "O prefeito prometeu reconstruir a muralha.",
    "Tenho uma missão importante para você.", "A cura custa vinte peças de ouro.",
    "Lembre-se de mim quando estiver longe.", "O dia está lindo para viajar.",
    "Os gnomos consertam relógios quebrados.", "A neve cobriu todas as estradas.",
    "Encontre o cristal e traga-o para mim.", "O jovem ferreiro sonha em ser cavaleiro.",
    "As abóboras cresceram muito este ano.", "O fantasma assombra o porão da casa.",
    "Pegue o machado e corte aquela corda.", "Quem é você e o que faz aqui?",
    "O navio pirata afundou perto dos recifes.", "A velha rainha guarda um segredo.",
    "Os camponeses pediram ajuda ao conselho.", "O céu ficou vermelho antes da guerra.",
    "Tome cuidado com o chefe dos bandidos.", "Ele aprendeu a ler com o monge.",
    "As ruínas antigas escondem passagens.", "O cachorro latiu a noite toda.",
    "Uma chave dourada abre a porta norte.", "A guilda dos ladrões tem novos membros.",
    "Os pássaros cantam no alto das árvores.", "Esse queijo tem um cheiro muito forte.",
    "O gelo da caverna nunca derrete.", "A carroça quebrou no meio da estrada.",
    "Conte-me tudo o que aconteceu ontem.", "O dragão vermelho cospe fogo e fumaça.",
    "Minha espada precisa de uma lâmina nova.", "Ela nasceu numa aldeia de pescadores.",
    "Os cogumelos azuis são venenosos.", "O torneio começa amanhã ao meio-dia.",
    "A ponte levadiça está emperrada.", "Não toque nesse ovo de dragão!",
    "O general planeja atacar ao amanhecer.", "A poção vermelha recupera a energia.",
    "Um gigante bloqueia a passagem do vale.", "As montanhas brilham sob o sol da manhã.",
    "Ele vendeu a fazenda para pagar dívidas.", "Os ventos do norte trazem chuva.",
    "A feiticeira mora numa torre de cristal.", "Preciso de um guia para atravessar o pântano.",
    "As crianças contam histórias de assombração.", "O padre acendeu as velas do altar.",
    "Lutamos juntos contra o exército das sombras.", "Que tal uma partida de xadrez?",
    "A maré sobe muito rápido nesta praia.", "O lenço bordado era da minha avó.",
    "Um cavaleiro sem cabeça cavalga à noite.", "O sapateiro consertou as minhas botas.",
    "A chama azul indica magia antiga.", "Ela canta melhor do que qualquer bardo.",
    "Os orcs destruíram a ponte do rio.", "O médico receitou chá de gengibre.",
    "A coroa pertence ao herdeiro legítimo.", "Ouço passos vindo do corredor escuro.",
    "Bem que eu avisei sobre aquele lugar.", "O moleiro mói o trigo todas as manhãs.",
    "Seu nome está escrito no livro antigo.", "Os mercenários exigem pagamento adiantado.",
    "O jardim do palácio tem rosas negras.", "Ninguém consegue abrir aquele baú.",
    "Volte quando tiver dinheiro suficiente.", "A estrela cadente caiu perto daqui.",
    "Ele guarda rancor desde a infância.", "A neblina sobe do pântano ao anoitecer.",
    "O rato roeu a roupa do rei de Roma.", "Três pratos de trigo para três tigres tristes.",
    "O sabiá sabia assobiar.", "A aranha arranha a jarra.",
    "Lhama, ilha, palha, olho, filho, velho.", "Banho, sonho, ninho, linha, vinho, caminho.",
    "Pão, mão, cão, chão, irmão, coração.", "Mãe, pães, cães, alemães, capitães.",
    "Põe, leões, dragões, botões, canções.", "Sim, fim, jardim, ruim, assim.",
    "Um, algum, nenhum, comum, atum.", "Bem, tem, também, ninguém, alguém.",
    "Tio, tia, dia, diabo, tipo, divino.", "Leite, noite, parte, verde, tarde.",
    "Carro, terra, ferro, guerra, morro.", "Rato, rosa, rua, rede, rio, rei.",
    "Mar, amor, calor, flor, cantar, partir.", "Sal, mel, sol, azul, papel, anel.",
    "Gato, gente, guerra, gigante, gostar.", "Casa, mesa, rosa, coisa, pesado.",
    "Chave, chuva, peixe, caixa, xícara.", "Janela, jogo, gelo, hoje, viagem.",
    "Prato, preto, primo, prova, pluma.", "Braço, branco, bruxa, blusa, bloco.",
    "Trono, trigo, trevo, atlas, atleta.", "Dragão, drama, cravo, crime, clima.",
    "Grito, grande, gruta, globo, glória.", "Fraco, frio, fruta, flecha, floresta.",
    "Vrum, livro, palavra, nevrálgico.", "Ótimo, ótica, órfão, ópera, ônibus.",
]
