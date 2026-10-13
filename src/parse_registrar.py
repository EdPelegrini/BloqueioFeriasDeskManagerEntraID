# Bloco Python nativo do Maestro (Desk Manager) — bloco "PARSE_Registrar".
#
# DADOS FICTÍCIOS — ver aviso no README do repositório. Códigos de status, autocategoria, causa,
# operador, grupo, e-mails e prefixo do ambiente abaixo são exemplos; troque pelos do seu ambiente.
#
# A primeira linha "#python,resultado!" é a convenção do Maestro: roda como bloco Python e devolve
# apenas a variável "resultado" ao restante do fluxo (evita vazar variáveis locais no response).
#
#python,resultado!
import requests, json, urllib.parse
from datetime import datetime, timedelta

resultado = {"steps": [], "acoes": [], "ok": False}
def log(k, v, _r=resultado):
    _r["steps"].append({str(k): str(v)[:250]})

# ---------------------------------------------------------------------------
# Credenciais: lidas das Constants do Maestro (nunca no codigo).
# Cadastre no Maestro: CST_OP_KEY, CST_PUBLIC_KEY, CST_TENANT, CST_CLIENT_ID,
# CST_CLIENT_SECRET, CST_GRUPO_ENTRA
# ---------------------------------------------------------------------------
cfg = {}
for _k in ["CST_OP_KEY", "CST_PUBLIC_KEY", "CST_TENANT", "CST_CLIENT_ID", "CST_CLIENT_SECRET", "CST_GRUPO_ENTRA"]:
    try:
        cfg[_k] = str(memoria[_k] or "").strip().strip('"')
    except Exception:
        cfg[_k] = ""
faltando = []
for _k in cfg:
    if not cfg[_k] or cfg[_k] == "PREENCHER":
        faltando.append(_k)
OP_KEY = cfg["CST_OP_KEY"]
PUBLIC_KEY = cfg["CST_PUBLIC_KEY"]
TENANT = cfg["CST_TENANT"]
CLIENT_ID = cfg["CST_CLIENT_ID"]
CLIENT_SECRET = cfg["CST_CLIENT_SECRET"]
GRUPO = cfg["CST_GRUPO_ENTRA"]

AUTOCAT = "9001"
STATUS_PAUSA = "000020"      # Aguardando Retorno Ferias (bloqueado) - pausa SLA
STATUS_AGENDADO = "000010"   # Agendamento (aguardando inicio) - pausa SLA
PERIODO_AGEND = "000001"     # Agendamento "Atendimento - Manha"
STATUS_FINAL = "000002"      # Resolvido
OPERADOR_API = "999"
GRUPO_ATEND = "000009"
CAUSA = "000070"
FORMA = "000004"
FRASE = "usuário desbloqueado, retorno de férias"
PREFIXO_URL = "exemplo"                 # para montar link direto do chamado no e-mail
ALERTA_DE = "alertas@exemplo.com.br"        # caixa de origem do alerta (precisa de Mail.Send no app)
ALERTA_PARA = "ti@exemplo.com.br"    # destinatario do alerta de pendencia
# Membros do grupo que NUNCA devem ser apontados como "orfaos" (ids ou UPNs em minusculo; ex.: contas de servico)
IGNORAR_MEMBROS = []
AVISO_SECRET_DIAS = 30  # avisa quando o client secret do app estiver a esta quantidade de dias (ou menos) de expirar

def graph_req(metodo, url, gtoken, corpo=None, extra=None):
    # Chamada ao Graph com retry curto para erros transitorios (429 throttling, 502/503/504) e falhas de rede.
    # Ate 4 tentativas; respeita Retry-After (maximo 8s por espera). Autocontida (sandbox do Maestro).
    # Retorna o objeto Response da ultima tentativa; levanta excecao so se TODAS as tentativas falharem por rede.
    import requests, time
    h = {"Authorization": "Bearer " + gtoken}
    if corpo is not None:
        h["Content-Type"] = "application/json"
    if extra:
        for k_ in extra:
            h[k_] = extra[k_]
    r = None
    for t in range(4):
        try:
            r = requests.request(metodo, url, headers=h, data=corpo, timeout=45)
        except Exception as e:
            if t == 3:
                raise
            time.sleep(2 * (t + 1))
            continue
        if r.status_code in (429, 502, 503, 504) and t < 3:
            espera = 2 * (t + 1)
            try:
                espera = min(int(r.headers.get("Retry-After", espera)), 8)
            except Exception:
                pass
            time.sleep(espera)
            continue
        return r
    return r

def graph_enviar_email(gtoken, de, para, assunto, corpo_texto, req):
    # Envia via Microsoft Graph, em nome de "de". Exige permissao de aplicativo Mail.Send
    # consentida no app registrado (alem das ja usadas para grupo/sessoes).
    # Retorna (ok, detalhe). 202 = aceito (sendMail nao retorna corpo em sucesso).
    # NAO usa constantes do escopo principal (ALERTA_DE/ALERTA_PARA): o sandbox do Maestro
    # nao da as funcoes acesso ao escopo externo - precisa vir por parametro.
    import requests, json
    try:
        r = req("POST", "https://graph.microsoft.com/v1.0/users/" + de + "/sendMail", gtoken,
            json.dumps({
                "message": {
                    "subject": assunto,
                    "body": {"contentType": "Text", "content": corpo_texto},
                    "toRecipients": [{"emailAddress": {"address": para}}],
                },
                "saveToSentItems": "false",
            }))
        if r.status_code == 202:
            return True, "202"
        return False, str(r.status_code) + ":" + r.text[:300]
    except Exception as e:
        return False, str(e)

def iso(d):
    d = (d or "").replace("/", "-").strip()
    p = d.split("-")
    if len(p) == 3:
        return d if len(p[0]) == 4 else p[2] + "-" + p[1].zfill(2) + "-" + p[0].zfill(2)
    return d

def graph_listar_membros(gtoken, grupo, req):
    # Lista os USUARIOS do grupo (id, nome, upn, employeeId), paginando. Retorna (ok, lista, detalhe).
    # Autocontida: o sandbox do Maestro nao deixa funcoes enxergarem o escopo principal.
    import requests
    url = ("https://graph.microsoft.com/v1.0/groups/" + grupo +
           "/members/microsoft.graph.user?$select=id,displayName,userPrincipalName,employeeId&$top=500")
    saida = []
    try:
        for _pag in range(20):
            r = req("GET", url, gtoken)
            if r.status_code != 200:
                return False, [], str(r.status_code) + ":" + r.text[:200]
            j = r.json()
            for u in (j.get("value") or []):
                saida.append(u)
            url = j.get("@odata.nextLink") or ""
            if not url:
                break
        return True, saida, "ok"
    except Exception as e:
        return False, [], str(e)

def norm_mat(m):
    # matricula sem zeros a esquerda, para comparar chamados da mesma pessoa
    m = str(m or "").strip()
    return m.lstrip("0") or "0"

def eh_liberacao(texto):
    # True se o texto (descricao/assunto) indica pedido de LIBERACAO/CANCELAMENTO do bloqueio, e nao um
    # pedido de bloqueio. A descricao vem com entidades HTML duplo-escapadas (ex.: "n&amp;atilde;o").
    # Funcao autocontida: o sandbox nao deixa funcoes enxergarem o escopo principal.
    import re
    t = str(texto or "").lower().replace("&amp;", "&")
    mapa = {"&atilde;": "a", "&otilde;": "o", "&aacute;": "a", "&eacute;": "e", "&iacute;": "i",
            "&oacute;": "o", "&uacute;": "u", "&ccedil;": "c", "&ecirc;": "e", "&acirc;": "a",
            "&ocirc;": "o", "&agrave;": "a"}
    for k in mapa:
        t = t.replace(k, mapa[k])
    t = re.sub(r"&[a-z0-9#]+;", " ", t)
    t = t.translate(str.maketrans("áàâãäéèêëíìîïóòôõöúùûüç", "aaaaaeeeeiiiiooooouuuuc"))
    frases = ["nao realiz", "nao efetu", "nao bloque", "nao execut", "nao proced",
              "cancel", "libera", "desconsider", "suspend", "revog"]
    for f in frases:
        if f in t:
            return True
    return False

def desk_interagir(token, cod, tchamado):
    # PUT api.desk.ms pode dar 413 intermitente de dentro do Maestro -> retry curto.
    # Retorna (ok, detalhe). ok so e True com HTTP 200 e sem "erro" no corpo.
    import requests, json
    ultimo = ""
    for _t in range(4):
        r = requests.put("https://api.desk.ms/ChamadosSuporte/interagir",
            headers={"Authorization": token, "Content-Type": "application/json"},
            data=json.dumps({"Chave": cod, "TChamado": tchamado}), timeout=45)
        ultimo = str(r.status_code) + ":" + r.text[:150]
        if r.status_code == 413:
            continue
        if r.status_code == 200 and '"erro"' not in r.text:
            return True, str(r.status_code)
        return False, ultimo
    return False, ultimo

def desk_ler(token, cod):
    # Relê o chamado imediatamente antes de agir: confirma autocategoria e status ATUAL.
    # Evita agir em chamado de outro processo e evita acao duplicada quando duas execucoes se sobrepoem.
    import requests, json
    r = requests.post("https://api.desk.ms/ChamadosSuporte",
        headers={"Authorization": token, "Content-Type": "application/json"},
        data=json.dumps({"Chave": cod, "CamposExtras": "true"}), timeout=45)
    return r.json()

# ---------------------------------------------------------------------------
# Entrada
# O corpo do POST chega em memoria["BEGIN_init"]["RESPONSE_BODY"] (dict ou string JSON).
# Chamado avulso: {"chamado": "<chave>"} ou webhook de abertura {"trigger":1,"data":{"chamado":...}}.
# Sem nada disso (ex.: cron, que envia {}) -> varredura. MAESTRO_PARAMS nao e lido:
# o "codigo" dele e a chave do proprio Maestro, nunca um chamado.
# ---------------------------------------------------------------------------
mp = {}
try:
    b = memoria["BEGIN_init"]
    if isinstance(b, str):
        b = json.loads(b or "{}")
    mp = dict(b)
except Exception as e:
    log("mp_err", e)
try:
    rb = mp.get("RESPONSE_BODY")
    if isinstance(rb, str):
        rb = json.loads(rb or "{}")
    if isinstance(rb, dict):
        for _k in rb:
            mp[_k] = rb[_k]
except Exception as e:
    log("rb_err", e)
_campos = []
for _k in mp:
    if _k != "MAESTRO_PARAMS" and _k != "RESPONSE_BODY":
        _campos.append(str(_k))
log("init_campos", ",".join(_campos))
codigo_in = str(mp.get("chamado") or mp.get("CodChamado") or "")
if not codigo_in:
    try:
        dd = mp.get("data") or {}
        if isinstance(dd, str):
            dd = json.loads(dd or "{}")
        ch = dd.get("chamado") or (dd.get("TChamado") or {}).get("Chave") or ""
        if isinstance(ch, list): ch = ch[0]
        codigo_in = str(ch or "")
        if "trigger" in mp:
            log("webhook", str(mp.get("trigger")) + " " + str(mp.get("action", "")))
    except Exception as e:
        log("data_err", e)
# A varredura COMPLETA roda SEMPRE, mesmo quando o webhook informa o chamado (codigo_in). Validado em teste:
# na invocacao normal (sem ?realtime=9) os campos declarados no response_model CHEGAM, entao o
# modo "chamado unico" estaria ativo nos webhooks reais - e nele nao existe a lista de abertos, logo as travas
# de duplicidade e a deteccao de orfaos nao rodariam. So a varredura completa aplica todas as protecoes.
# O chamado informado fica apenas registrado no log.
modo = "scan"
evento_cod = ""  # codigo do chamado que disparou o webhook (resolvido apos a listagem)
log("modo", modo +((" (chamado informado: " + codigo_in + ")") if codigo_in else ""))

if faltando:
    log("abortado", "constants faltando: " + ",".join(faltando))
else:
    # Desk login
    desk_token = ""
    try:
        lr = requests.post("https://api.desk.ms/Login/autenticar",
            headers={"Authorization": OP_KEY, "Content-Type": "application/json"},
            data=json.dumps({"PublicKey": PUBLIC_KEY}), timeout=45)
        t = lr.text.strip().strip('"')
        if lr.status_code == 200 and t and not t.startswith("{"):
            desk_token = t
        else:
            log("desk_login_resp", lr.text)
    except Exception as e:
        log("desk_login_err", e)
    log("desk_ok", bool(desk_token))

    # Graph token
    gtoken = ""
    try:
        tr = requests.post("https://login.microsoftonline.com/" + TENANT + "/oauth2/v2.0/token",
            data={"client_id": CLIENT_ID, "scope": "https://graph.microsoft.com/.default",
                  "client_secret": CLIENT_SECRET, "grant_type": "client_credentials"}, timeout=45).json()
        gtoken = tr.get("access_token", "")
        if not gtoken: log("graph_resp", tr.get("error_description", tr))
    except Exception as e:
        log("graph_err", e)
    log("graph_ok", bool(gtoken))

    hoje = (datetime.utcnow() - timedelta(hours=3)).strftime("%Y-%m-%d")
    log("hoje", hoje)
    log("agora_utc", datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
    agora_br = datetime.utcnow() - timedelta(hours=3)
    # Janela do resumo diario: a rodada do cron (03h BRT). Fora dela so avisam falhas gerais e itens do chamado
    # que acabou de disparar o webhook (evita reenviar o mesmo alerta a cada abertura de chamado).
    janela_diaria = 3 <= agora_br.hour < 5

    # Validade do client secret do proprio app (leitura via Graph: applications). A credencial em uso e localizada
    # pelo "hint" (3 primeiros caracteres do secret). Se a leitura falhar, so registra - nao e falha da automacao.
    secret_fim = ""
    secret_dias = None
    if gtoken:
        try:
            ra = graph_req("GET", "https://graph.microsoft.com/v1.0/applications(appId='" + CLIENT_ID + "')?$select=passwordCredentials", gtoken)
            if ra.status_code == 200:
                for cr_ in (ra.json().get("passwordCredentials") or []):
                    if str(cr_.get("hint") or "") == CLIENT_SECRET[:3]:
                        secret_fim = str(cr_.get("endDateTime") or "")[:10]
                if secret_fim:
                    secret_dias = (datetime.strptime(secret_fim, "%Y-%m-%d") - datetime.strptime(hoje, "%Y-%m-%d")).days
                log("secret_validade", (secret_fim + " (" + str(secret_dias) + " dias)") if secret_fim else "credencial em uso nao localizada")
            else:
                log("secret_validade", "leitura indisponivel " + str(ra.status_code))
        except Exception as e:
            log("secret_validade_erro", e)

    # Sem os dois tokens nao faz nada: evita mudar status no Desk sem mexer no Entra (e vice-versa).
    items = []
    abertos = {}  # cod -> {chave, mat, ini, fim, st}: base p/ detectar duplicidade e membros orfaos do grupo
    lista_ok = False  # so apontamos "orfaos" se a listagem de chamados abertos veio inteira (evita falso alarme)
    if desk_token and gtoken:
        if modo == "single":
            items.append({"cod": codigo_in})
        else:
            # varredura de TODOS os chamados em aberto (inclui novos em 000001, agendados e bloqueados).
            # Pre-filtro pelos campos de ferias; a autocategoria 9001 e conferida na releitura.
            seen = set()
            for filtro in ["EmAberto"]:
                try:
                    body = {"Pesquisa": "", "Ativo": filtro, "Colunas": {"CodChamado": "on", "Chave": "on", "CodStatusAtual": "on", "_9102": "on", "_9103": "on", "_9104": "on"}}
                    lr = requests.post("https://api.desk.ms/ChamadosSuporte/lista",
                        headers={"Authorization": desk_token, "Content-Type": "application/json"},
                        data=json.dumps(body), timeout=90)
                    lj = lr.json() or {}
                    root = lj.get("root", []) or []
                    lista_ok = (lr.status_code == 200 and "root" in lj and len(root) > 0)
                    log("lista_" + str(filtro), len(root))
                    for it in root:
                        # pre-filtro barato: sem matricula ou sem datas nao e deste processo
                        if not (it.get("_9102") or "").strip() or not it.get("_9103") or not it.get("_9104"):
                            continue
                        cod = it.get("CodChamado") or ""
                        if cod and cod not in seen:
                            seen.add(cod)
                            items.append({"cod": cod})
                            try:
                                chv = int(it.get("Chave") or 0)
                            except Exception:
                                chv = 0
                            abertos[cod] = {"chave": chv, "mat": norm_mat(it.get("_9102")),
                                            "ini": iso(it.get("_9103")), "fim": iso(it.get("_9104")),
                                            "st": str(it.get("CodStatusAtual") or "")}
                except Exception as e:
                    log("lista_err_" + str(filtro), e)
    else:
        log("abortado", "sem token Desk ou Graph")
    log("items", len(items))
    if codigo_in:
        # o webhook pode informar o CodChamado ou a Chave numerica
        for ocod in abertos:
            if ocod == codigo_in or str(abertos[ocod]["chave"]) == codigo_in:
                evento_cod = ocod

    pendencias = []  # acumula p/ UM e-mail ao final (evita spam de um e-mail por chamado)
    revisoes = []    # chamados que NAO foram tratados porque parecem liberacao/duplicidade/dado invalido
    justificados = set()  # matriculas (sem zeros a esquerda) bloqueadas NESTA rodada: nao sao "orfas"
    # periodo inicial anterior a isto e considerado dado digitado errado (ex.: ano 2024 em vez de 2026)
    limite_antigo = (datetime.utcnow() - timedelta(hours=3, days=60)).strftime("%Y-%m-%d")

    for it in items:
        cod = it["cod"]
        item = {"chamado": cod}

        # releitura: autocategoria, status atual e campos extras direto da fonte
        try:
            tk = desk_ler(desk_token, cod)
            tch = tk.get("TChamado") or {}
        except Exception as e:
            item["erro"] = "ler:" + str(e); resultado["acoes"].append(item); continue
        if str(tch.get("CodAutoCategoria", "")) != AUTOCAT:
            item["skip"] = "autocat " + str(tch.get("CodAutoCategoria", "")); resultado["acoes"].append(item); continue
        vals = {}
        for x in (tk.get("TCamposExtras", []) or []):
            vals[str(x.get("codcampoextra"))] = (x.get("valcampoextra") or "").strip()
        st = tch.get("CodStatusAtual")
        st_seq = st[0].get("sequence", "") if isinstance(st, list) and st else ""
        matricula = vals.get("9102", ""); ini_iso = iso(vals.get("9103", "")); fim_iso = iso(vals.get("9104", ""))
        item["mat"] = matricula; item["janela"] = ini_iso + ".." + fim_iso; item["status"] = st_seq

        if not matricula or not ini_iso or not fim_iso:
            item["skip"] = "sem dados"; resultado["acoes"].append(item); continue
        if st_seq == STATUS_FINAL:
            item["skip"] = "finalizado"; resultado["acoes"].append(item); continue

        # decide a acao ANTES de chamar o Graph (so resolve usuario se for agir)
        if st_seq == STATUS_PAUSA:
            acao = "desbloquear" if hoje > fim_iso else ""
        elif ini_iso <= hoje <= fim_iso:
            acao = "bloquear"
        elif hoje > fim_iso:
            acao = "finalizar_fora_janela"
        elif st_seq != STATUS_AGENDADO:
            # inicio no futuro e SLA correndo: agenda para o dia do inicio (pausa o SLA)
            acao = "agendar"
        else:
            acao = ""
        if not acao:
            item["acao"] = "mantem bloqueado" if st_seq == STATUS_PAUSA else "aguardando inicio"
            resultado["acoes"].append(item); continue

        # Travas antes de BLOQUEAR/AGENDAR: um pedido de liberacao/cancelamento aberto na mesma
        # autocategoria nao pode ser tratado como pedido de bloqueio (foi o que bloqueou uma colaboradora
        # que deveria ser liberada). Na duvida NAO age e avisa por e-mail para revisao manual.
        if acao == "bloquear" or acao == "agendar":
            motivo = ""
            # (A) periodo inicial muito antigo = dado digitado errado
            if ini_iso < limite_antigo:
                motivo = "periodo inicial muito antigo (" + ini_iso + ") - provavel erro de digitacao"
            # (B) outro chamado ABERTO e mais antigo, mesma matricula, periodo sobreposto = duplicidade/liberacao
            if not motivo:
                eu = abertos.get(cod)
                if eu:
                    for ocod in abertos:
                        o = abertos[ocod]
                        if ocod != cod and o["mat"] == eu["mat"] and o["chave"] < eu["chave"] \
                                and eu["ini"] <= o["fim"] and o["ini"] <= eu["fim"]:
                            motivo = "duplicidade com o chamado " + ocod + " (mesma matricula, periodo sobreposto) - possivel pedido de liberacao/cancelamento"
                            break
            # (C) o proprio texto pede para NAO bloquear / cancelar / liberar
            if not motivo:
                if eh_liberacao(str(tch.get("Descricao", "")) + " " + str(tch.get("Assunto", ""))):
                    motivo = "a descricao indica pedido de liberacao/cancelamento"
            if motivo:
                item["acao"] = "REVISAR(" + motivo + ")"; resultado["acoes"].append(item)
                revisoes.append({"chamado": cod, "mat": matricula, "acao": acao, "motivo": motivo})
                continue

        if acao == "agendar":
            ini_br = ini_iso[8:10] + "-" + ini_iso[5:7] + "-" + ini_iso[0:4]
            ok, det = desk_interagir(desk_token, cod, {"CodStatus": STATUS_AGENDADO, "CodFormaAtendimento": FORMA,
                "CodAgendamento": PERIODO_AGEND, "DataAgendamento": ini_br, "PrimeiroAtendimento": "S",
                "Descricao": "Ticket agendado para realizar o bloqueio em " + ini_br + ", conforme solicitado (automacao)."})
            item["acao" if ok else "erro"] = ("AGENDADO p/ " + ini_br) if ok else "agendar:" + det
            resultado["acoes"].append(item); continue

        if acao == "finalizar_fora_janela":
            ok, det = desk_interagir(desk_token, cod, {"CodStatus": STATUS_FINAL, "CodCausa": CAUSA,
                "CodFormaAtendimento": FORMA, "TransferirOperador": OPERADOR_API, "TransferirGrupo": GRUPO_ATEND,
                "Descricao": FRASE})
            item["acao" if ok else "erro"] = "FINALIZADO(fora de janela)" if ok else "finalizar:" + det
            resultado["acoes"].append(item); continue

        # bloquear / desbloquear: resolve matricula -> usuario do Entra (exatamente 1)
        core = matricula.lstrip("0") or "0"
        cands = []
        for w in range(len(core), 9):
            cands.append("'" + core.zfill(w) + "'")
        filt = "employeeId in (" + ",".join(cands) + ")"
        oid = ""; nfound = -1
        try:
            u = "https://graph.microsoft.com/v1.0/users?$count=true&$select=id&$filter=" + urllib.parse.quote(filt)
            rr = graph_req("GET", u, gtoken, None, {"ConsistencyLevel": "eventual"}).json()
            gv = rr.get("value", []); nfound = len(gv)
            if nfound == 1: oid = gv[0]["id"]
        except Exception as e:
            item["erro"] = "resolve:" + str(e); resultado["acoes"].append(item); continue
        if nfound != 1:
            item["acao"] = "PENDENCIA(" + str(nfound) + " usuarios com a matricula)"; resultado["acoes"].append(item)
            pendencias.append({"chamado": cod, "mat": matricula, "acao": acao, "encontrados": nfound})
            continue

        if acao == "desbloquear":
            try:
                rg = graph_req("DELETE", "https://graph.microsoft.com/v1.0/groups/" + GRUPO + "/members/" + oid + "/$ref", gtoken)
            except Exception as e:
                item["erro"] = "graph_delete:" + str(e); resultado["acoes"].append(item); continue
            # 204 = removido; 404 = ja nao era membro. Qualquer outro: NAO finaliza o chamado.
            if rg.status_code not in (204, 404):
                item["erro"] = "graph_delete(" + str(rg.status_code) + "):" + rg.text[:150]
                resultado["acoes"].append(item); continue
            ok, det = desk_interagir(desk_token, cod, {"CodStatus": STATUS_FINAL, "CodCausa": CAUSA,
                "CodFormaAtendimento": FORMA, "TransferirOperador": OPERADOR_API, "TransferirGrupo": GRUPO_ATEND,
                "Descricao": FRASE})
            item["acao" if ok else "erro"] = ("DESBLOQUEADO+FINALIZADO(graph " + str(rg.status_code) + ")") if ok \
                else "removido do grupo, mas falhou finalizar:" + det
        else:  # bloquear
            try:
                rg = graph_req("POST", "https://graph.microsoft.com/v1.0/groups/" + GRUPO + "/members/$ref", gtoken,
                    json.dumps({"@odata.id": "https://graph.microsoft.com/v1.0/directoryObjects/" + oid}))
            except Exception as e:
                item["erro"] = "graph_add:" + str(e); resultado["acoes"].append(item); continue
            # 204 = adicionado; 400 "already exist" = ja era membro. Qualquer outro: NAO muda o status.
            ja_membro = rg.status_code == 400 and "already exist" in rg.text
            if rg.status_code != 204 and not ja_membro:
                item["erro"] = "graph_add(" + str(rg.status_code) + "):" + rg.text[:150]
                resultado["acoes"].append(item); continue
            justificados.add(norm_mat(matricula))
            # derruba as sessoes abertas (forca novo login, que o grupo de ferias barra).
            # Exige a permissao de aplicativo User.RevokeSessions.All. Falha nao desfaz o bloqueio: vai para a obs. interna.
            revog = ""
            try:
                rv = graph_req("POST", "https://graph.microsoft.com/v1.0/users/" + oid + "/revokeSignInSessions", gtoken)
                if rv.status_code != 200:
                    revog = "graph_revoke(" + str(rv.status_code) + "):" + rv.text[:150]
            except Exception as e:
                revog = "graph_revoke:" + str(e)
            obs = "Sessoes do usuario revogadas." if not revog else "ATENCAO: falha ao revogar sessoes abertas - " + revog
            ok, det = desk_interagir(desk_token, cod, {"CodStatus": STATUS_PAUSA, "CodFormaAtendimento": FORMA,
                "TransferirOperador": OPERADOR_API, "TransferirGrupo": GRUPO_ATEND, "PrimeiroAtendimento": "S",
                "Descricao": "Colaborador em ferias - acesso bloqueado ate o retorno (automacao).",
                "ObservacaoInterna": obs})
            item["acao" if ok else "erro"] = ("BLOQUEADO+PAUSA" + ("+SESSOES_REVOGADAS" if not revog else "")) if ok \
                else "adicionado ao grupo, mas falhou mudar status:" + det
            if revog:
                item["aviso"] = revog
        resultado["acoes"].append(item)

    # Membros ORFAOS: pessoas no grupo de ferias sem nenhum chamado de ferias ABERTO em "Aguardando Retorno"
    # que as justifique (ex.: chamado fechado a mao com a pessoa ja bloqueada). So AVISA - nao remove ninguem.
    orfaos = []
    erro_membros = ""
    membros_total = None
    if modo == "scan" and gtoken and lista_ok:
        just = set(justificados)
        for ocod in abertos:
            if abertos[ocod]["st"] == STATUS_PAUSA:
                just.add(abertos[ocod]["mat"])
        okm, membros, detm = graph_listar_membros(gtoken, GRUPO, graph_req)
        if not okm:
            erro_membros = detm
            log("membros_grupo_erro", detm)
        else:
            membros_total = len(membros)
            log("membros_grupo", len(membros))
            for mb in membros:
                mid = str(mb.get("id") or "")
                mupn = str(mb.get("userPrincipalName") or "")
                if mid.lower() in IGNORAR_MEMBROS or mupn.lower() in IGNORAR_MEMBROS:
                    continue
                emp_raw = str(mb.get("employeeId") or "").strip()
                if emp_raw and norm_mat(emp_raw) in just:
                    continue
                orfaos.append({"nome": str(mb.get("displayName") or ""), "upn": mupn,
                               "emp": emp_raw if emp_raw else "(sem employeeId)"})
        log("orfaos", len(orfaos))

    # FALHAS da propria automacao (diferentes de pendencias de negocio). O cron nao grava log, entao sem isto
    # um erro (ex.: Graph recusando remover do grupo, Desk fora do ar) so existiria na execucao e ninguem veria.
    # falhas = tudo o que ocorreu; falhas_env = o que vai no e-mail desta execucao (regra de envio abaixo).
    falhas = []
    falhas_env = []
    if not desk_token:
        falhas.append("Login no Desk Manager falhou (chave do operador/ambiente invalida, ou Desk fora do ar). Nada foi tratado.")
        falhas_env.append(falhas[-1])
    elif modo == "scan" and gtoken and not lista_ok:
        falhas.append("A listagem de chamados abertos do Desk falhou ou veio vazia. A varredura nao tratou nada.")
        falhas_env.append(falhas[-1])
    if erro_membros:
        falhas.append("Nao foi possivel listar os membros do grupo de ferias no Entra ID: " + erro_membros[:200])
        falhas_env.append(falhas[-1])
    for a in resultado["acoes"]:
        if a.get("erro"):
            falhas.append("Chamado " + str(a.get("chamado")) + ": " + str(a.get("erro"))[:200])
            if janela_diaria or str(a.get("chamado")) == evento_cod:
                falhas_env.append(falhas[-1])

    # Aviso de validade do client secret (so no resumo diario).
    aviso_secret = []
    if secret_dias is not None and secret_dias <= AVISO_SECRET_DIAS and janela_diaria:
        aviso_secret.append("O client secret do app (CST_CLIENT_SECRET) expira em " + secret_fim[8:10] + "/" + secret_fim[5:7] + "/" + secret_fim[0:4] +
                            " (" + str(secret_dias) + " dia(s)). Crie um novo secret no registro do app no Entra ID e atualize a Constant CST_CLIENT_SECRET do Maestro. " +
                            "Quando vencer, a automacao para de bloquear/liberar.")

    # Alerta por e-mail: dispara se houver falha da automacao OU item que exige revisao manual (matricula nao
    # resolvida no Entra ID, chamado que parece liberacao/duplicidade/dado invalido, ou membro orfao do grupo).
    # Um e-mail por execucao, SEM estado entre execucoes. Para nao repetir o mesmo alerta a cada abertura de chamado:
    #  - resumo completo (tudo o que segue aberto) so na rodada diaria do cron (03h BRT);
    #  - fora dela: falhas gerais (Desk/lista/membros) e itens do PROPRIO chamado que disparou o webhook (itens novos).
    env_pend = pendencias if janela_diaria else [x_ for x_ in pendencias if x_["chamado"] == evento_cod]
    env_rev = revisoes if janela_diaria else [x_ for x_ in revisoes if x_["chamado"] == evento_cod]
    env_orf = orfaos if janela_diaria else []
    suprimidos = (len(falhas) - len(falhas_env)) + (len(pendencias) - len(env_pend)) + (len(revisoes) - len(env_rev)) + (len(orfaos) - len(env_orf))
    if suprimidos:
        log("alerta_adiado_p_resumo_diario", suprimidos)
    if (falhas_env or aviso_secret or env_pend or env_rev or env_orf) and gtoken:
        partes = []
        if aviso_secret:
            partes.append("CREDENCIAL PRESTES A EXPIRAR:\n" + "\n".join(aviso_secret))
        if falhas_env:
            linhas = []
            for fl_ in falhas_env:
                linhas.append("- " + fl_)
            partes.append("FALHAS DA AUTOMACAO (" + str(len(falhas_env)) + "):\n" +
                          "A automacao tentou agir e nao conseguiu. As acoes sao repetidas na proxima execucao, " +
                          "mas persistindo o erro verifique permissoes do app no Entra ID, validade do client secret e o Desk.\n" +
                          "\n".join(linhas))
        if env_pend:
            linhas = []
            for p in env_pend:
                link = "https://" + PREFIXO_URL + ".desk.ms/?Ticket#ChamadosSuporte:" + p["chamado"]
                qtd = "nao encontrada" if p["encontrados"] == 0 else (str(p["encontrados"]) + " usuarios encontrados")
                linhas.append("- Chamado " + p["chamado"] + " | matricula " + p["mat"] + " | acao pendente: " +
                               p["acao"] + " | " + qtd + " no Entra ID\n  " + link)
            partes.append("MATRICULA NAO RESOLVIDA NO ENTRA ID (" + str(len(env_pend)) + "):\n" +
                          "Corrija o campo 'employeeId' do colaborador no Entra ID ou a matricula no chamado.\n" +
                          "\n".join(linhas))
        if env_rev:
            linhas = []
            for r in env_rev:
                link = "https://" + PREFIXO_URL + ".desk.ms/?Ticket#ChamadosSuporte:" + r["chamado"]
                linhas.append("- Chamado " + r["chamado"] + " | matricula " + r["mat"] + " | iria: " + r["acao"] +
                               " | motivo: " + r["motivo"] + "\n  " + link)
            partes.append("CHAMADOS NAO TRATADOS - REVISAR (" + str(len(env_rev)) + "):\n" +
                          "Parecem pedido de liberacao/cancelamento, duplicidade ou data invalida. " +
                          "Se for liberacao de quem JA esta bloqueado, remova a pessoa do grupo de ferias manualmente.\n" +
                          "\n".join(linhas))
        if env_orf:
            linhas = []
            for o in env_orf:
                linhas.append("- " + o["nome"] + " | " + o["upn"] + " | employeeId: " + o["emp"])
            partes.append("NO GRUPO DE FERIAS SEM CHAMADO ABERTO QUE JUSTIFIQUE (" + str(len(env_orf)) + "):\n" +
                          "Estas pessoas estao bloqueadas, mas nao ha chamado de ferias aberto em 'Aguardando Retorno'. " +
                          "Se ja voltaram (ex.: chamado fechado a mao), remova do grupo de ferias no Entra ID. " +
                          "Se o bloqueio ainda e devido, reabra/abra o chamado. A automacao NAO remove ninguem por conta propria neste caso.\n" +
                          "\n".join(linhas))
        total = len(falhas_env) + len(aviso_secret) + len(env_pend) + len(env_rev) + len(env_orf)
        corpo = (
            "A automacao de Bloqueio de Ferias encontrou " + str(total) +
            " item(ns) que exigem atencao. Itens de revisao (matricula, liberacao, orfaos) nao foram tratados automaticamente.\n\n" +
            "\n\n".join(partes) +
            "\n\nResumo diario (03h): itens ainda abertos sao reenviados todos os dias ate serem resolvidos. " +
            "Falhas gerais da automacao e itens de um chamado recem-aberto avisam na hora."
        )
        ok, det = graph_enviar_email(gtoken, ALERTA_DE, ALERTA_PARA,
            "[Alerta] Bloqueio de Ferias - " + str(total) + " item(ns) exigem atencao",
            corpo, graph_req)
        log("alerta_email", ("enviado " + det) if ok else ("FALHOU " + det))

    # BATIMENTO semanal (segunda, 03h-05h BRT, rodada do cron): prova de vida. Se este e-mail DEIXAR de chegar,
    # a automacao parou (cron, credenciais ou Graph) - unico jeito de perceber uma falha total silenciosa, ja que
    # com o Graph fora nem o alerta consegue sair. So envia se a varredura realmente funcionou (lista_ok).
    if modo == "scan" and gtoken and lista_ok and agora_br.weekday() == 0 and janela_diaria:
        try:
            ate7 = (agora_br + timedelta(days=7)).strftime("%Y-%m-%d")
            n_ag = 0; n_bl = 0; n_out = 0
            blq_prox = []; lib_prox = []
            for ocod in abertos:
                o = abertos[ocod]
                if o["st"] == STATUS_PAUSA:
                    n_bl += 1
                    if o["fim"] < ate7:
                        lib_prox.append((o["fim"], ocod))
                else:
                    if o["st"] == STATUS_AGENDADO:
                        n_ag += 1
                    else:
                        n_out += 1
                    if o["ini"] <= ate7:
                        blq_prox.append((o["ini"], ocod))
            blq_prox.sort(); lib_prox.sort()
            l_blq = []
            for dt_, c_ in blq_prox[:15]:
                l_blq.append("- " + c_ + " (inicio " + dt_[8:10] + "/" + dt_[5:7] + ")")
            l_lib = []
            for dt_, c_ in lib_prox[:15]:
                l_lib.append("- " + c_ + " (fim " + dt_[8:10] + "/" + dt_[5:7] + ", libera no dia seguinte)")
            corpo_hb = (
                "Automacao de Bloqueio de Ferias ATIVA.\n" +
                "Execucao: " + agora_br.strftime("%d/%m/%Y %H:%M") + " (horario de Brasilia). Situacao no inicio da execucao.\n\n" +
                "CHAMADOS DE FERIAS EM ABERTO: " + str(len(abertos)) + "\n" +
                "- Agendados (aguardando inicio): " + str(n_ag) + "\n" +
                "- Bloqueados (aguardando retorno): " + str(n_bl) + "\n" +
                "- Outros (novos/pendentes): " + str(n_out) + "\n" +
                "- Membros no grupo de ferias: " + (str(membros_total) if membros_total is not None else "indisponivel") +
                " | orfaos: " + str(len(orfaos)) + "\n" +
                "- Client secret do app: " + (("expira em " + secret_fim[8:10] + "/" + secret_fim[5:7] + "/" + secret_fim[0:4] +
                                              " (" + str(secret_dias) + " dias)") if secret_fim else "validade indisponivel") + "\n" +
                "- Itens que exigiram atencao nesta execucao: " + str(len(falhas) + len(pendencias) + len(revisoes) + len(orfaos)) + "\n\n" +
                "BLOQUEIOS PREVISTOS NOS PROXIMOS 7 DIAS (" + str(len(blq_prox)) + "):\n" +
                ("\n".join(l_blq) if l_blq else "- nenhum") + "\n\n" +
                "LIBERACOES PREVISTAS NOS PROXIMOS 7 DIAS (" + str(len(lib_prox)) + "):\n" +
                ("\n".join(l_lib) if l_lib else "- nenhuma") + "\n\n" +
                "Se voce deixar de receber este e-mail toda segunda-feira, a automacao parou: verifique o cron " +
                "diario do Bloqueio de Ferias, as Constants (validade do client secret do Entra ID) e o Maestro."
            )
            ok, det = graph_enviar_email(gtoken, ALERTA_DE, ALERTA_PARA,
                "[Batimento] Bloqueio de Ferias - automacao ativa (" + agora_br.strftime("%d/%m") + ")", corpo_hb, graph_req)
            log("batimento", ("enviado " + det) if ok else ("FALHOU " + det))
        except Exception as e:
            log("batimento_erro", e)

    resultado["ok"] = True
