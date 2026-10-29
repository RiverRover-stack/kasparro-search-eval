#!/usr/bin/env python3
"""Build evaluation/comparison-report.pdf (charts, confusion matrices, metric tables) from comparison-report.json. No network."""
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt
    from matplotlib.patches import Patch, Rectangle
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.pdfgen import canvas
    from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
except ImportError as error:
    raise SystemExit(
        f"make_comparison_pdf.py needs matplotlib and reportlab ({error.name} is missing). "
        'Install them with: py -3 -m pip install -e ".[report]"'
    )

from tools.run_evaluation import (  # noqa: E402
    FIELDS,
    LIMITS,
    MODEL_LABEL,
    case_name,
    failure_reason,
    format_metric,
    format_percent,
    load_labels,
    yes_no,
)

EVALUATION = ROOT / "evaluation"
TITLE = "Kasparro AI visibility classifier: model versus keyword baseline"
CAVEAT = "Single frozen model run (openai/gpt-oss-120b via Groq) - owner-written labels - model quality unverified"
BINARY_FIELDS = FIELDS[:3]
SYSTEMS = (("Model", "model"), ("Keyword baseline", "baseline"))

SURFACE, INK, INK_SOFT, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
MODEL_BLUE, BASELINE_ORANGE = "#2a78d6", "#eb6834"
RAMP_LIGHT, RAMP_DARK = "#cde2fb", "#184f95"
ZEBRA, HEADER_FILL, RULE = "#f3f2ee", "#e6e5e0", "#cfcec8"
CORRECT_BLUE, WRONG_BLUE = "#184f95", "#8cb8ee"

PAGE_WIDTH = A4[0] - 4 * cm


# ---------------------------------------------------------------- charts

def mix(light: str, dark: str, share: float) -> str:
    start, end = colors.HexColor(light), colors.HexColor(dark)
    return colors.Color(*(a + (b - a) * share for a, b in zip(start.rgb(), end.rgb()))).hexval().replace("0x", "#")


def is_dark(color: str) -> bool:
    red, green, blue = colors.HexColor(color).rgb()
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue < 0.5


def style_axes(ax) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(INK_SOFT)
    ax.tick_params(colors=INK_SOFT, labelsize=7, length=0)


def chart_png(fig, preview_dir: Path | None, name: str) -> tuple[bytes, float, float]:
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=200, facecolor=SURFACE)
    width, height = fig.get_size_inches()
    plt.close(fig)
    if preview_dir is not None:
        preview_dir.mkdir(parents=True, exist_ok=True)
        (preview_dir / f"{name}.png").write_bytes(buffer.getvalue())
    return buffer.getvalue(), width, height


def figure_agreement(doc: dict, preview_dir: Path | None) -> tuple[bytes, float, float]:
    fig, axes = plt.subplots(1, 3, figsize=(6.7, 3.1), sharey=True, facecolor=SURFACE)
    series = (("Model", "model_held_out", MODEL_BLUE, -0.2), ("Keyword baseline", "baseline_held_out", BASELINE_ORANGE, 0.2))
    for ax, field in zip(axes, BINARY_FIELDS):
        style_axes(ax)
        ax.set_title(field, fontsize=8, color=INK, pad=6)
        ax.set_ylim(0, 1.12)
        ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
        ax.set_xticks(range(3), ["Agreement", "Precision", "Recall"])
        ax.grid(axis="y", color=GRID, linewidth=0.5)
        ax.set_axisbelow(True)
        for _, key, color, shift in series:
            metric = doc[key]["summary"]["per_label"][field]
            for position, name in enumerate(("agreement", "precision", "recall")):
                value = metric[name]
                if value is None:
                    ax.text(position + shift, 0.02, "n/a", ha="center", va="bottom", fontsize=6.5, color=INK_SOFT)
                    continue
                ax.bar(position + shift, value, width=0.4, color=color, edgecolor=SURFACE, linewidth=1.5)
                ax.text(position + shift, value + 0.015, f"{value:.3f}", ha="center", va="bottom", fontsize=5.5, color=INK)
    axes[0].set_ylabel("Score (0 to 1)", fontsize=7, color=INK_SOFT)
    handles = [Patch(facecolor=color, label=name) for name, _, color, _ in series]
    fig.legend(handles=handles, loc="upper center", ncol=2, frameon=False, fontsize=7.5, labelcolor=INK)
    fig.subplots_adjust(left=0.08, right=0.99, top=0.80, bottom=0.1, wspace=0.12)
    return chart_png(fig, preview_dir, "figure1-held-out-agreement-precision-recall")


def figure_confusion(doc: dict, preview_dir: Path | None) -> tuple[bytes, float, float]:
    fig, axes = plt.subplots(2, 3, figsize=(6.7, 4.7), facecolor=SURFACE)
    summaries = {key: doc[f"{key}_held_out"]["summary"] for _, key in SYSTEMS}
    largest = max(
        summaries[key]["per_label"][field][count]
        for key in summaries
        for field in BINARY_FIELDS
        for count in ("tp", "fp", "fn", "tn")
    )
    roles = (("tp", 0, 0), ("fn", 0, 1), ("fp", 1, 0), ("tn", 1, 1))
    for row, (system, key) in enumerate(SYSTEMS):
        summary = summaries[key]
        for column, field in enumerate(BINARY_FIELDS):
            ax = axes[row][column]
            ax.set_facecolor(SURFACE)
            ax.set_xlim(0, 2)
            ax.set_ylim(2, 0)
            ax.set_aspect("equal")
            for spine in ax.spines.values():
                spine.set_visible(False)
            for role, y, x in roles:
                count = summary["per_label"][field][role]
                fill = mix(SURFACE, RAMP_LIGHT, 0.35) if count == 0 else mix(RAMP_LIGHT, RAMP_DARK, count / largest)
                ax.add_patch(Rectangle((x, y), 1, 1, facecolor=fill, edgecolor=SURFACE, linewidth=2))
                text_color = "white" if is_dark(fill) else INK
                ax.text(x + 0.5, y + 0.45, str(count), ha="center", va="center", fontsize=14, weight="bold", color=text_color)
                ax.text(x + 0.5, y + 0.74, role.upper(), ha="center", va="center", fontsize=6.5, color=text_color)
            ax.set_xticks([0.5, 1.5], ["yes", "no"])
            ax.set_yticks([0.5, 1.5], ["yes", "no"])
            ax.tick_params(colors=INK_SOFT, labelsize=7, length=0)
            ax.set_xlabel("Predicted", fontsize=7, color=INK_SOFT, labelpad=2)
            ax.set_ylabel("Actual", fontsize=7, color=INK_SOFT, labelpad=2)
            ax.set_title(field, fontsize=7.5, color=INK, pad=4)
    fig.subplots_adjust(left=0.07, right=0.99, top=0.88, bottom=0.07, wspace=0.3, hspace=0.78)
    for row, (system, key) in enumerate(SYSTEMS):
        summary = summaries[key]
        covered = f"{summary['validated_cases']} of {summary['total_cases']} cases"
        fig.text(0.5, axes[row][0].get_position().y1 + 0.075, f"{system} ({covered})", ha="center", fontsize=9, weight="bold", color=INK)
    return chart_png(fig, preview_dir, "figure2-held-out-confusion-matrices")


def outcome_counts(summary: dict) -> tuple[int, int, int]:
    correct = summary["passed_cases"]
    return correct, summary["validated_cases"] - correct, summary["total_cases"] - summary["validated_cases"]


def figure_outcomes(doc: dict, preview_dir: Path | None) -> tuple[bytes, float, float]:
    bars = (
        ("Held-out: model", doc["model_held_out"]["summary"], 0.0),
        ("Held-out: keyword baseline", doc["baseline_held_out"]["summary"], 1.0),
        ("Development: model", doc["model_development"]["summary"], 2.5),
        ("Development: keyword baseline", doc["baseline_development"]["summary"], 3.5),
    )
    fig, ax = plt.subplots(figsize=(6.7, 2.7), facecolor=SURFACE)
    style_axes(ax)
    ax.grid(axis="x", color=GRID, linewidth=0.5)
    ax.set_axisbelow(True)
    segments = (
        ("All four labels correct", CORRECT_BLUE, None),
        ("Valid result, at least one label wrong", WRONG_BLUE, None),
        ("No valid result (failed)", "#f1f0ec", "////"),
    )
    plt.rcParams["hatch.linewidth"] = 0.6
    for name, summary, position in bars:
        left = 0
        for count, (_, fill, hatch) in zip(outcome_counts(summary), segments):
            if count == 0:
                continue
            ax.barh(position, count, left=left, height=0.8, color=fill, hatch=hatch,
                    edgecolor=INK_SOFT if hatch else SURFACE, linewidth=0.8 if hatch else 1.5)
            ax.text(left + count / 2, position, str(count), ha="center", va="center", fontsize=9, weight="bold",
                    color="white" if is_dark(fill) else INK,
                    bbox={"facecolor": "#f1f0ec", "edgecolor": "none", "pad": 1.2} if hatch else None)
            left += count
    ax.set_yticks([position for _, _, position in bars], [name for name, _, _ in bars])
    ax.set_ylim(4.1, -0.6)
    ax.set_xlim(0, max(summary["total_cases"] for _, summary, _ in bars))
    ax.set_xlabel("Number of cases", fontsize=7.5, color=INK_SOFT)
    handles = [Patch(facecolor=fill, edgecolor=INK_SOFT if hatch else fill, hatch=hatch, label=name) for name, fill, hatch in segments]
    fig.legend(handles=handles, loc="upper center", ncol=3, frameon=False, fontsize=7, labelcolor=INK)
    fig.subplots_adjust(left=0.27, right=0.98, top=0.86, bottom=0.17)
    return chart_png(fig, preview_dir, "figure3-outcome-per-system")


# ---------------------------------------------------------------- captions (numbers computed from the JSON)

def agreement_caption(doc: dict) -> str:
    model, baseline = doc["model_held_out"]["summary"], doc["baseline_held_out"]["summary"]
    pairs = "; ".join(
        f"{field} {format_metric(model['per_label'][field]['agreement'])} vs {format_metric(baseline['per_label'][field]['agreement'])}"
        for field in BINARY_FIELDS
    )
    return (
        f"Figure 1. Held-out agreement, precision and recall per label. Agreement, model vs keyword baseline: {pairs}. "
        f"Model agreement counts the {model['total_cases'] - model['validated_cases']} failed calls as disagreement, so coverage alone "
        f"caps it at {model['validated_cases']}/{model['total_cases']} = {format_metric(model['validation_coverage'])}. "
        "n/a means the formula has a zero denominator."
    )


def confusion_totals(summary: dict) -> tuple[int, int]:
    metrics = [summary["per_label"][field] for field in BINARY_FIELDS]
    return sum(item["fp"] for item in metrics), sum(item["fn"] for item in metrics)


def confusion_caption(doc: dict) -> str:
    model, baseline = doc["model_held_out"]["summary"], doc["baseline_held_out"]["summary"]
    model_fp, model_fn = confusion_totals(model)
    baseline_fp, baseline_fn = confusion_totals(baseline)
    return (
        "Figure 2. Confusion matrices for the held-out set: rows are the owner's label, columns what the system said. "
        f"The model matrices cover only the {model['validated_cases']} validated cases; the "
        f"{model['total_cases'] - model['validated_cases']} failed cases are in no cell and are listed under Failed cases. "
        f"Summed over the three labels, false positives / false negatives are: model {model_fp} / {model_fn} on those cases, "
        f"keyword baseline {baseline_fp} / {baseline_fn} on all {baseline['total_cases']}."
    )


def outcome_caption(doc: dict) -> str:
    parts = []
    for title, prefix in (("Held-out", "held_out"), ("Development", "development")):
        for system, key in SYSTEMS:
            correct, wrong, failed = outcome_counts(doc[f"{key}_{prefix}"]["summary"])
            parts.append(f"{title} {system.lower()} {correct}/{wrong}/{failed}")
    return (
        "Figure 3. Outcome per case, shown as all four labels correct / valid result with at least one label wrong / "
        "no valid result: " + "; ".join(parts) + ". A failed result is its own category and is never counted as brand absence."
    )


def glance_sentences(doc: dict) -> list[str]:
    model, baseline = doc["model_held_out"]["summary"], doc["baseline_held_out"]["summary"]
    total, failed = model["total_cases"], model["total_cases"] - model["validated_cases"]
    recommended = baseline["per_label"]["recommended"]
    positives = recommended["tp"] + recommended["fn"]
    model_recommended = model["per_label"]["recommended"]
    model_positives = model_recommended["tp"] + model_recommended["fn"]
    return [
        f"On the {total} held-out cases the model returned a valid result for {model['validated_cases']} "
        f"({format_percent(model['validation_coverage'])}); the other {failed} calls failed and count as disagreement, not as brand absence.",
        f"All four labels were correct on {model['passed_cases']} of {total} cases for the model and "
        f"{baseline['passed_cases']} of {total} for the keyword baseline.",
        f"brand_mentioned agreement is {format_metric(model['per_label']['brand_mentioned']['agreement'])} for the model and "
        f"{format_metric(baseline['per_label']['brand_mentioned']['agreement'])} for the baseline. "
        f"Recommended cases in the held-out set: {positives}. The baseline found {recommended['tp']} of {positives}; "
        f"the model found {model_recommended['tp']} of the {model_positives} it returned a valid result for.",
        "These numbers come from one run on a small, owner-labelled set. They show how each system lined up with those labels; "
        "they do not show how well either would do on other data.",
    ]


# ---------------------------------------------------------------- document

def build_styles() -> dict[str, ParagraphStyle]:
    base = ParagraphStyle("base", fontName="Helvetica", fontSize=9.5, leading=13.5, textColor=colors.HexColor(INK))
    return {
        "body": base,
        "title": ParagraphStyle("title", parent=base, fontName="Helvetica-Bold", fontSize=20, leading=25, spaceAfter=4),
        "subtitle": ParagraphStyle("subtitle", parent=base, fontSize=12, leading=16, textColor=colors.HexColor(INK_SOFT), spaceAfter=10),
        "h1": ParagraphStyle("h1", parent=base, fontName="Helvetica-Bold", fontSize=14, leading=18, spaceBefore=16, spaceAfter=6, keepWithNext=1),
        "h2": ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold", fontSize=11, leading=15, spaceBefore=10, spaceAfter=4, keepWithNext=1),
        "caption": ParagraphStyle("caption", parent=base, fontSize=8.5, leading=11.5, textColor=colors.HexColor(INK_SOFT), spaceBefore=3, spaceAfter=8),
        "note": ParagraphStyle("note", parent=base, fontSize=8.5, leading=11.5, textColor=colors.HexColor(INK_SOFT), spaceBefore=4, spaceAfter=6),
        "bullet": ParagraphStyle("bullet", parent=base, leftIndent=12, bulletIndent=2, spaceAfter=3),
        "cell": ParagraphStyle("cell", parent=base, fontSize=8.5, leading=11),
        "cell_right": ParagraphStyle("cell_right", parent=base, fontSize=8.5, leading=11, alignment=TA_RIGHT),
        "head": ParagraphStyle("head", parent=base, fontName="Helvetica-Bold", fontSize=8.5, leading=11),
        "head_right": ParagraphStyle("head_right", parent=base, fontName="Helvetica-Bold", fontSize=8.5, leading=11, alignment=TA_RIGHT),
        "code": ParagraphStyle("code", parent=base, fontName="Courier", fontSize=8, leading=11),
        "caveat": ParagraphStyle("caveat", parent=base, fontName="Helvetica-Bold", fontSize=9.5, leading=13),
        "kpi_value": ParagraphStyle("kpi_value", parent=base, fontName="Helvetica-Bold", fontSize=13, leading=17),
        "kpi_label": ParagraphStyle("kpi_label", parent=base, fontSize=8.5, leading=11),
        "kpi_sub": ParagraphStyle("kpi_sub", parent=base, fontSize=7.5, leading=10, textColor=colors.HexColor(INK_SOFT)),
    }


class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas: collects the pages, then draws header and 'Page n of m' once the total is known."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._saved_pages: list[dict] = []

    def showPage(self) -> None:
        self._saved_pages.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total = len(self._saved_pages)
        for state in self._saved_pages:
            self.__dict__.update(state)
            self.draw_chrome(total)
            super().showPage()
        super().save()

    def draw_chrome(self, total: int) -> None:
        left, right = 2 * cm, A4[0] - 2 * cm
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor(INK_SOFT))
        self.setStrokeColor(colors.HexColor(RULE))
        self.setLineWidth(0.5)
        if self._pageNumber > 1:
            self.drawString(left, A4[1] - 1.2 * cm, "Kasparro AI visibility classifier - evaluation comparison")
            self.line(left, A4[1] - 1.4 * cm, right, A4[1] - 1.4 * cm)
        self.line(left, 1.5 * cm, right, 1.5 * cm)
        self.drawString(left, 1.0 * cm, "Single frozen model run - owner-written labels - model quality unverified")
        self.drawRightString(right, 1.0 * cm, f"Page {self._pageNumber} of {total}")


def para(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(text), style)


def table(rows: list[list[str]], widths: list[float], styles: dict, right_from: int | None = None, code_first: bool = False) -> Table:
    def cell(row: int, column: int, text: str) -> Paragraph:
        right = right_from is not None and column >= right_from
        if row == 0:
            return para(text, styles["head_right" if right else "head"])
        if code_first and column == 0:
            return para(text, styles["code"])
        return para(text, styles["cell_right" if right else "cell"])

    data = [[cell(r, c, text) for c, text in enumerate(row)] for r, row in enumerate(rows)]
    result = Table(data, colWidths=widths, repeatRows=1)
    result.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(HEADER_FILL)),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor(SURFACE), colors.HexColor(ZEBRA)]),
                ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor(RULE)),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return result


def metric_table(summary: dict, styles: dict) -> Table:
    rows = [["Label", "Agreement", "Precision", "Recall", "TP", "FP", "FN", "TN"]]
    for field in BINARY_FIELDS:
        metric = summary["per_label"][field]
        rows.append(
            [field, format_metric(metric["agreement"]), format_metric(metric["precision"]), format_metric(metric["recall"])]
            + [str(metric[key]) for key in ("tp", "fp", "fn", "tn")]
        )
    rows.append(["observable_position", format_metric(summary["per_label"]["observable_position"]["agreement"]), "n/a", "n/a", "-", "-", "-", "-"])
    widths = [4.8 * cm, 2.2 * cm, 2.0 * cm, 2.0 * cm] + [1.5 * cm] * 4
    return table(rows, widths, styles, right_from=1)


def set_section(title: str, blocks: list[tuple[str, dict]], styles: dict) -> list:
    story = []
    for system, block in blocks:
        summary = block["summary"]
        story.append(
            KeepTogether(
                [
                    *([para(title, styles["h1"])] if not story else []),
                    para(system, styles["h2"]),
                    para(
                        f"Coverage {summary['validated_cases']}/{summary['total_cases']} ({format_percent(summary['validation_coverage'])}); "
                        f"all four labels correct on {summary['passed_cases']}/{summary['total_cases']} cases.",
                        styles["body"],
                    ),
                    Spacer(1, 4),
                    metric_table(summary, styles),
                    para(
                        f"observable_position is graded by exact equality: {summary['per_label']['observable_position']['matches']} "
                        f"of {summary['total_cases']} cases matched.",
                        styles["note"],
                    ),
                ]
            )
        )
    return story


def figure_block(png: tuple[bytes, float, float], caption: str, styles: dict, heading: str | None = None) -> KeepTogether:
    data, width, height = png
    image = Image(io.BytesIO(data), width=PAGE_WIDTH, height=PAGE_WIDTH * height / width)
    return KeepTogether([*([para(heading, styles["h1"])] if heading else []), image, para(caption, styles["caption"])])


def glance_tiles(doc: dict, styles: dict) -> Table:
    model, baseline = doc["model_held_out"]["summary"], doc["baseline_held_out"]["summary"]
    recommended_model, recommended_baseline = model["per_label"]["recommended"], baseline["per_label"]["recommended"]
    brand_model, brand_baseline = model["per_label"]["brand_mentioned"], baseline["per_label"]["brand_mentioned"]
    tiles = [
        (f"{model['validated_cases']}/{model['total_cases']}", "valid model results", f"{format_percent(model['validation_coverage'])} coverage, held-out"),
        (f"{model['passed_cases']} vs {baseline['passed_cases']}", "exact-match cases", f"model vs baseline, of {model['total_cases']}"),
        (f"{format_metric(brand_model['agreement'])} vs {format_metric(brand_baseline['agreement'])}", "brand_mentioned agreement", "model vs baseline, held-out"),
        (f"{format_metric(recommended_model['recall'])} vs {format_metric(recommended_baseline['recall'])}", "recommended recall", "model vs baseline, held-out"),
    ]
    cells = [[[para(value, styles["kpi_value"]), para(label, styles["kpi_label"]), para(sub, styles["kpi_sub"])] for value, label, sub in tiles]]
    result = Table(cells, colWidths=[PAGE_WIDTH / 4] * 4)
    result.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(ZEBRA)),
                ("LINEAFTER", (0, 0), (-2, -1), 3, colors.HexColor(SURFACE)),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return result


def caveat_bar(styles: dict) -> Table:
    result = Table([[para(CAVEAT, styles["caveat"])]], colWidths=[PAGE_WIDTH])
    result.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(HEADER_FILL)),
                ("LINEBEFORE", (0, 0), (0, -1), 4, colors.HexColor(INK_SOFT)),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    return result


METRIC_DEFINITIONS = [
    ["Metric", "Definition", "Formula"],
    ["Agreement", "Share of all cases in the set where the system's yes/no matches the owner's label. A failed result counts as not agreeing.", "(TP + TN) / all cases in the set"],
    ["Precision", "Of the cases the system called yes, how many the owner also called yes. n/a when the system never said yes.", "TP / (TP + FP)"],
    ["Recall", "Of the cases the owner called yes, how many the system also called yes. n/a when the owner has no yes case.", "TP / (TP + FN)"],
    ["TP, FP, FN, TN", "Owner label (Actual) against system answer (Predicted): TP both yes; FP system yes, owner no; FN system no, owner yes; TN both no.", "counted on validated results only"],
    ["Coverage", "Share of cases where the model output passed the output-contract check.", "validated / total cases"],
    ["Exact match", "A case where all four fields are correct.", "all four fields equal the owner's labels"],
    ["observable_position", "Graded by exact equality with the owner's label, not by precision and recall.", "matches / total cases"],
    ["Failed result", "No valid model output. It is never counted as brand absence and is left out of TP, FP, FN and TN.", "-"],
]


def build_story(doc: dict, labels: dict, preview_dir: Path | None) -> list:
    styles = build_styles()
    story: list = [
        para(TITLE, styles["title"]),
        para(f"Evaluation comparison report - label set {labels['label_set_version']}", styles["subtitle"]),
        caveat_bar(styles),
        para("At a glance", styles["h1"]),
        glance_tiles(doc, styles),
        Spacer(1, 8),
    ]
    story += [para(sentence, styles["body"]) for sentence in glance_sentences(doc)]
    story += [
        para("Metrics used", styles["h1"]),
        para(
            "Both systems label each archived AI answer for four fields, and every score compares them with the project owner's labels.",
            styles["body"],
        ),
        Spacer(1, 4),
        table(METRIC_DEFINITIONS, [3.2 * cm, 9.3 * cm, 4.5 * cm], styles),
        figure_block(figure_agreement(doc, preview_dir), agreement_caption(doc), styles, heading="Held-out results"),
        figure_block(figure_confusion(doc, preview_dir), confusion_caption(doc), styles),
        figure_block(figure_outcomes(doc, preview_dir), outcome_caption(doc), styles),
    ]
    story += set_section(
        "Held-out final check: metric tables",
        [(MODEL_LABEL, doc["model_held_out"]), ("Keyword baseline", doc["baseline_held_out"])],
        styles,
    )
    story += set_section(
        "Development cases: metric tables",
        [(MODEL_LABEL, doc["model_development"]), ("Keyword baseline", doc["baseline_development"])],
        styles,
    )
    story += set_section("Synthetic edge cases: metric tables", [("Keyword baseline only (the model was not run on these cases)", doc["baseline_synthetic"])], styles)
    failures = [
        (title, failure)
        for title, key in (("Held-out", "model_held_out"), ("Development", "model_development"))
        for failure in doc[key]["failed_cases"]
    ]
    if failures:
        rows = [["Set", "Case", "Reason"]] + [
            [title, case_name(failure["response_id"], labels), failure_reason(failure["last_attempt_error"])] for title, failure in failures
        ]
        failed_body = table(rows, [2.6 * cm, 4.2 * cm, 10.2 * cm], styles)
    else:
        failed_body = para("No failed cases.", styles["body"])
    story += [KeepTogether([para("Failed cases", styles["h1"]), failed_body])]
    story += integrity_section(doc, styles)
    story += limits_section(styles)
    return story


def integrity_section(doc: dict, styles: dict) -> list:
    cross, arithmetic, evidence = doc["cross_checks"], doc["score_arithmetic"], doc["report_evidence_check"]
    cross_rows = [
        ["Check", "Result"],
        ["Held-out artifact summary equals recomputed summary", yes_no(cross["held_out_summary_matches_artifact"])],
        ["Stored passed flags equal recomputation from labels (held-out)", yes_no(cross["held_out_passed_flags_match"])],
        ["Stored passed flags equal recomputation from labels (development)", yes_no(cross["development_passed_flags_match"])],
    ]
    defect_rows = [["Seeded defect", "Flagged"]] + [
        [name.replace("_", " "), yes_no(flagged)] for name, flagged in evidence["seeded_defects_flagged"].items()
    ]
    return [
        KeepTogether([para("Integrity checks", styles["h1"]), para("Cross-checks", styles["h2"]), table(cross_rows, [14 * cm, 3 * cm], styles),
                      para("The development artifact stores no summary, so only per-case passed flags are compared.", styles["note"])]),
        KeepTogether(
            [
                para("Score arithmetic", styles["h2"]),
                para(
                    "An independent function (absent 0, mentioned 25, recommended 100) was compared with the project's visibility_score: "
                    f"{arithmetic['checked']} checks ({arithmetic['contract_allowed_combinations']} contract-allowed boolean combinations, "
                    f"{arithmetic['from_expected_labels']} from expected labels, {arithmetic['from_validated_model_results']} from validated "
                    f"model results), {arithmetic['mismatches']} mismatches.",
                    styles["body"],
                ),
            ]
        ),
        KeepTogether(
            [
                para("Report evidence check (stub analysis - mechanics only, not model quality)", styles["h2"]),
                para(
                    f"The report checker read {evidence['results_checked']} results from a stub analysis and found "
                    f"{len(evidence['clean_problems'])} problems in the clean report. Each seeded defect below was inserted on purpose "
                    "to see whether the checker flags it.",
                    styles["body"],
                ),
                Spacer(1, 4),
                table(defect_rows, [14 * cm, 3 * cm], styles),
            ]
        ),
    ]


def limits_section(styles: dict) -> list:
    command_rows = [
        ["Command", "What it does"],
        [r"py -3 tools\run_evaluation.py", "Rebuilds comparison-report.md and comparison-report.json from the saved results. No network, no key."],
        [r"py -3 tools\make_comparison_pdf.py", 'Builds this PDF from the JSON. Needs matplotlib and reportlab: py -3 -m pip install -e ".[report]"'],
        ["see README: hosted_groq", "Real-model runs. The model numbers here were produced earlier and are only read from evaluation/, never rerun."],
    ]
    commands = table(command_rows, [6.2 * cm, 10.8 * cm], styles, code_first=True)
    bullets = [Paragraph(escape(item), styles["bullet"], bulletText="-") for item in LIMITS]
    return [
        KeepTogether([para("Limits and how to reproduce", styles["h1"]), bullets[0]]),
        *bullets[1:],
        Spacer(1, 6),
        KeepTogether([para("How to reproduce", styles["h2"]), commands]),
    ]


def build_pdf(input_dir: Path, output: Path, preview_dir: Path | None = None) -> Path:
    doc = json.loads((input_dir / "comparison-report.json").read_text(encoding="utf-8"))
    labels = json.loads((input_dir / "labels-v1.json").read_text(encoding="utf-8"))
    output.parent.mkdir(parents=True, exist_ok=True)
    template = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=TITLE,
        author="",
        subject="Evaluation comparison report",
        invariant=1,
    )
    template.build(build_story(doc, labels, preview_dir), canvasmaker=NumberedCanvas)
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=EVALUATION, help="folder with comparison-report.json and labels-v1.json")
    parser.add_argument("--output", type=Path, default=None, help="PDF path (default: <input-dir>/comparison-report.pdf)")
    parser.add_argument("--preview-dir", type=Path, default=None, help="also save the chart PNGs here")
    args = parser.parse_args(argv)
    output = args.output or args.input_dir / "comparison-report.pdf"
    print(f"PDF: {build_pdf(args.input_dir, output, args.preview_dir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
