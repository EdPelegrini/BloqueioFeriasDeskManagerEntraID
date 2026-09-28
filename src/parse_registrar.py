# Bloco Python nativo do Maestro (Desk Manager) — bloco "PARSE_Registrar".
#
# DADOS FICTÍCIOS — ver aviso no README do repositório. Códigos de status, autocategoria, causa,
# operador e grupo abaixo são exemplos; troque pelos códigos reais do seu ambiente antes de usar.
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
# Credenciais: lidas das Constants do Maestro (nunca hardcoded no bloco).
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

# Códigos do ambiente (fictícios — ver docs/regras-de-negocio.md)
AUTOCAT = "9001"             # autocategoria "Bloqueio por Férias"
STATUS_PAUSA = "000020"      # "Aguardando Retorno de Férias" (bloqueado) - pausa SLA
STATUS_AGENDADO = "000010"   # "Agendamento" (aguardando início) - pausa SLA
PERIODO_AGEND = "000001"     # tipo de agendamento "Atendimento - Manhã"
STATUS_FINAL = "000002"      # "Resolvido"
OPERADOR_API = "999"         # operador técnico usado pela automação
GRUPO_ATEND = "000009"       # grupo de atendimento para onde o chamado é transferido
CAUSA = "000070"             # causa de finalização "Liberação de Acesso"
FORMA = "000004"             # forma de atendimento
FRASE = "usuário desbloqueado, retorno de férias"

def iso(d):
    # normaliza DD-MM-AAAA (ou D/M/AAAA) para AAAA-MM-DD, comparável como string
    d = (d or "").replace("/", "-").strip()
    p = d.split("-")
    if len(p) == 3:
        return d if len(p[0]) == 4 else p[2] + "-" + p[1].zfill(2) + "-" + p[0].zfill(2)
    return d

def desk_interagir(token, cod, tchamado):
    # PUT na API do Desk Manager pode responder 413 de forma intermitente -> retry curto.
    # Retorna (ok, detalhe). ok só é True com HTTP 200 e sem "erro" no corpo.
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
    # Evita agir em chamado de outro processo e evita ação duplicada quando cron e webhook
    # rodam perto um do outro.
    import requests, json
    r = requests.post("https://api.desk.ms/ChamadosSuporte",
        headers={"Authorization": token, "Content-Type": "application/json"},
        data=json.dumps({"Chave": cod, "CamposExtras": "true"}), timeout=45)
    return r.json()

# ---------------------------------------------------------------------------
# Entrada
# O corpo do POST chega em memoria["BEGIN_init"]["RESPONSE_BODY"] (dict ou string JSON).
# Chamado avulso: {"chamado": "<chave>"} ou webhook de abertura {"trigger":1,"data":{"chamado":...}}.
# Sem nada disso (ex.: cron, que envia {}) -> varredura completa. MAESTRO_PARAMS não é lido para
# isso: o "codigo" dele é a chave do próprio Maestro, nunca um número de chamado.
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
modo = "single" if codigo_in else "scan"
log("modo", modo)

if faltando:
    log("abortado", "constants faltando: " + ",".join(faltando))
else:
    # Login na API do Desk Manager
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

    # Login no Microsoft Graph (client credentials)
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

    # Sem os dois tokens não faz nada: evita mudar status no Desk sem conseguir mexer no Entra
    # (e vice-versa).
    items = []
    if desk_token and gtoken:
        if modo == "single":
            items.append({"cod": codigo_in})
        else:
            # varredura de TODOS os chamados em aberto (inclui novos, agendados e bloqueados).
            # Pré-filtro pelos campos de férias; a autocategoria é conferida na releitura.
            seen = set()
            for filtro in ["EmAberto"]:
                try:
                    body = {"Pesquisa": "", "Ativo": filtro, "Colunas": {"CodChamado": "on", "_9102": "on", "_9103": "on", "_9104": "on"}}
                    lr = requests.post("https://api.desk.ms/ChamadosSuporte/lista",
                        headers={"Authorization": desk_token, "Content-Type": "application/json"},
                        data=json.dumps(body), timeout=90)
                    root = (lr.json() or {}).get("root", []) or []
                    log("lista_" + str(filtro), len(root))
                    for it in root:
                        # pré-filtro barato: sem matrícula ou sem datas não é deste processo
                        if not (it.get("_9102") or "").strip() or not it.get("_9103") or not it.get("_9104"):
                            continue
                        cod = it.get("CodChamado") or ""
                        if cod and cod not in seen:
                            seen.add(cod)
                            items.append({"cod": cod})
                except Exception as e:
                    log("lista_err_" + str(filtro), e)
    else:
        log("abortado", "sem token Desk ou Graph")
    log("items", len(items))

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

        # decide a ação ANTES de chamar o Graph (só resolve usuário se for agir)
        if st_seq == STATUS_PAUSA:
            acao = "desbloquear" if hoje > fim_iso else ""
        elif ini_iso <= hoje <= fim_iso:
            acao = "bloquear"
        elif hoje > fim_iso:
            acao = "finalizar_fora_janela"
        elif st_seq != STATUS_AGENDADO:
            # início no futuro e SLA correndo: agenda para o dia do início (pausa o SLA)
            acao = "agendar"
        else:
            acao = ""
        if not acao:
            item["acao"] = "mantem bloqueado" if st_seq == STATUS_PAUSA else "aguardando inicio"
            resultado["acoes"].append(item); continue

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

        # bloquear / desbloquear: resolve matrícula -> usuário do Entra (exatamente 1)
        core = matricula.lstrip("0") or "0"
        cands = []
        for w in range(len(core), 9):
            cands.append("'" + core.zfill(w) + "'")
        filt = "employeeId in (" + ",".join(cands) + ")"
        oid = ""; nfound = -1
        try:
            u = "https://graph.microsoft.com/v1.0/users?$count=true&$select=id&$filter=" + urllib.parse.quote(filt)
            rr = requests.get(u, headers={"Authorization": "Bearer " + gtoken, "ConsistencyLevel": "eventual"}, timeout=45).json()
            gv = rr.get("value", []); nfound = len(gv)
            if nfound == 1: oid = gv[0]["id"]
        except Exception as e:
            item["erro"] = "resolve:" + str(e); resultado["acoes"].append(item); continue
        if nfound != 1:
            item["acao"] = "PENDENCIA(" + str(nfound) + " usuarios com a matricula)"; resultado["acoes"].append(item); continue

        if acao == "desbloquear":
            try:
                rg = requests.delete("https://graph.microsoft.com/v1.0/groups/" + GRUPO + "/members/" + oid + "/$ref",
                    headers={"Authorization": "Bearer " + gtoken}, timeout=45)
            except Exception as e:
                item["erro"] = "graph_delete:" + str(e); resultado["acoes"].append(item); continue
            # 204 = removido; 404 = já não era membro. Qualquer outro: NÃO finaliza o chamado.
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
                rg = requests.post("https://graph.microsoft.com/v1.0/groups/" + GRUPO + "/members/$ref",
                    headers={"Authorization": "Bearer " + gtoken, "Content-Type": "application/json"},
                    data=json.dumps({"@odata.id": "https://graph.microsoft.com/v1.0/directoryObjects/" + oid}), timeout=45)
            except Exception as e:
                item["erro"] = "graph_add:" + str(e); resultado["acoes"].append(item); continue
            # 204 = adicionado; 400 "already exist" = já era membro. Qualquer outro: NÃO muda o status.
            ja_membro = rg.status_code == 400 and "already exist" in rg.text
            if rg.status_code != 204 and not ja_membro:
                item["erro"] = "graph_add(" + str(rg.status_code) + "):" + rg.text[:150]
                resultado["acoes"].append(item); continue
            # derruba as sessões abertas (força novo login, que o grupo de férias barra).
            # Exige a permissão de aplicativo User.RevokeSessions.All. Falha não desfaz o bloqueio:
            # vai para a observação interna, para acompanhamento da equipe.
            revog = ""
            try:
                rv = requests.post("https://graph.microsoft.com/v1.0/users/" + oid + "/revokeSignInSessions",
                    headers={"Authorization": "Bearer " + gtoken}, timeout=45)
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

    resultado["ok"] = True
