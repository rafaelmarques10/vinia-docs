# Modelo de custo e margem por cliente do Vinia (valores em R$ por mês)
FX = 5.50                       # R$/US$ (fechamento de 9/11/2026: 5,51)
IN_USD, OUT_USD = 0.15, 0.60    # Groq gpt-oss-120b, US$ por milhão de tokens
FIXO_IN, POR_VINHO, SAIDA = 614, 156, 500   # tokens: parte fixa, por vinho (515 chars), saída (conservador)

def custo_consulta(vinhos, fx=FX, cache=False, atalho=None):
    w = min(vinhos, atalho) if atalho else vinhos
    tin = FIXO_IN + POR_VINHO * w
    cin = tin * IN_USD / 1e6 * (0.5 if cache else 1)
    return (cin + SAIDA * OUT_USD / 1e6) * fx

def gateway(preco):  # Asaas: 64% Pix/boleto R$1,99; 36% cartão 2,99% + R$0,49
    return 0.64 * 1.99 + 0.36 * (0.49 + 0.0299 * preco)

PLANOS = {  # do PDF: preço, cota, suporte (hipótese de horas valorizadas)
    'Início': dict(preco=147, cota=500,  suporte=20),
    'Pro':    dict(preco=297, cota=2000, suporte=30),
    'Rede':   dict(preco=597, cota=6000, suporte=60),
}
print('=== custo por consulta (R$) por tamanho da carta (FX %.2f) ===' % FX)
for w in (11, 60, 100, 200, 300, 500):
    print(f'{w:>4} vinhos: R$ {custo_consulta(w):.4f}   com cache de entrada 50%: R$ {custo_consulta(w, cache=True):.4f}   com atalho de 40 vinhos: R$ {custo_consulta(w, atalho=40):.4f}')

def linha(nome, p, uso, vinhos, imposto, fixo_rateado, fx=FX, atalho=None):
    cons = p['cota'] * uso
    ia = cons * custo_consulta(vinhos, fx, atalho=atalho)
    gw = gateway(p['preco'])
    imp = p['preco'] * imposto
    bruta = p['preco'] - ia - gw - fixo_rateado
    contrib = bruta - imp - p['suporte']
    return ia, gw, imp, bruta / p['preco'], contrib, contrib / p['preco']

print('\n=== margem por plano (imposto 6%%, infra rateada R$ 9 por cliente = ~30 clientes) ===')
print('%-7s %-22s %-8s %8s %8s %8s %9s %9s %9s' % ('plano', 'cenário', 'vinhos', 'IA', 'gateway', 'imposto', 'bruta%', 'contrib.', 'contrib%'))
for nome, p in PLANOS.items():
    for rot, uso, vin in (('uso típico (50% cota)', 0.5, 60), ('cota cheia, carta 100', 1.0, 100), ('cota cheia, carta 300', 1.0, 300), ('cota cheia, carta 500', 1.0, 500)):
        ia, gw, imp, bp, c, cp = linha(nome, p, uso, vin, 0.06, 9)
        print('%-7s %-22s %-8d %8.2f %8.2f %8.2f %8.1f%% %9.2f %8.1f%%' % (nome, rot, vin, ia, gw, imp, bp * 100, c, cp * 100))

print('\n=== com "atalho" (só 40 vinhos pré-filtrados vão no prompt), cota cheia, carta 300 ===')
for nome, p in PLANOS.items():
    ia, gw, imp, bp, c, cp = linha(nome, p, 1.0, 300, 0.06, 9, atalho=40)
    print('%-7s IA R$ %6.2f  bruta %5.1f%%  contribuição R$ %7.2f (%4.1f%%)' % (nome, ia, bp * 100, c, cp * 100))

print('\n=== sensibilidade: câmbio 6,50 e imposto 11,2%, Pro, cota cheia, carta 100 ===')
ia, gw, imp, bp, c, cp = linha('Pro', PLANOS['Pro'], 1.0, 100, 0.112, 9, fx=6.5)
print('Pro  IA R$ %.2f  bruta %.1f%%  contribuição R$ %.2f (%.1f%%)' % (ia, bp * 100, c, cp * 100))

print('\n=== infra fixa (PDF): R$ 75 a 485/mês; ponto de equilíbrio com contribuição típica ===')
for f in (75, 280, 485):
    for nome in ('Início', 'Pro'):
        p = PLANOS[nome]
        ia, gw, imp, bp, c, cp = linha(nome, p, 0.5, 60, 0.06, 0)
        print('fixo R$ %3d | %-6s contribuição típica R$ %6.2f por cliente => %4.1f clientes pagam a infra' % (f, nome, c, f / c))

print('\n=== custo de um trial (14 dias) para teto de consultas ===')
for q in (100, 150, 300):
    print('teto %3d consultas, carta 100: R$ %.2f | com conversão de 25%%, custo por cliente que fecha: R$ %.2f' % (q, q * custo_consulta(100), q * custo_consulta(100) / 0.25))

print('\n=== excedente: preço sugerido por pacote de 500 consultas (margem sobre o custo + gateway + imposto) ===')
for w in (60, 100, 300):
    c = 500 * custo_consulta(w)
    for preco in (29, 49, 79):
        liq = preco - gateway(preco) - preco * 0.06 - c
        print('carta %3d | custo IA R$ %5.2f | pacote R$ %2d => lucro líquido R$ %5.2f (%4.1f%% do preço)' % (w, c, preco, liq, liq / preco * 100))

print('\n\n######## EXTRAS ########')
def piso(nome, vinhos, atalho=None, alvo=0.80, fixo=9):
    p = PLANOS[nome]; cons = p['cota']; ia = cons * custo_consulta(vinhos, atalho=atalho)
    for preco in range(30, 2000):
        gw = gateway(preco)
        if (preco - ia - gw - fixo) / preco >= alvo: return preco, ia
print('--- preço mínimo p/ margem bruta de 80%, cota CHEIA ---')
for nome in PLANOS:
    for rot, vin, at in (('carta 100, sem atalho', 100, None), ('carta 150, sem atalho', 150, None), ('carta 300, sem atalho', 300, None), ('qualquer carta, COM atalho de 40', 300, 40)):
        pr, ia = piso(nome, vin, at)
        print(f'{nome:<7}{rot:<36} IA R$ {ia:7.2f} => preço mínimo R$ {pr}')
print('--- Pro e Rede com carta de 150 rótulos, cota cheia, sem atalho ---')
for nome in ('Pro', 'Rede'):
    ia, gw, imp, bp, c, cp = linha(nome, PLANOS[nome], 1.0, 150, 0.06, 9)
    print(f'{nome}: IA R$ {ia:.2f}  bruta {bp*100:.1f}%  contribuição R$ {c:.2f} ({cp*100:.1f}%)')
print('--- oferta de lançamento (-30% por 3 meses), COM atalho, cota cheia, carta 300 ---')
for nome, p in PLANOS.items():
    q = dict(p); q['preco'] = round(p['preco'] * 0.7)
    ia, gw, imp, bp, c, cp = linha(nome, q, 1.0, 300, 0.06, 9, atalho=40)
    print(f'{nome}: R$ {q["preco"]}  bruta {bp*100:.1f}%  contribuição R$ {c:.2f} ({cp*100:.1f}%)')
print('--- qual fração do preço é IA no pior caso (alerta de 30% do PDF) ---')
for nome, p in PLANOS.items():
    sem = p['cota'] * custo_consulta(300) / p['preco']; com = p['cota'] * custo_consulta(300, atalho=40) / p['preco']
    print(f'{nome}: carta 300 sem atalho {sem*100:.1f}% do preço | com atalho {com*100:.1f}%')
