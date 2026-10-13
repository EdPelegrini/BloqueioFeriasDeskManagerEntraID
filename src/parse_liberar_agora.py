# Bloco Python nativo do Maestro — Ação Rápida "Liberar acesso agora" (Interação Avançada do chamado).
#
# DADOS FICTÍCIOS — ver aviso no README do repositório. Códigos de autocategoria, status e campos extras
# abaixo são exemplos; troque pelos do seu ambiente.
#
#python,d_saida!
# Acao Rapida "Liberar acesso agora" (bloqueio de ferias).
# NAO mexe no Entra ID: ajusta o periodo final do chamado para ONTEM e aciona o Maestro de bloqueio (varredura),
# que remove a pessoa do grupo (ou cancela o bloqueio agendado) e finaliza o chamado, com todas as travas.
# Duas etapas: (1) sem "etapa" -> modal de confirmacao; (2) etapa="liberar" -> executa.
# Funcoes autocontidas (o sandbox do Maestro nao deixa funcoes enxergarem o escopo principal).
import json
import requests
import maestroutils
from datetime import datetime, timedelta

d_init = memoria["BEGIN_init"]
d_saida = {}

AUTOCAT = "9001"
STATUS_PAUSA = "000020"
STATUS_AGENDADO = "000010"
PREFIXO = "exemplo"


def f_cod(d_entrada):
    l_campos = ["codmodal", "cod_chamado", "codchamado", "chamado_cod", "chave_chamado", "chamado"]
    for s_campo in l_campos:
        v_valor = d_entrada.get(s_campo, "")
        if isinstance(v_valor, str) and v_valor.strip() != "":
            return v_valor.strip()
    return ""


def f_primeiro(d_entrada, l_campos):
    # primeiro campo preenchido entre os nomes candidatos
    for s_campo in l_campos:
        v_valor = d_entrada.get(s_campo, "")
        if isinstance(v_valor, str) and v_valor.strip() != "":
            return v_valor.strip()
    return ""


def f_campos_recebidos(d_entrada):
    # nomes (sem valores) dos campos preenchidos que chegaram - usado so quando o operador nao e identificado
    l_nomes = []
    for s_k in d_entrada:
        if s_k.startswith("MAESTRO_"):
            continue
        v = d_entrada.get(s_k)
        if isinstance(v, str) and v.strip() != "":
            l_nomes.append(s_k)
    return ",".join(l_nomes)


def f_ler(s_token, s_cod):
    import requests
    import json
    o_r = requests.post("https://api.desk.ms/ChamadosSuporte",
        headers={"Authorization": s_token, "Content-Type": "application/json"},
        data=json.dumps({"Chave": s_cod, "CamposExtras": "true"}), timeout=45)
    return o_r.json()


def f_resumo(d_tk):
    d_tch = d_tk.get("TChamado") or {}
    d_ce = {}
    for d_x in (d_tk.get("TCamposExtras") or []):
        d_ce[str(d_x.get("codcampoextra"))] = (d_x.get("valcampoextra") or "").strip()
    l_st = d_tch.get("CodStatusAtual")
    s_st = ""
    if isinstance(l_st, list) and len(l_st) > 0:
        s_st = str(l_st[0].get("sequence", ""))
    s_fin = str(d_tch.get("DataFinalizacao", ""))
    return {
        "chave": str(d_tch.get("Chave", "")),
        "cod": str(d_tch.get("CodChamado", "")),
        "autocat": str(d_tch.get("CodAutoCategoria", "")),
        "st": s_st,
        "st_nome": str(d_tch.get("NomeStatus", "")),
        "finalizado": (s_fin != "" and s_fin != "0000-00-00"),
        "nome": d_ce.get("8864", ""),
        "mat": d_ce.get("8602", ""),
        "ini": d_ce.get("8603", ""),
        "fim": d_ce.get("9104", ""),
    }


def f_operador(s_token, s_cod):
    # nome do operador pelo codigo (a Acao Rapida so entrega o codigo). Melhor esforco: "" se nao resolver.
    import requests
    import json
    if s_cod == "":
        return ""
    try:
        o_r = requests.post("https://api.desk.ms/Operadores",
            headers={"Authorization": s_token, "Content-Type": "application/json"},
            data=json.dumps({"Chave": s_cod}), timeout=30)
        d_o = (o_r.json() or {}).get("TOperador") or {}
        s_nome = (str(d_o.get("Nome") or "") + " " + str(d_o.get("Sobrenome") or "")).strip()
        s_login = str(d_o.get("Login") or "").strip()
        if s_nome != "" and s_login != "":
            return s_nome + " (" + s_login + ")"
        return s_nome
    except Exception:
        return ""


def f_campo(s_tipo, s_nome, s_label, s_valor, b_ro):
    return {
        "type": s_tipo, "name": s_nome, "label": s_label, "value": s_valor,
        "placeholder": "", "description": "", "readonly": "true" if b_ro else "false",
        "required": "false", "mask": "", "maskreverse": "", "cols": "10", "trigger": "false",
    }


def f_nota(s_token, s_cod, s_st, s_ini_br, s_obs):
    # registro de auditoria sem trocar o status (validado: CodStatus igual ao atual). Melhor esforco.
    import requests
    import json
    d_t = {"CodStatus": s_st, "CodFormaAtendimento": "000004",
           "Descricao": "Liberacao antecipada do bloqueio solicitada por operador (acao rapida).",
           "ObservacaoInterna": s_obs, "EnviarEmail": "N"}
    if s_st == "000010":  # status "Agendamento" (literal: funcoes do sandbox nao enxergam o escopo principal)
        d_t["CodAgendamento"] = "000001"
        d_t["DataAgendamento"] = s_ini_br
    try:
        o_r = requests.put("https://api.desk.ms/ChamadosSuporte/interagir",
            headers={"Authorization": s_token, "Content-Type": "application/json"},
            data=json.dumps({"Chave": s_cod, "TChamado": d_t}), timeout=45)
        return (o_r.status_code == 200 and '"erro"' not in o_r.text)
    except Exception:
        return False


def f_set_fim(s_token, s_chave, s_valor):
    import requests
    import json
    o_r = requests.put("https://exemplo.desk.ms/ChamadosSuporte/camposextras",
        headers={"Authorization": s_token, "Content-Type": "application/json"},
        data=json.dumps({"TChamado": {"Chave": s_chave}, "TCampoExtra": {"9104": s_valor}}), timeout=45)
    return (o_r.status_code == 200 and "sucesso" in o_r.text)


def f_acionar(s_url):
    import requests
    try:
        o_r = requests.post(s_url, headers={"Content-Type": "application/json"}, data="{}", timeout=100)
        return o_r.status_code
    except Exception:
        return 0


s_token = memoria["CRON_access_token"]["access_token"]
s_url_var = str(memoria["CST_URL_VARREDURA"]).strip().strip('"')
s_etapa = str(d_init.get("etapa") or "").strip()
s_cod_in = f_cod(d_init)
s_cod = s_cod_in
if s_etapa == "liberar":
    s_conf = str(d_init.get("chamado_conf") or "").strip()
    if s_conf != "":
        s_cod = s_conf
# Operador que clicou: o nome do campo no payload real da Acao Rapida foi descoberto empiricamente. O primeiro
# clique real mostrou que "operador_cod" (padrao de Embed) vem VAZIO; "codoperador" e o usado em modais de AR.
s_oper = f_primeiro(d_init, ["operador_conf", "codoperador", "operador_cod"])
s_oper_nome = f_primeiro(d_init, ["operador_nome_conf", "operador_nomecompleto", "operador_nome"])
if s_oper_nome == "" and s_oper != "":
    s_oper_nome = f_operador(s_token, s_oper)

try:
    s_action = str(maestroutils.tokenMaestro()).strip().strip('"')
except Exception:
    s_action = ""

try:
    if s_cod == "":
        d_saida = {"error": "Nao foi possivel identificar o chamado. Abra esta acao a partir de um chamado.", "action": s_action}
    else:
        d_r = f_resumo(f_ler(s_token, s_cod))
        if d_r["autocat"] != AUTOCAT:
            d_saida = {"error": "Este chamado nao e de bloqueio por ferias (autocategoria " + d_r["autocat"] + ").", "action": s_action}
        elif d_r["finalizado"]:
            d_saida = {"error": "Este chamado ja esta finalizado. Se a pessoa continua bloqueada, remova-a do grupo de ferias no Entra ID " +
                       "(o alerta por e-mail de membros sem chamado aberto avisa esses casos).", "action": s_action}
        elif s_etapa != "liberar":
            # ETAPA 1: modal de confirmacao (nao altera nada)
            if d_r["st"] == STATUS_PAUSA:
                s_aviso = "A pessoa sera REMOVIDA do grupo de bloqueio e o chamado sera finalizado."
            else:
                s_aviso = "O bloqueio ainda nao foi aplicado: o bloqueio agendado sera CANCELADO e o chamado finalizado."
            d_saida = {
                "modal": {"title": "Liberar acesso agora", "button": "Liberar acesso", "btnback": ""},
                "group": [{
                    "name": "Confirme a liberacao",
                    "open": "true",
                    "fields": [
                        f_campo("text", "i_chamado", "Chamado", d_r["cod"], True),
                        f_campo("text", "i_nome", "Colaborador", d_r["nome"], True),
                        f_campo("text", "i_mat", "Matricula", d_r["mat"], True),
                        f_campo("text", "i_periodo", "Periodo de ferias", d_r["ini"] + " a " + d_r["fim"], True),
                        f_campo("text", "i_status", "Status atual", d_r["st_nome"], True),
                        f_campo("text", "i_aviso", "O que vai acontecer", s_aviso, True),
                        f_campo("text", "i_operador", "Solicitado por", s_oper_nome if s_oper_nome != "" else ("operador " + s_oper), True),
                        f_campo("hidden", "etapa", "", "liberar", False),
                        f_campo("hidden", "chamado_conf", "", d_r["cod"], False),
                        f_campo("hidden", "operador_conf", "", s_oper, False),
                        f_campo("hidden", "operador_nome_conf", "", s_oper_nome, False),
                        f_campo("hidden", "campos_conf", "", f_campos_recebidos(d_init) if s_oper == "" else "", False),
                    ],
                }],
                "action": s_action,
            }
        else:
            # ETAPA 2: executa
            s_agora = (datetime.utcnow() - timedelta(hours=3))
            s_ontem = (s_agora - timedelta(days=1)).strftime("%d-%m-%Y")
            if s_oper != "":
                s_quem = "operador " + s_oper + ((" (" + s_oper_nome + ")") if s_oper_nome != "" else "")
            else:
                s_quem = "operador NAO IDENTIFICADO [campos recebidos na 1a chamada: " + str(d_init.get("campos_conf") or "") + "]"
            s_obs = ("AUDITORIA: liberacao antecipada solicitada pelo " + s_quem + " em " +
                     s_agora.strftime("%d/%m/%Y %H:%M") + " via acao rapida. Periodo final alterado de " +
                     d_r["fim"] + " para " + s_ontem + " (para desfazer, restaure o periodo original).")
            b_nota = f_nota(s_token, d_r["cod"], d_r["st"], d_r["ini"], s_obs)
            b_fim = f_set_fim(s_token, d_r["chave"], s_ontem)
            if not b_fim:
                d_saida = {"error": "Nao foi possivel ajustar o periodo do chamado. Nada foi liberado.", "action": s_action}
            else:
                i_http = f_acionar(s_url_var)
                d_r2 = f_resumo(f_ler(s_token, d_r["cod"]))
                if d_r2["finalizado"]:
                    s_msg = "Acesso liberado e chamado finalizado."
                else:
                    s_msg = "Liberacao solicitada: o periodo foi ajustado e a automacao conclui na proxima execucao. Confira o chamado."
                if not b_nota:
                    s_msg = s_msg + " (A nota de auditoria nao pode ser registrada.)"
                d_saida = {"msg": s_msg, "modal": "close.all", "grid": "refresh"}
except Exception as o_erro:
    d_saida = {"error": "Falha ao processar a liberacao: " + str(o_erro)[:200], "action": s_action}
