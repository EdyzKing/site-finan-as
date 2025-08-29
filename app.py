import json
import dash
from dash import dcc, html, Input, Output, State
import plotly.express as px
import pandas as pd

app = dash.Dash(__name__)
server = app.server

# -------------------------------------------------------
# LAYOUT
# - "Ganhos Mensais" contém APENAS receitas.
# - Todas as seções a seguir são despesas (subtração).
# - Internet recebida é contabilizada como RECEITA.
#   => Portanto, NÃO é abatida do custo da Internet nas despesas,
#      para evitar dupla contagem.
# -------------------------------------------------------
app.layout = html.Div([
    html.Div([
        html.H1("ORGANIZADOR FINANCEIRO MENSAL"),

        # =================== GANHOS ===================
        html.Div([
            html.H2("💰 Ganhos Mensais"),
            html.Div([html.Label("Salário Bruto:"), dcc.Input(id="salary", type="number", value=0, className="dash-input")], className="input-row"),
            html.Div([html.Label("Bolsa Família:"), dcc.Input(id="bolsa", type="number", value=0, className="dash-input")], className="input-row"),
            html.Div([html.Label("Divisão Internet (recebido):"), dcc.Input(id="internet_received", type="number", value=0, className="dash-input")], className="input-row"),
            html.Div(id="total-income", className="section-total")
        ], className="section"),

        # =================== CONTAS FIXAS ===================
        html.Div([
            html.H2("🏠 Contas Fixas"),
            html.Div([html.Label("Aluguel (atual):"), dcc.Input(id="rent_current", type="number", value=0, className="dash-input")], className="input-row"),
            html.Div([html.Label("Aluguel (novo):"), dcc.Input(id="rent_new", type="number", value=0, className="dash-input")], className="input-row"),
            html.Div([html.Label("Internet (custo cheio):"), dcc.Input(id="internet_cost", type="number", value=0, className="dash-input")], className="input-row"),
            html.Div([html.Label("Luz:"), dcc.Input(id="electricity", type="number", value=0, className="dash-input")], className="input-row"),
            html.Div(id="total-fixed-current", className="section-total"),
            html.Div(id="total-fixed-new", className="section-total")
        ], className="section"),

        # =================== CONTAS PESSOAIS (DINÂMICAS) ===================
        html.Div([
            html.H2("👤 Contas Pessoais"),
            html.Div(id="personal-expenses-div"),
            html.Button("+ Adicionar pessoa", id="add-person", n_clicks=0, className="modern-btn"),
            html.Div(id="total-personal", className="section-total")
        ], className="section"),

        # =================== ALIMENTAÇÃO E TRANSPORTE ===================
        html.Div([
            html.H2("🍽 Alimentação e Transporte"),
            html.Div([html.Label("Supermercado:"), dcc.Input(id="food", type="number", value=0, className="dash-input")], className="input-row"),
            html.Div([html.Label("Delivery/Restaurantes:"), dcc.Input(id="delivery", type="number", value=0, className="dash-input")], className="input-row"),
            html.Div([html.Label("Mobilidade:"), dcc.Input(id="mobility", type="number", value=0, className="dash-input")], className="input-row"),
            html.Div(id="total-food", className="section-total")
        ], className="section"),

        # =================== CALCULAR + SALDO FINAL ===================
        html.Div(
            html.Button("Calcular", id="calculate", n_clicks=0, className="calculate-btn"),
            className="calculate-wrapper"
        ),
        html.Div(id="final-balance", className="final-balance"),

        # =================== GRÁFICOS ===================
        html.H2("📊 Gráficos"),
        dcc.Graph(id="pie-chart"),
        dcc.Graph(id="bar-chart"),
    ], className="container"),
], style={"backgroundColor": "#273f4b", "minHeight": "100vh"})

# -------------------------------------------------------
# CALLBACK: Gestão dinâmica das pessoas (adicionar/excluir)
# -------------------------------------------------------
@app.callback(
    Output("personal-expenses-div", "children"),
    Input("add-person", "n_clicks"),
    Input({'type': 'delete-person', 'index': dash.ALL}, 'n_clicks'),
    State("personal-expenses-div", "children"),
    prevent_initial_call=True
)
def manage_persons(add_click, delete_clicks, children):
    ctx = dash.callback_context
    if not ctx.triggered:
        return children

    trigger = ctx.triggered[0]["prop_id"].split(".")[0]

    # Adicionar pessoa
    if trigger == "add-person":
        idx = add_click  # usa o número atual de cliques como índice
        new_child = html.Div([
            html.Label("Nome:"),
            dcc.Input(id={'type': 'person-name', 'index': idx}, type="text", className="dash-input"),
            html.Label("Dívida Total:"),
            dcc.Input(id={'type': 'person-debt', 'index': idx}, type="number", value=0, className="dash-input"),
            html.Label("Pagamento Mensal:"),
            dcc.Input(id={'type': 'person-monthly', 'index': idx}, type="number", value=0, className="dash-input"),
            html.Button("❌", id={'type': 'delete-person', 'index': idx}, n_clicks=0, className="delete-btn")
        ], className="personal-div", id={'type': 'person-container', 'index': idx})
        if children is None:
            children = []
        children.append(new_child)
        return children

    # Excluir pessoa
    if "delete-person" in trigger:
        try:
            delete_id = json.loads(trigger)  # {'type':'delete-person','index':X}
            remove_index = delete_id["index"]
        except Exception:
            return children

        new_children = []
        for child in children or []:
            # Mantém apenas os que não têm o índice que está sendo removido
            if f"'index': {remove_index}" not in str(child):
                new_children.append(child)
        return new_children

    return children

# -------------------------------------------------------
# CALLBACK: Cálculos + Gráficos + Totais
# - income_total = salary + bolsa + internet_received
# - DESPESAS (sempre subtração após ganhos):
#   * Fixas (atual/novo): aluguel + internet (cheia) + luz
#   * Pessoais: soma dos pagamentos mensais das pessoas
#   * Alimentação e Transporte: supermercado + delivery + mobilidade
# - SALDO FINAL (atual) = income_total - (todas despesas do cenário atual)
# -------------------------------------------------------
@app.callback(
    Output("pie-chart", "figure"),
    Output("bar-chart", "figure"),
    Output("total-income", "children"),
    Output("total-fixed-current", "children"),
    Output("total-fixed-new", "children"),
    Output("total-personal", "children"),
    Output("total-food", "children"),
    Output("final-balance", "children"),
    Input("calculate", "n_clicks"),
    State("salary", "value"),
    State("bolsa", "value"),
    State("internet_received", "value"),
    State("rent_current", "value"),
    State("rent_new", "value"),
    State("internet_cost", "value"),
    State("electricity", "value"),
    State({'type': 'person-monthly', 'index': dash.ALL}, 'value'),
    State("food", "value"),
    State("delivery", "value"),
    State("mobility", "value"),
)
def update_all(n_clicks, salary, bolsa, internet_received,
               rent_current, rent_new, internet_cost, electricity,
               personal_monthly, food, delivery, mobility):
    _ = n_clicks  # só para não acusar variável não usada

    # ------- RECEITAS -------
    income_total = (salary or 0) + (bolsa or 0) + (internet_received or 0)

    # ------- DESPESAS -------
    # Fixas (custo CHEIO de Internet; o que é recebido já está em RECEITAS)
    fixed_current = (rent_current or 0) + (internet_cost or 0) + (electricity or 0)
    fixed_new = (rent_new or 0) + (internet_cost or 0) + (electricity or 0)

    # Pessoais (somatório dos pagamentos mensais)
    total_personal = sum([v for v in (personal_monthly or []) if v is not None])

    # Alimentação e Transporte
    total_food = (food or 0) + (delivery or 0) + (mobility or 0)

    # Totais de despesas por cenário
    expenses_current = fixed_current + total_personal + total_food
    expenses_new = fixed_new + total_personal + total_food

    # Saldos
    saldo_atual = income_total - expenses_current
    saldo_novo = income_total - expenses_new

    # ------- GRÁFICOS -------
    # Pizza mostra como as despesas ATUAIS se distribuem
    pie_df = pd.DataFrame({
        "Categoria": ["Fixas", "Pessoais", "Ali./Transp."],
        "Valor": [fixed_current, total_personal, total_food]
    })
    pie_fig = px.pie(pie_df, names="Categoria", values="Valor", title="Distribuição das Despesas (Cenário Atual)",
                     color_discrete_sequence=["#00c49f", "#ffbb28", "#0088fe"])
    pie_fig.update_layout(paper_bgcolor="#273f4b", font_color="#f5f5f5")

    # Barras com comparação Atual x Novo
    bar_df = pd.DataFrame({
        "Cenário": ["Atual", "Novo"],
        "Receita": [income_total, income_total],
        "Despesas": [expenses_current, expenses_new],
        "Saldo": [saldo_atual, saldo_novo]
    })
    bar_fig = px.bar(bar_df, x="Cenário", y=["Receita", "Despesas", "Saldo"],
                     barmode="group", title="Receita x Despesas x Saldo",
                     color_discrete_map={"Receita": "#00c49f", "Despesas": "#ffbb28", "Saldo": "#0088fe"})
    bar_fig.update_layout(paper_bgcolor="#273f4b", font_color="#f5f5f5")

    # ------- TEXTOS DE TOTAIS -------
    income_text = f"➡️ Receita Total Mensal: R$ {income_total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    fixed_current_text = f"➡️ Contas Fixas (atual): R$ {fixed_current:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    fixed_new_text = f"➡️ Contas Fixas (novo): R$ {fixed_new:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    personal_text = f"➡️ Contas Pessoais (mensal): R$ {total_personal:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    food_text = f"➡️ Alimentação e Transporte: R$ {total_food:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    final_balance_text = html.Div(
        f"💰 SALDO FINAL (Atual): R$ {saldo_atual:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
        className="final-balance"
    )

    return (
        pie_fig,
        bar_fig,
        income_text,
        fixed_current_text,
        fixed_new_text,
        personal_text,
        food_text,
        final_balance_text
    )

# -------------------------------------------------------
# RUN
# -------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True)
