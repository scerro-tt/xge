#!/usr/bin/env python3
"""Generate XGE whitepaper PDF — v2 with tier system and advanced features."""

from fpdf import FPDF

FONT_DIR = "/System/Library/Fonts/Supplemental/"


class XGEReport(FPDF):
    DARK = (30, 30, 30)
    ACCENT = (0, 102, 204)
    GRAY = (100, 100, 100)
    LIGHT_BG = (245, 245, 250)
    WHITE = (255, 255, 255)
    GREEN = (0, 128, 60)
    RED = (180, 30, 30)

    def __init__(self):
        super().__init__()
        self.add_font("Arial", "", FONT_DIR + "Arial.ttf", uni=True)
        self.add_font("Arial", "B", FONT_DIR + "Arial Bold.ttf", uni=True)
        self.add_font("Arial", "I", FONT_DIR + "Arial Italic.ttf", uni=True)
        self.add_font("Arial", "BI", FONT_DIR + "Arial Bold Italic.ttf", uni=True)
        self.add_font("Mono", "", FONT_DIR + "Courier New.ttf", uni=True)
        self.add_font("Mono", "B", FONT_DIR + "Courier New Bold.ttf", uni=True)

    def header(self):
        if self.page_no() > 1:
            self.set_font("Arial", "I", 8)
            self.set_text_color(*self.GRAY)
            self.cell(0, 10, "XGE \u2013 Basis Trade System v2.0", align="L")
            self.cell(0, 10, f"P\u00e1gina {self.page_no()}", align="R")
            self.ln(15)

    def footer(self):
        self.set_y(-15)
        self.set_font("Arial", "I", 7)
        self.set_text_color(*self.GRAY)
        self.cell(0, 10, "Documento confidencial \u2013 Solo para uso interno", align="C")

    def title_page(self):
        self.add_page()
        self.ln(50)
        self.set_font("Arial", "B", 42)
        self.set_text_color(*self.ACCENT)
        self.cell(0, 15, "XGE", align="C")
        self.ln(20)
        self.set_font("Arial", "", 18)
        self.set_text_color(*self.DARK)
        self.cell(0, 10, "Crypto Basis Trade System", align="C")
        self.ln(10)
        self.set_font("Arial", "B", 12)
        self.set_text_color(*self.GREEN)
        self.cell(0, 8, "v2.0 \u2014 Sistema de Tiers con gesti\u00f3n avanzada de capital", align="C")
        self.ln(16)
        self.set_font("Arial", "I", 12)
        self.set_text_color(*self.GRAY)
        self.cell(0, 8, "Documento t\u00e9cnico: arquitectura, rentabilidad,", align="C")
        self.ln(7)
        self.cell(0, 8, "escalabilidad y gesti\u00f3n de riesgo", align="C")
        self.ln(35)
        self.set_font("Arial", "", 10)
        self.set_text_color(*self.GRAY)
        self.cell(0, 6, "Febrero 2026", align="C")
        self.ln(6)
        self.cell(0, 6, "Capital actual: 2.000 USDT", align="C")

    def section_title(self, number, title):
        self.ln(8)
        self.set_font("Arial", "B", 16)
        self.set_text_color(*self.ACCENT)
        self.cell(0, 10, f"{number}. {title}")
        self.ln(10)

    def subsection_title(self, title):
        self.ln(4)
        self.set_font("Arial", "B", 12)
        self.set_text_color(*self.DARK)
        self.cell(0, 8, title)
        self.ln(8)

    def body_text(self, text):
        self.set_font("Arial", "", 10)
        self.set_text_color(*self.DARK)
        self.multi_cell(0, 5.5, text)
        self.ln(2)

    def bullet(self, text):
        self.set_font("Arial", "", 10)
        self.set_text_color(*self.DARK)
        self.cell(8, 5.5, "\u2022")
        self.multi_cell(0, 5.5, text)
        self.ln(1)

    def formula_box(self, lines):
        self.set_fill_color(*self.LIGHT_BG)
        self.set_font("Arial", "", 9)
        self.set_text_color(50, 50, 50)
        x = self.get_x() + 5
        w = self.w - 2 * self.l_margin - 10
        h = len(lines) * 5.5 + 8
        y_start = self.get_y()
        if y_start + h > self.h - 25:
            self.add_page()
            y_start = self.get_y()
        self.set_xy(x, y_start)
        self.rect(x - 2, y_start - 2, w + 4, h + 4, "F")
        for line in lines:
            self.set_x(x + 2)
            self.cell(w, 5.5, line)
            self.ln(5.5)
        self.ln(4)

    def table(self, headers, rows, col_widths=None):
        if col_widths is None:
            col_widths = [(self.w - 2 * self.l_margin) / len(headers)] * len(headers)
        self.set_fill_color(*self.ACCENT)
        self.set_text_color(*self.WHITE)
        self.set_font("Arial", "B", 9)
        for i, h in enumerate(headers):
            self.cell(col_widths[i], 7, h, border=1, fill=True, align="C")
        self.ln()
        self.set_text_color(*self.DARK)
        self.set_font("Arial", "", 9)
        fill = False
        for row in rows:
            if self.get_y() > self.h - 25:
                self.add_page()
            if fill:
                self.set_fill_color(240, 240, 245)
            else:
                self.set_fill_color(*self.WHITE)
            for i, val in enumerate(row):
                align = "C" if i > 0 else "L"
                self.cell(col_widths[i], 6.5, str(val), border=1, fill=True, align=align)
            self.ln()
            fill = not fill
        self.ln(4)

    def highlight_box(self, title, text):
        self.set_fill_color(230, 243, 255)
        self.set_draw_color(*self.ACCENT)
        y = self.get_y()
        w = self.w - 2 * self.l_margin
        self.set_font("Arial", "", 10)
        lines = self.multi_cell(w - 16, 5.5, text, dry_run=True, output="LINES")
        h = len(lines) * 5.5 + 18
        if y + h > self.h - 25:
            self.add_page()
            y = self.get_y()
        self.rect(self.l_margin, y, w, h, "DF")
        self.set_xy(self.l_margin + 6, y + 3)
        self.set_font("Arial", "B", 10)
        self.set_text_color(*self.ACCENT)
        self.cell(0, 6, title)
        self.set_xy(self.l_margin + 6, y + 11)
        self.set_font("Arial", "", 10)
        self.set_text_color(*self.DARK)
        self.multi_cell(w - 16, 5.5, text)
        self.set_y(y + h + 4)

    def warning_box(self, title, text):
        self.set_fill_color(255, 243, 230)
        self.set_draw_color(200, 100, 0)
        y = self.get_y()
        w = self.w - 2 * self.l_margin
        self.set_font("Arial", "", 10)
        lines = self.multi_cell(w - 16, 5.5, text, dry_run=True, output="LINES")
        h = len(lines) * 5.5 + 18
        if y + h > self.h - 25:
            self.add_page()
            y = self.get_y()
        self.rect(self.l_margin, y, w, h, "DF")
        self.set_xy(self.l_margin + 6, y + 3)
        self.set_font("Arial", "B", 10)
        self.set_text_color(200, 100, 0)
        self.cell(0, 6, title)
        self.set_xy(self.l_margin + 6, y + 11)
        self.set_font("Arial", "", 10)
        self.set_text_color(*self.DARK)
        self.multi_cell(w - 16, 5.5, text)
        self.set_y(y + h + 4)


def build():
    pdf = XGEReport()
    pdf.set_auto_page_break(auto=True, margin=25)
    pdf.set_left_margin(20)
    pdf.set_right_margin(20)

    # ═══════════════════════════════════════════════════════════════
    # PORTADA
    # ═══════════════════════════════════════════════════════════════
    pdf.title_page()

    # ═══════════════════════════════════════════════════════════════
    # 1. QU\u00c9 ES XGE
    # ═══════════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.section_title("1", "\u00bfQu\u00e9 es XGE?")
    pdf.body_text(
        "XGE es un sistema automatizado de trading que explota una ineficiencia estructural "
        "del mercado de criptomonedas: la diferencia entre el precio spot (contado) y el precio "
        "de los contratos perpetuos. Esta diferencia genera un flujo de pagos llamado "
        "funding rate que XGE captura de forma sistem\u00e1tica."
    )
    pdf.body_text(
        "El sistema opera 24/7 de forma aut\u00f3noma con una arquitectura modular: recolecci\u00f3n "
        "de datos en tiempo real v\u00eda WebSocket, validaci\u00f3n multicapa de oportunidades, "
        "ejecuci\u00f3n automatizada, monitorizaci\u00f3n continua de delta y un sistema de protecci\u00f3n "
        "de capital con reservas intocables."
    )
    pdf.body_text(
        "Actualmente opera con un capital de 2.000 USDT distribuido en un sistema de tiers "
        "que asigna capital por calidad de activo. Su arquitectura es horizontalmente escalable: "
        "puede gestionar desde 2.000 USDT hasta carteras de m\u00e1s de 1.500.000 USDT "
        "a\u00f1adiendo exchanges y pares sin modificar el c\u00f3digo."
    )

    # ═══════════════════════════════════════════════════════════════
    # 2. FUNDING RATE
    # ═══════════════════════════════════════════════════════════════
    pdf.section_title("2", "\u00bfQu\u00e9 es el funding rate y por qu\u00e9 existe?")
    pdf.body_text(
        "Los contratos perpetuos son derivados sin fecha de vencimiento. Para que su "
        "precio se mantenga alineado con el spot, los exchanges aplican un mecanismo de "
        "equilibrio: el funding rate."
    )
    pdf.bullet(
        "Cuando el perp cotiza POR ENCIMA del spot (mercado alcista, m\u00e1s compradores), "
        "los longs pagan a los shorts. El funding rate es positivo."
    )
    pdf.bullet(
        "Cuando el perp cotiza POR DEBAJO del spot, los shorts pagan a los longs. "
        "El funding rate es negativo."
    )
    pdf.bullet(
        "El pago se realiza cada 8 horas (3 veces al d\u00eda): "
        "a las 00:00, 08:00 y 16:00 UTC."
    )
    pdf.subsection_title("F\u00f3rmula de anualizaci\u00f3n")
    pdf.formula_box([
        "Tasa anualizada = funding_rate \u00d7 3 periodos/d\u00eda \u00d7 365 d\u00edas \u00d7 100",
        "",
        "Ejemplo: funding_rate = 0,0001 (0,01% por periodo de 8h)",
        "  anualizada = 0,0001 \u00d7 3 \u00d7 365 \u00d7 100 = 10,95%",
    ])

    # ═══════════════════════════════════════════════════════════════
    # 3. ESTRATEGIA
    # ═══════════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.section_title("3", "La estrategia: Basis Trade (Cash & Carry)")
    pdf.body_text(
        "El basis trade es una de las estrategias m\u00e1s antiguas y probadas en mercados "
        "financieros. En el \u00e1mbito crypto funciona as\u00ed:"
    )
    pdf.subsection_title("Mec\u00e1nica paso a paso")
    pdf.body_text(
        "1. VALIDACI\u00d3N MULTICAPA: Antes de abrir cualquier posici\u00f3n, el sistema ejecuta "
        "5 comprobaciones: funding rate actual, historial de 7 d\u00edas, spread spot-perp, "
        "volumen 24h y estabilidad del Open Interest."
    )
    pdf.body_text(
        "2. AN\u00c1LISIS DE BREAKEVEN: Se calcula el coste real de la operaci\u00f3n "
        "(comisiones de entrada + salida) y se verifica que el funding cubra esos costes "
        "en menos de 9 periodos (3 d\u00edas). Si no es viable, no se abre."
    )
    pdf.body_text("3. APERTURA: Se ejecutan dos \u00f3rdenes simult\u00e1neas:")
    pdf.bullet("Compra en mercado spot (posici\u00f3n larga).")
    pdf.bullet("Venta en contrato perpetuo (posici\u00f3n corta).")
    pdf.body_text(
        "4. COBRO: Cada 8 horas, al mantener el perp en short con funding positivo, "
        "el exchange nos paga el funding rate sobre el tama\u00f1o de la posici\u00f3n."
    )
    pdf.body_text(
        "5. MONITORIZACI\u00d3N: Cada 30 segundos el Delta Monitor verifica que la posici\u00f3n "
        "se mantiene equilibrada. Si el desbalance supera el 2%, lanza alertas y reequilibra."
    )
    pdf.body_text(
        "6. CIERRE: El sistema cierra autom\u00e1ticamente cuando se cumple alguna condici\u00f3n "
        "de salida (5 criterios diferentes, detallados en la secci\u00f3n 6)."
    )

    pdf.subsection_title("\u00bfPor qu\u00e9 es delta-neutral?")
    pdf.formula_box([
        "Si BTC sube $1.000:",
        "  Spot:  ganamos  +$1.000",
        "  Perp:  perdemos -$1.000",
        "  Neto:  $0 (neutral) + funding cobrado",
        "",
        "Si BTC baja $1.000:",
        "  Spot:  perdemos -$1.000",
        "  Perp:  ganamos  +$1.000",
        "  Neto:  $0 (neutral) + funding cobrado",
    ])
    pdf.highlight_box(
        "Ventaja fundamental",
        "No necesitamos predecir si el precio va a subir o bajar. "
        "Ganamos dinero independientemente de la direcci\u00f3n del mercado, "
        "siempre que el funding rate se mantenga positivo."
    )

    # ═══════════════════════════════════════════════════════════════
    # 4. SISTEMA DE TIERS Y CAPITAL
    # ═══════════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.section_title("4", "Sistema de tiers y gesti\u00f3n de capital")
    pdf.body_text(
        "El capital de 2.000 USDT se distribuye de forma estructurada en tiers "
        "seg\u00fan la calidad y liquidez de cada activo. Este dise\u00f1o optimiza el "
        "rendimiento ajustado al riesgo de cada par."
    )

    pdf.subsection_title("Distribuci\u00f3n del capital")
    pdf.formula_box([
        "Capital total:       2.000 USDT",
        "\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500",
        "Capital operativo:   1.800 USDT (90%)",
        "Reserva rebalanceo:    200 USDT (10%) \u2014 intocable",
        "",
        "Del capital operativo:",
        "  Tier 1:  1.260 USDT (70%)  \u2192 BTC, ETH, SOL, XRP",
        "  Tier 2:    360 USDT (20%)  \u2192 WLD, NEAR, AVAX",
        "  Buffer:    180 USDT (10%)  \u2192 reserva de estabilidad",
    ])

    pdf.subsection_title("Tier 1 \u2014 Large Caps")
    pdf.table(
        ["Par\u00e1metro", "Valor"],
        [
            ["S\u00edmbolos", "BTC/USDT, ETH/USDT, SOL/USDT, XRP/USDT"],
            ["Capital asignado", "1.260 USDT"],
            ["Tama\u00f1o por par", "315 USDT (1.260 / 4)"],
            ["M\u00e1ximo posiciones abiertas", "4"],
            ["Funding m\u00ednimo por periodo", "0,008% (8,76% anualizado)"],
            ["Stop loss por par", "-1,575 USDT (0,5% de 315)"],
            ["Alerta de delta drift", "6,30 USDT (2% de 315)"],
        ],
        [55, 115],
    )

    pdf.subsection_title("Tier 2 \u2014 Mid Caps")
    pdf.table(
        ["Par\u00e1metro", "Valor"],
        [
            ["S\u00edmbolos", "WLD/USDT, NEAR/USDT, AVAX/USDT"],
            ["Capital asignado", "360 USDT"],
            ["Tama\u00f1o por par", "180 USDT"],
            ["M\u00e1ximo posiciones abiertas", "2"],
            ["Funding m\u00ednimo por periodo", "0,015% (16,4% anualizado)"],
            ["Stop loss por par", "-0,90 USDT (0,5% de 180)"],
            ["Alerta de delta drift", "3,60 USDT (2% de 180)"],
        ],
        [55, 115],
    )

    pdf.subsection_title("Blacklist")
    pdf.body_text(
        "Los siguientes pares est\u00e1n excluidos permanentemente de la operativa "
        "por baja liquidez, funding err\u00e1tico o problemas hist\u00f3ricos: "
        "ATOM/USDT, DOT/USDT, OP/USDT, AAVE/USDT."
    )

    pdf.subsection_title("Protecci\u00f3n de la reserva")
    pdf.body_text(
        "La reserva de 200 USDT es intocable salvo emergencia. Si el balance total estimado "
        "cae por debajo de 1.800 USDT, el sistema activa el protocolo de protecci\u00f3n:"
    )
    pdf.bullet("Primero cierra todas las posiciones del Tier 2.")
    pdf.bullet("Si el balance sigue por debajo, eval\u00faa cerrar posiciones del Tier 1.")
    pdf.bullet("Cada cierre por protecci\u00f3n se registra con exit_reason='reserve_protection'.")

    # ═══════════════════════════════════════════════════════════════
    # 5. FILTROS DE ENTRADA
    # ═══════════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.section_title("5", "Filtros de entrada: validaci\u00f3n multicapa")
    pdf.body_text(
        "Antes de abrir cualquier posici\u00f3n, el sistema ejecuta una validaci\u00f3n exhaustiva "
        "que debe superar 7 comprobaciones independientes. Esto elimina la mayor\u00eda de "
        "falsos positivos y reduce dr\u00e1sticamente el riesgo de entrar en operaciones no viables."
    )

    pdf.subsection_title("Capa 1: Filtros b\u00e1sicos")
    pdf.bullet("El s\u00edmbolo no est\u00e1 en la blacklist.")
    pdf.bullet("El s\u00edmbolo pertenece a un tier (Tier 1 o Tier 2).")
    pdf.bullet("El funding rate actual es positivo.")
    pdf.bullet("El funding rate supera el m\u00ednimo del tier correspondiente.")
    pdf.bullet("El funding rate anualizado supera el 10% de umbral de entrada.")

    pdf.subsection_title("Capa 2: Validaci\u00f3n de capital")
    pdf.bullet("Hay capital libre suficiente para el tama\u00f1o del tier (315 o 180 USDT).")
    pdf.bullet("No se ha alcanzado el m\u00e1ximo de posiciones abiertas para ese tier.")
    pdf.bullet("La reserva de 200 USDT permanece intacta.")
    pdf.bullet("No existe ya una posici\u00f3n abierta para ese par/exchange.")

    pdf.subsection_title("Capa 3: An\u00e1lisis de breakeven")
    pdf.body_text(
        "El sistema calcula el coste real del ciclo completo (apertura + cierre) "
        "usando las comisiones reales de cada exchange:"
    )
    pdf.table(
        ["Exchange", "Spot", "Perp Maker", "Perp Taker"],
        [
            ["Bitget", "0,10%", "0,02%", "0,06%"],
            ["OKX", "0,10%", "0,02%", "0,05%"],
            ["MEXC", "0,02%", "0,00%", "0,06%"],
        ],
        [40, 35, 45, 45],
    )

    pdf.body_text("Ejemplo con 315 USDT en Bitget y funding de 0,05%:")
    pdf.formula_box([
        "Coste entrada  = 315 \u00d7 (0,001 + 0,0006) = 0,504 USDT",
        "Coste salida   = 315 \u00d7 (0,001 + 0,0002) = 0,378 USDT",
        "Coste total    = 0,882 USDT",
        "",
        "Funding/periodo = 315 \u00d7 0,0005 = 0,1575 USDT",
        "Breakeven       = 0,882 / 0,1575 = 5,6 periodos (1,9 d\u00edas)",
        "Viable: S\u00cd (< 9 periodos / 3 d\u00edas)",
    ])

    pdf.warning_box(
        "Regla cr\u00edtica",
        "Con un capital de 2.000 USDT y posiciones de 315 USDT, solo se abre una posici\u00f3n "
        "cuando el breakeven es inferior a 9 periodos de funding (3 d\u00edas). "
        "Si el funding es demasiado bajo para cubrir las comisiones en ese plazo, "
        "la oportunidad se descarta autom\u00e1ticamente."
    )

    pdf.subsection_title("Capa 4: Validaci\u00f3n del par (Pair Selector)")
    pdf.bullet("Funding rate positivo durante los \u00faltimos 7 d\u00edas consecutivos.")
    pdf.bullet("Spread spot-perp inferior al 0,05% (evita entrar con p\u00e9rdida latente).")
    pdf.bullet("Volumen 24h del perpetuo superior a 5.000.000 USDT.")
    pdf.bullet("Open Interest estable o creciente (ca\u00edda m\u00e1xima del 10% en 24h).")

    pdf.highlight_box(
        "Resultado del filtro multicapa",
        "De las cientos de combinaciones exchange/par monitorizadas, solo pasan las que "
        "cumplen TODAS las condiciones de las 4 capas. Esto garantiza que cada posici\u00f3n "
        "abierta tiene una alta probabilidad de ser rentable."
    )

    # ═══════════════════════════════════════════════════════════════
    # 6. CRITERIOS DE SALIDA
    # ═══════════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.section_title("6", "Criterios de salida autom\u00e1tica")
    pdf.body_text(
        "El sistema implementa 5 criterios de salida independientes, cada uno dise\u00f1ado "
        "para un escenario espec\u00edfico de deterioro. Cada cierre registra la raz\u00f3n exacta "
        "en Redis para an\u00e1lisis posterior."
    )

    pdf.subsection_title("a) Funding Drop")
    pdf.body_text(
        "Si el funding actual cae por debajo del 70% del funding de entrada, se eval\u00faa "
        "el cierre. Esto detecta deterioro progresivo antes de que el funding se vuelva "
        "no rentable. Solo se activa tras completar al menos 1 periodo de funding (8 horas)."
    )
    pdf.formula_box([
        "Condici\u00f3n: funding_actual < funding_entrada \u00d7 0,70",
        "exit_reason: 'funding_drop'",
    ])

    pdf.subsection_title("b) Funding Negativo (2 periodos)")
    pdf.body_text(
        "Si el funding se vuelve negativo durante 2 periodos consecutivos, se cierra "
        "inmediatamente sin respetar el tiempo m\u00ednimo de holding. El Delta Monitor "
        "rastrea los periodos negativos de cada posici\u00f3n."
    )
    pdf.formula_box([
        "Condici\u00f3n: funding < 0 durante 2 periodos consecutivos",
        "exit_reason: 'funding_negative'",
        "Prioridad: INMEDIATA (sin esperar 8h m\u00ednimas)",
    ])

    pdf.subsection_title("c) Stop Loss por Tier")
    pdf.body_text(
        "Cada tier tiene un l\u00edmite de p\u00e9rdida m\u00e1ximo por posici\u00f3n. Si el PnL no realizado "
        "supera ese l\u00edmite y el funding acumulado no cubre la p\u00e9rdida, se cierra inmediatamente."
    )
    pdf.table(
        ["Tier", "Tama\u00f1o", "Stop Loss", "L\u00edmite"],
        [
            ["Tier 1", "315 USDT", "0,5%", "-1,575 USDT"],
            ["Tier 2", "180 USDT", "0,5%", "-0,900 USDT"],
        ],
        [30, 40, 30, 40],
    )
    pdf.formula_box([
        "Condici\u00f3n: PnL_no_realizado < -stop_loss",
        "  Y funding_acumulado < abs(PnL_no_realizado)",
        "exit_reason: 'stop_loss'",
    ])

    pdf.subsection_title("d) Tiempo m\u00ednimo de holding")
    pdf.body_text(
        "Ninguna posici\u00f3n se cierra antes de completar 1 periodo completo de funding "
        "(8 horas), excepto por stop loss o funding negativo. Esto evita cierres prematuros "
        "que no permitan al funding cubrir los costes de entrada."
    )

    pdf.subsection_title("e) Protecci\u00f3n de reserva")
    pdf.body_text(
        "Si el balance total estimado cae por debajo de 1.800 USDT (capital operativo), "
        "el sistema cierra posiciones de forma escalonada: primero Tier 2, luego Tier 1."
    )
    pdf.formula_box([
        "Condici\u00f3n: balance_estimado < 1.800 USDT",
        "Acci\u00f3n: cerrar Tier 2 \u2192 si persiste, cerrar Tier 1",
        "exit_reason: 'reserve_protection'",
    ])

    # ═══════════════════════════════════════════════════════════════
    # 7. DELTA MONITOR
    # ═══════════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.section_title("7", "Monitorizaci\u00f3n de delta y basis en tiempo real")
    pdf.body_text(
        "El Delta Monitor es un componente independiente que corre cada 30 segundos "
        "para verificar que todas las posiciones abiertas mantienen su neutralidad. "
        "Esto es cr\u00edtico porque peque\u00f1os desequilibrios pueden convertirse en p\u00e9rdidas "
        "significativas si no se detectan a tiempo."
    )

    pdf.subsection_title("C\u00e1lculo del delta")
    pdf.formula_box([
        "delta = (spot_quantity \u00d7 spot_price) - (perp_quantity \u00d7 perp_price)",
        "",
        "Umbral de alerta:",
        "  Tier 1: abs(delta) > 6,30 USDT (2% de 315)",
        "  Tier 2: abs(delta) > 3,60 USDT (2% de 180)",
    ])

    pdf.subsection_title("Protocolo de actuaci\u00f3n")
    pdf.bullet("Si delta dentro de umbral: log DEBUG y continuar.")
    pdf.bullet("Si delta supera umbral: log WARNING con detalle completo.")
    pdf.bullet("Intento de rebalanceo con \u00f3rdenes maker (timeout 60 segundos).")
    pdf.bullet("Si el rebalanceo falla: log CRITICAL para intervenci\u00f3n manual.")

    pdf.subsection_title("Basis tracking")
    pdf.body_text(
        "Adem\u00e1s del delta, el monitor calcula y almacena en Redis la basis (diferencia "
        "porcentual entre spot y perp) de cada posici\u00f3n con timestamps. Esto permite "
        "analizar la evoluci\u00f3n de la basis a lo largo del tiempo y detectar patrones."
    )
    pdf.formula_box([
        "basis = (spot_price - perp_price) / perp_price \u00d7 100",
        "Almacenado en: basis:{exchange}:{symbol}:{timestamp}",
        "TTL: 24 horas",
    ])

    # ═══════════════════════════════════════════════════════════════
    # 8. ARQUITECTURA
    # ═══════════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.section_title("8", "Arquitectura del sistema")
    pdf.body_text(
        "XGE est\u00e1 compuesto por m\u00f3dulos as\u00edncronos que operan de forma concurrente. "
        "Todo el c\u00f3digo es async/await (asyncio), lo que permite escalar a decenas de "
        "exchanges y cientos de pares sin hilos ni procesos adicionales."
    )

    pdf.subsection_title("M\u00f3dulos del sistema")
    pdf.table(
        ["M\u00f3dulo", "Funci\u00f3n", "Frecuencia"],
        [
            ["ws_collector", "Precios bid/ask en tiempo real (WebSocket)", "Continuo"],
            ["funding_collector", "Funding rates (WS o REST fallback)", "5 min"],
            ["redis_cache", "Almac\u00e9n de datos en memoria", "Continuo"],
            ["pair_selector", "Validaci\u00f3n multicapa de oportunidades", "Por entrada"],
            ["breakeven", "C\u00e1lculo de viabilidad con fees reales", "Por entrada"],
            ["tier_config", "Definici\u00f3n de tiers, capital y comisiones", "Est\u00e1tico"],
            ["strategy", "L\u00f3gica de entrada/salida con tiers", "60 seg"],
            ["executor", "Ejecuci\u00f3n de \u00f3rdenes (paper/live)", "Por se\u00f1al"],
            ["position_manager", "Gesti\u00f3n de posiciones en Redis", "Por evento"],
            ["delta_monitor", "Monitorizaci\u00f3n de delta y basis", "30 seg"],
            ["metrics", "C\u00e1lculo de m\u00e9tricas y reportes", "Bajo demanda"],
            ["email_notifier", "Notificaciones de apertura/cierre", "Por evento"],
        ],
        [38, 85, 40],
    )

    pdf.subsection_title("Flujo de datos")
    pdf.formula_box([
        "Exchanges (WS) \u2192 Collectors \u2192 Redis Cache",
        "",
        "Redis \u2192 BasisTradeStrategy (cada 60s)",
        "  \u2502",
        "  \u251c\u2500 Filtros b\u00e1sicos (blacklist, tier, funding)",
        "  \u251c\u2500 Validaci\u00f3n de capital (tier limits, reserva)",
        "  \u251c\u2500 Breakeven (comisiones reales, viabilidad)",
        "  \u251c\u2500 Pair Selector (historial, spread, volumen, OI)",
        "  \u2502",
        "  \u2514\u2500 Si pasa todo \u2192 TradeExecutor \u2192 PositionManager",
        "                             \u2514\u2500 EmailNotifier",
        "",
        "DeltaMonitor (cada 30s) \u2192 Monitoriza posiciones abiertas",
    ])

    pdf.subsection_title("Tecnolog\u00edas")
    pdf.bullet("Python 3.11+ con asyncio para concurrencia.")
    pdf.bullet("ccxt / ccxt.pro para la comunicaci\u00f3n con exchanges.")
    pdf.bullet("Redis para persistencia en memoria (posiciones, precios, historial).")
    pdf.bullet("Resend para notificaciones por correo electr\u00f3nico.")
    pdf.bullet("Docker + Railway para el despliegue en producci\u00f3n.")
    pdf.bullet("pytest + pytest-asyncio para el conjunto de tests (49 tests).")

    # ═══════════════════════════════════════════════════════════════
    # 9. M\u00c9TRICAS Y REPORTING
    # ═══════════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.section_title("9", "M\u00e9tricas y reporting")
    pdf.body_text(
        "El m\u00f3dulo de m\u00e9tricas lee todos los trades de Redis y genera un informe completo "
        "de rendimiento. Las m\u00e9tricas se calculan bajo demanda y cubren tanto el rendimiento "
        "individual como la gesti\u00f3n global del capital."
    )

    pdf.subsection_title("M\u00e9tricas disponibles")
    pdf.table(
        ["M\u00e9trica", "Descripci\u00f3n"],
        [
            ["funding_yield_real", "Rendimiento real del funding cobrado vs. capital"],
            ["basis_cost", "Coste medio del spread al entrar"],
            ["net_pnl_ratio", "PnL neto como porcentaje del capital usado"],
            ["win_rate", "Porcentaje de trades con PnL positivo"],
            ["avg_pnl_per_trade", "PnL medio por operaci\u00f3n"],
            ["funding_vs_drift", "Ratio funding cobrado vs. p\u00e9rdida por drift"],
            ["projected_monthly_yield", "Rendimiento mensual proyectado"],
            ["capital_deployed", "Capital actualmente en posiciones"],
            ["capital_free", "Capital disponible para nuevas posiciones"],
            ["reserve_status", "Estado de la reserva (OK o ALERT)"],
            ["best_pair / worst_pair", "Par con mejor/peor rendimiento acumulado"],
        ],
        [55, 115],
    )

    pdf.subsection_title("Logging estructurado")
    pdf.body_text(
        "Cada evento del sistema se registra con un formato estructurado que incluye "
        "timestamp, nivel, exchange, s\u00edmbolo y mensaje descriptivo."
    )
    pdf.formula_box([
        "INFO:     Entradas, salidas, funding acumulado, estado del capital",
        "WARNING:  Drift > 2%, funding drop, posici\u00f3n cerca de stop loss",
        "ERROR:    Fallos de conexi\u00f3n, \u00f3rdenes rechazadas",
        "CRITICAL: Stop loss activado, reserva comprometida, funding negativo",
    ])

    # ═══════════════════════════════════════════════════════════════
    # 10. ESCALABILIDAD
    # ═══════════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.section_title("10", "Escalabilidad")
    pdf.body_text(
        "La arquitectura de XGE est\u00e1 dise\u00f1ada para escalar desde un capital m\u00ednimo "
        "de prueba hasta carteras institucionales. Los cambios necesarios para escalar "
        "son puramente de configuraci\u00f3n, sin modificar c\u00f3digo."
    )

    pdf.subsection_title("\u00bfQu\u00e9 cambia al escalar?")
    pdf.table(
        ["Par\u00e1metro", "2.000 USDT", "100K USDT", "1M USDT"],
        [
            ["Exchanges", "3", "6\u20138", "10\u201312"],
            ["Pares por tier", "4 + 3", "15 + 10", "25 + 15"],
            ["Posiciones simult\u00e1neas", "6", "20\u201330", "40\u201350"],
            ["Tama\u00f1o por posici\u00f3n", "180\u2013315", "2K\u20135K", "10K\u201330K"],
            ["Fee (VIP)", "Est\u00e1ndar", "Reducido", "VIP"],
            ["Coste por ciclo", "~0,32%", "~0,24%", "~0,16%"],
            ["Retorno estimado", "4\u20138%", "5\u201310%", "6\u201312%"],
        ],
        [42, 30, 30, 30],
    )

    pdf.subsection_title("\u00bfPor qu\u00e9 mejora la rentabilidad al escalar?")
    pdf.bullet(
        "Comisiones VIP: a mayor volumen, menores fees. Con 1M USDT y 50 posiciones "
        "rotando cada 2\u20133 semanas, el volumen mensual supera los $5M, desbloqueando "
        "tarifas VIP en todos los exchanges principales."
    )
    pdf.bullet(
        "M\u00e1s oportunidades: con 40+ pares y 12 exchanges (480+ combinaciones), "
        "siempre hay m\u00faltiples pares con funding atractivo. La utilizaci\u00f3n del capital "
        "aumenta del 60% al 75%."
    )
    pdf.bullet(
        "Diversificaci\u00f3n: el impacto de un evento adverso (liquidaci\u00f3n, exchange down, "
        "funding negativo en un par) se diluye entre 50 posiciones en 12 exchanges."
    )
    pdf.bullet(
        "Sin impacto de mercado: posiciones de $10K\u2013$30K son insignificantes respecto "
        "al volumen diario de los principales pares (BTC mueve $20B+/d\u00eda)."
    )

    pdf.subsection_title("C\u00f3mo se escala")
    pdf.body_text(
        "Escalar el sistema requiere \u00fanicamente modificar el archivo de configuraci\u00f3n "
        "tier_config.py y a\u00f1adir exchanges en settings.yaml. La l\u00f3gica del sistema "
        "se adapta autom\u00e1ticamente:"
    )
    pdf.bullet("A\u00f1adir nuevos tiers (Tier 3 para altcoins l\u00edquidas).")
    pdf.bullet("Aumentar size_per_pair y capital_total de cada tier.")
    pdf.bullet("Habilitar exchanges adicionales (Binance, Bybit, Gate, etc.).")
    pdf.bullet("A\u00f1adir nuevos s\u00edmbolos a cada tier.")

    # ═══════════════════════════════════════════════════════════════
    # 11. RIESGOS
    # ═══════════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.section_title("11", "Riesgos y mitigaciones")
    pdf.body_text(
        "Aunque el basis trade es delta-neutral, no est\u00e1 libre de riesgos. "
        "El sistema implementa m\u00faltiples capas de protecci\u00f3n para cada tipo de riesgo."
    )

    pdf.table(
        ["Riesgo", "Probabilidad", "Impacto", "Mitigaci\u00f3n"],
        [
            ["Funding negativo", "Media", "Bajo", "Cierre tras 2 periodos negativos"],
            ["Delta drift", "Media", "Bajo", "Monitor cada 30s, rebalanceo auto"],
            ["Slippage entrada", "Baja", "Bajo", "Spread < 0,05% como filtro"],
            ["Liquidaci\u00f3n perp", "Muy baja", "Alto", "Delta-neutral + stop loss 0,5%"],
            ["Exchange down", "Baja", "Medio", "Diversificaci\u00f3n en 3\u201312 exchanges"],
            ["Hackeo exchange", "Muy baja", "Alto", "M\u00e1x. 15% capital por exchange"],
            ["Low funding period", "Alta", "Bajo", "No abrir si breakeven > 3 d\u00edas"],
            ["Reserva da\u00f1ada", "Baja", "Alto", "Cierre escalonado autom\u00e1tico"],
        ],
        [35, 28, 22, 80],
    )

    pdf.highlight_box(
        "Defensa en profundidad",
        "El sistema aplica 7 filtros antes de abrir y 5 condiciones de cierre. "
        "La reserva de 200 USDT (10%) es intocable. El stop loss del 0,5% limita "
        "la p\u00e9rdida m\u00e1xima por posici\u00f3n a 1,575 USDT (Tier 1) o 0,90 USDT (Tier 2). "
        "La p\u00e9rdida m\u00e1xima te\u00f3rica del sistema completo, con todas las posiciones "
        "en stop loss simult\u00e1neamente, ser\u00eda de 8,10 USDT (0,4% del capital)."
    )

    # ═══════════════════════════════════════════════════════════════
    # 12. PROYECCIONES
    # ═══════════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.section_title("12", "Proyecciones de rentabilidad")

    pdf.subsection_title("Con 2.000 USDT (configuraci\u00f3n actual)")
    pdf.body_text(
        "Los siguientes c\u00e1lculos asumen comisiones est\u00e1ndar (sin VIP), "
        "3 exchanges activos y la distribuci\u00f3n de capital por tiers."
    )

    pdf.table(
        ["Escenario", "Funding medio", "Neto/mes", "Neto/a\u00f1o", "% Anual"],
        [
            ["Conservador", "0,008%/per.", "$1,44", "$17,28", "0,86%"],
            ["Moderado", "0,015%/per.", "$4,32", "$51,84", "2,59%"],
            ["Optimista", "0,03%/per.", "$11,88", "$142,56", "7,13%"],
        ],
        [30, 35, 30, 30, 30],
    )

    pdf.warning_box(
        "Nota sobre capital peque\u00f1o",
        "Con 2.000 USDT las comisiones tienen un impacto proporcionalmente mayor. "
        "El sistema est\u00e1 optimizado para operar de forma segura a este nivel, "
        "pero la rentabilidad real mejora significativamente al escalar."
    )

    pdf.subsection_title("Con 100.000 USDT (primer escalado)")
    pdf.table(
        ["Escenario", "Funding medio", "Neto/mes", "Neto/a\u00f1o", "% Anual"],
        [
            ["Conservador", "0,008%/per.", "$130", "$1.560", "1,56%"],
            ["Moderado", "0,012%/per.", "$380", "$4.560", "4,56%"],
            ["Optimista", "0,018%/per.", "$750", "$9.000", "9,00%"],
        ],
        [30, 35, 30, 30, 30],
    )

    pdf.subsection_title("Con 1.000.000 USDT (escala institucional)")
    pdf.table(
        ["Escenario", "Funding medio", "Neto/mes", "Neto/a\u00f1o", "% Anual"],
        [
            ["Conservador", "0,008%/per.", "$3.194", "$38.320", "3,83%"],
            ["Moderado", "0,012%/per.", "$5.693", "$68.320", "6,83%"],
            ["Optimista", "0,018%/per.", "$9.579", "$114.950", "11,50%"],
        ],
        [30, 35, 30, 30, 30],
    )

    pdf.highlight_box(
        "Rendimiento ajustado al riesgo",
        "El Sharpe ratio estimado del basis trade es de 2,0\u20133,5, "
        "significativamente superior al del S&P 500 (hist\u00f3rico ~0,9). "
        "Esto se debe a la baja volatilidad del retorno (delta-neutral) "
        "combinada con un flujo de ingresos consistente (funding rate). "
        "La estrategia genera retorno tanto en mercados alcistas como bajistas."
    )

    # ═══════════════════════════════════════════════════════════════
    # 13. COMPARATIVA
    # ═══════════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.section_title("13", "Comparativa con otras inversiones")
    pdf.body_text("Comparaci\u00f3n con inversi\u00f3n de 1.000.000 USDT (escenario moderado):")

    pdf.table(
        ["Inversi\u00f3n", "Retorno", "Ret. \u20ac", "Riesgo", "Volat."],
        [
            ["Cuenta ahorro", "3\u20134%", "$30\u201340K", "Muy bajo", "Nula"],
            ["Bonos EE.UU.", "4\u20135%", "$40\u201350K", "Bajo", "Baja"],
            ["S&P 500", "8\u201310%", "$80\u2013100K", "Medio", "Alta"],
            ["Basis trade XGE", "4\u201312%", "$38\u2013115K", "Medio-bajo", "Muy baja"],
            ["Holding BTC", "Variable", "Variable", "Muy alto", "Muy alta"],
        ],
        [36, 22, 27, 28, 28],
    )

    pdf.body_text(
        "La ventaja diferencial del basis trade es que ofrece retornos comparables "
        "a la renta variable pero con volatilidad significativamente menor. "
        "La fuente de retorno (el funding rate) es estructural: existe mientras "
        "haya traders apalancados en el mercado de perpetuos, lo cual es una "
        "constante del mercado crypto."
    )

    # ═══════════════════════════════════════════════════════════════
    # 14. CONCLUSI\u00d3N
    # ═══════════════════════════════════════════════════════════════
    pdf.section_title("14", "Conclusi\u00f3n")
    pdf.body_text(
        "XGE v2.0 implementa un sistema de basis trading con las siguientes "
        "caracter\u00edsticas diferenciales:"
    )
    pdf.bullet(
        "Validaci\u00f3n multicapa (4 capas, 7+ comprobaciones) que elimina "
        "operaciones no viables antes de ejecutarlas."
    )
    pdf.bullet(
        "Sistema de tiers que asigna capital proporcionalmente a la calidad "
        "y liquidez de cada activo."
    )
    pdf.bullet(
        "C\u00e1lculo de breakeven con comisiones reales por exchange que garantiza "
        "que solo se abren posiciones econ\u00f3micamente viables."
    )
    pdf.bullet(
        "Monitorizaci\u00f3n continua de delta (cada 30s) con rebalanceo autom\u00e1tico "
        "y alertas escalonadas."
    )
    pdf.bullet(
        "5 criterios de salida independientes que cubren desde deterioro gradual "
        "(funding drop) hasta emergencias (reserva comprometida)."
    )
    pdf.bullet(
        "Protecci\u00f3n de capital con reserva intocable del 10% y cierre escalonado "
        "por tiers ante p\u00e9rdidas."
    )
    pdf.bullet(
        "Escalabilidad horizontal: de 2.000 USDT a 1.500.000 USDT sin cambiar "
        "una l\u00ednea de c\u00f3digo, solo configuraci\u00f3n."
    )
    pdf.bullet(
        "49 tests unitarios que cubren pair_selector, breakeven, strategy, "
        "modelos y toda la l\u00f3gica cr\u00edtica."
    )

    pdf.ln(4)
    pdf.body_text(
        "El sistema est\u00e1 listo para operar en producci\u00f3n con capital real. "
        "La transici\u00f3n de paper trading a live trading requiere \u00fanicamente "
        "configurar las API keys de los exchanges y cambiar paper_trading a false "
        "en el archivo de configuraci\u00f3n."
    )

    # ── Guardar ──
    output_path = "/Users/platomico/Desktop/projects/xge/XGE_Basis_Trade_System.pdf"
    pdf.output(output_path)
    print(f"PDF generado: {output_path}")
    return output_path


if __name__ == "__main__":
    build()
