"""Build the two searchable handoff PDFs from editable sources and saved results."""

import hashlib
import json
import os
import re
import subprocess
import sys
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from xml.sax.saxutils import escape

import reportlab
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    CondPageBreak,
    Flowable,
    Frame,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

ROOT = Path(__file__).resolve().parents[1]
PDF_DIR = ROOT / "docs/pdf"
WIDTH, HEIGHT = A4
MARGIN = 44
CONTENT = WIDTH - 2 * MARGIN
INK = colors.HexColor("#213547")
TEAL = colors.HexColor("#11666a")
PALE = colors.HexColor("#edf5f4")
MUTED = colors.HexColor("#536577")
DATE = datetime.now(UTC).strftime("%Y-%m-%d")

SOURCES = {
    "overview": ["docs/project_overview.md", "docs/results/overview-results.md"],
    "technical": [
        "docs/architecture.md",
        "docs/technology.md",
        "docs/module_reference.md",
        "docs/models.md",
        "docs/aws.md",
        "docs/testing.md",
        "docs/results/results.md",
        "evaluation/README.md",
        "docs/learning_path.md",
        "docs/operations.md",
        "docs/interview_walkthrough.md",
        "docs/data_sources.md",
    ],
}


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def software_inventory():
    locked = tomllib.loads((ROOT / "uv.lock").read_text())
    python_versions = {package["name"]: package["version"] for package in locked["package"]}
    packages = json.loads((ROOT / "frontend/package-lock.json").read_text())["packages"]
    roles = {
        "fastapi": "Required API framework",
        "uvicorn": "Required ASGI HTTP server",
        "pydantic": "Required typed data contracts",
        "pydantic-settings": "Required environment settings",
        "sqlalchemy": "Required database mapping/transactions",
        "alembic": "Required database migrations",
        "psycopg": "Required PostgreSQL driver",
        "boto3": "Optional live AWS client; required adapter dependency",
        "openai": "Optional live provider; required SDK adapter dependency",
        "anthropic": "Optional live provider; required SDK adapter dependency",
        "httpx": "Required bounded HTTP client and SDK test transport",
        "jsonschema": "Required JSON Schema validation",
        "pytest": "Development test runner",
        "hypothesis": "Development generated-input tests",
        "ruff": "Development lint/format checks",
        "mypy": "Development Python type checks",
        "reportlab": "Documentation PDF generation only",
        "pymupdf": "Documentation PDF validation/rendering only",
        "pillow": "Documentation contact sheets only",
    }
    records = [
        {"tool": name, "version": python_versions[name], "role": role, "source": "uv.lock"}
        for name, role in roles.items()
    ]
    for name, role in {
        "react": "Required browser UI framework",
        "react-dom": "Required DOM renderer",
        "typescript": "Development browser type checker",
        "vite": "Development asset build/server",
        "@playwright/test": "Development browser automation",
        "prettier": "Development source formatter",
        "lucide-react": "Required interface icons",
    }.items():
        records.append(
            {
                "tool": name,
                "version": packages["node_modules/" + name]["version"],
                "role": role,
                "source": "frontend/package-lock.json",
            }
        )
    for item in json.loads((ROOT / "docs/tool_inventory.json").read_text()):
        records.append(
            {
                "tool": item["tool"],
                "version": item["version"],
                "role": {
                    "conftest": "Required deterministic guard fixtures",
                    "k6": "Required measured workload profiles",
                    "terraform": "Optional isolated AWS scaffold",
                }[item["tool"]],
                "source": item["source_url"],
            }
        )
    provider_lock = (ROOT / "infra/aws-demo/.terraform.lock.hcl").read_text()
    records.extend(
        [
            {
                "tool": "Python",
                "version": ".".join(map(str, sys.version_info[:3])),
                "role": "Required; application range 3.12.x",
                "source": "Current docs build interpreter / uv.lock",
            },
            {
                "tool": "uv",
                "version": "0.12.23",
                "role": "Required frozen dependency installer",
                "source": "Dockerfile and CI",
            },
            {
                "tool": "Node",
                "version": "22 (container/LTS setup); host 25.7.0",
                "role": "Frontend build; not a backend runtime",
                "source": "frontend/Dockerfile and measured host",
            },
            {
                "tool": "PostgreSQL",
                "version": "17.6-alpine",
                "role": "Required persistent transactional database",
                "source": "compose.yaml",
            },
            {
                "tool": "nginx",
                "version": "1.28-alpine",
                "role": "Container static web/proxy server",
                "source": "frontend/Dockerfile",
            },
            {
                "tool": "Terraform AWS provider",
                "version": re.search(r'version\s*=\s*"([^"]+)"', provider_lock).group(1),
                "role": "Optional isolated AWS scaffold; not deployed",
                "source": "infra/aws-demo/.terraform.lock.hcl",
            },
        ]
    )
    for name, args in (
        ("Docker", ["docker", "--version"]),
        ("Compose", ["docker", "compose", "version", "--short"]),
    ):
        try:
            version = subprocess.run(
                args, check=True, capture_output=True, text=True, timeout=10
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            version = None
        records.append(
            {
                "tool": name,
                "version": version,
                "role": "Required local container runtime; host version observed, not package-locked",
                "source": "Local version command",
            }
        )
    inventory = {
        "schema_version": 1,
        "recorded_at": DATE,
        "software": records,
        "deferred": ["LangGraph", "Kubernetes", "vector database", "trained router"],
    }
    save(ROOT / "docs/software_inventory.json", inventory)
    return inventory


def fonts_and_styles():
    fonts = Path(reportlab.__file__).parent / "fonts"
    for name, filename in (
        ("Vera", "Vera.ttf"),
        ("Vera-Bold", "VeraBd.ttf"),
        ("Vera-Italic", "VeraIt.ttf"),
        ("Vera-BoldItalic", "VeraBI.ttf"),
    ):
        pdfmetrics.registerFont(TTFont(name, str(fonts / filename)))
    pdfmetrics.registerFontFamily(
        "Vera", normal="Vera", bold="Vera-Bold", italic="Vera-Italic", boldItalic="Vera-BoldItalic"
    )
    license_path = ROOT / "docs/licenses/bitstream-vera-license.txt"
    license_path.parent.mkdir(parents=True, exist_ok=True)
    license_path.write_bytes((fonts / "bitstream-vera-license.txt").read_bytes())
    base = ParagraphStyle(
        "body",
        fontName="Vera",
        fontSize=9.7,
        leading=14,
        textColor=INK,
        spaceAfter=8,
        splitLongWords=True,
        allowWidows=0,
        allowOrphans=0,
    )
    return {
        "body": base,
        "h1": ParagraphStyle(
            "h1",
            parent=base,
            fontName="Vera-Bold",
            fontSize=20,
            leading=25,
            textColor=TEAL,
            spaceBefore=4,
            spaceAfter=15,
            keepWithNext=True,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base,
            fontName="Vera-Bold",
            fontSize=13,
            leading=18,
            spaceBefore=12,
            spaceAfter=6,
            keepWithNext=True,
        ),
        "h3": ParagraphStyle(
            "h3",
            parent=base,
            fontName="Vera-Bold",
            fontSize=10.5,
            leading=15,
            spaceBefore=9,
            spaceAfter=5,
            keepWithNext=True,
        ),
        "small": ParagraphStyle("small", parent=base, fontSize=8.3, leading=11.5, textColor=MUTED),
        "code": ParagraphStyle(
            "code",
            parent=base,
            fontSize=8.5,
            leading=12,
            backColor=PALE,
            borderPadding=7,
            spaceBefore=3,
            spaceAfter=9,
        ),
        "cell": ParagraphStyle("cell", parent=base, fontSize=8.5, leading=12, spaceAfter=1),
        "cell_header": ParagraphStyle(
            "cell_header",
            parent=base,
            fontName="Vera-Bold",
            fontSize=8.5,
            leading=12,
            textColor=colors.white,
            spaceAfter=1,
        ),
        "toc": ParagraphStyle(
            "toc",
            parent=base,
            fontSize=10,
            leading=16,
            leftIndent=0,
            firstLineIndent=0,
            rightIndent=20,
            spaceBefore=5,
        ),
    }


def slug(value):
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def bookmark(source, heading=""):
    value = str(source.relative_to(ROOT)) + "#" + heading
    return "ref-" + hashlib.sha256(value.encode()).hexdigest()[:18]


def inline(text, source, included):
    pieces = re.split(r"(`[^`]+`|\[[^\]]+\]\([^\s)]+\)|\*\*[^*]+\*\*)", text)
    output = []
    for piece in pieces:
        if piece.startswith("`") and piece.endswith("`"):
            output.append(f'<font size="8.6" color="#23585b">{escape(piece[1:-1])}</font>')
        elif piece.startswith("**") and piece.endswith("**"):
            output.append("<b>" + escape(piece[2:-2]) + "</b>")
        elif match := re.fullmatch(r"\[([^\]]+)\]\(([^)]+)\)", piece):
            label, target = match.groups()
            if target.startswith("https://"):
                link = target
            else:
                path_text, _, anchor = target.partition("#")
                destination = (source.parent / path_text).resolve() if path_text else source
                link = (
                    "#" + bookmark(destination, anchor)
                    if destination in included
                    else os.path.relpath(destination, PDF_DIR).replace(os.sep, "/")
                )
            output.append(
                f'<link href="{escape(link, {chr(34): "&quot;"})}" color="#11666a"><u>{escape(label)}</u></link>'
            )
        else:
            output.append(escape(piece))
    return "".join(output)


class Diagram(Flowable):
    def __init__(self, aws=False):
        super().__init__()
        self.width = CONTENT
        self.height = 210 if aws else 300
        self.aws = aws

    def draw(self):
        canvas = self.canv

        def box(x, y, width, title, detail):
            canvas.setFillColor(PALE)
            canvas.setStrokeColor(TEAL)
            canvas.roundRect(x, y, width, 48, 7, fill=1, stroke=1)
            canvas.setFillColor(INK)
            canvas.setFont("Vera-Bold", 8.6)
            canvas.drawCentredString(x + width / 2, y + 30, title)
            canvas.setFont("Vera", 7.8)
            canvas.drawCentredString(x + width / 2, y + 14, detail)

        def arrow(x1, y1, x2, y2):
            import math

            canvas.setStrokeColor(TEAL)
            canvas.setFillColor(TEAL)
            canvas.setLineWidth(1.2)
            canvas.line(x1, y1, x2, y2)
            angle = math.atan2(y2 - y1, x2 - x1)
            path = canvas.beginPath()
            path.moveTo(x2, y2)
            for offset in (-0.5, 0.5):
                path.lineTo(x2 - 6 * math.cos(angle + offset), y2 - 6 * math.sin(angle + offset))
            path.close()
            canvas.drawPath(path, fill=1, stroke=0)

        if self.aws:
            w = (CONTENT - 32) / 3
            box(0, 140, w, "Credential chain", "Local SSO / temporary role")
            box(w + 16, 140, w, "STS identity", "Expected account verified")
            box(2 * w + 32, 140, w, "Bounded collector", "One region / service")
            arrow(w, 164, w + 16, 164)
            arrow(2 * w + 16, 164, 2 * w + 32, 164)
            box(0, 48, w, "ECS", "Task identity + allocation")
            box(w + 16, 48, w, "CloudWatch", "Metrics + bounded logs")
            box(2 * w + 32, 48, w, "Observation", "Status, window, origin")
            arrow(2.5 * w + 32, 140, 2.5 * w + 32, 96)
            arrow(w / 2, 96, 2.5 * w + 32, 140)
            arrow(1.5 * w + 16, 96, 2.5 * w + 32, 140)
            caption = "Read-only adapter code tested with mocks; no AWS deployment or live smoke performed."
        else:
            w = (CONTENT - 36) / 3
            x = [0, w + 18, 2 * w + 36]
            box(x[0], 235, w, "Plan + scope map", "Bounded sanitized import")
            box(x[1], 235, w, "Contract + guard", "Trusted revision + template")
            box(x[2], 235, w, "Evidence + rates", "Origin, time, workload pins")
            box(x[1], 140, w, "Shared engine", "Python + leased worker")
            for position in x:
                arrow(position + w / 2, 235, x[1] + w / 2, 188)
            box(x[0], 50, w, "PostgreSQL", "Jobs, evidence, ledger")
            box(x[1], 50, w, "UI / CLI / CI report", "Export + operator outcome")
            box(x[2], 140, w, "Optional AI adapters", "Two attempts; no tools")
            box(x[2], 50, w, "Output validation", "Facts, schema, citations")
            arrow(x[0] + w, 80, x[1], 153)
            arrow(x[1] + w / 2, 140, x[1] + w / 2, 98)
            arrow(x[1] + w, 164, x[2], 164)
            arrow(x[2] + w / 2, 140, x[2] + w / 2, 98)
            arrow(x[2], 74, x[1] + w, 74)
            caption = "Human review > draft fixtures > separate protected source review. No app deployment."
        canvas.setFillColor(MUTED)
        canvas.setFont("Vera", 8)
        canvas.drawCentredString(CONTENT / 2, 16, caption)


class Guide(BaseDocTemplate):
    def __init__(self, path, title, styles):
        super().__init__(
            str(path),
            pagesize=A4,
            leftMargin=MARGIN,
            rightMargin=MARGIN,
            topMargin=50,
            bottomMargin=46,
            title=title,
            author="ProofOps project",
            subject="Implemented local review workflow and honest verification",
            pageCompression=1,
        )
        self.guide_title = title
        self.styles = styles
        self.addPageTemplates(
            PageTemplate(
                id="body",
                frames=[
                    Frame(
                        MARGIN,
                        46,
                        CONTENT,
                        HEIGHT - 96,
                        leftPadding=0,
                        rightPadding=0,
                        topPadding=0,
                        bottomPadding=0,
                    )
                ],
                onPage=self.decorate,
            )
        )

    def decorate(self, canvas, document):
        canvas.saveState()
        canvas.setFont("Vera", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(MARGIN, HEIGHT - 28, "PROOFOPS / " + self.guide_title)
        canvas.setStrokeColor(colors.HexColor("#d6e5e3"))
        canvas.line(MARGIN, 33, WIDTH - MARGIN, 33)
        canvas.drawString(MARGIN, 20, f"Local implementation • {DATE} • v0.1.0")
        canvas.drawRightString(WIDTH - MARGIN, 20, str(document.page))
        canvas.restoreState()

    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and hasattr(flowable, "anchor_key"):
            level = flowable.outline_level
            title = flowable.getPlainText()
            self.canv.bookmarkPage(flowable.anchor_key)
            self.canv.addOutlineEntry(title, flowable.anchor_key, level=level, closed=False)
            if level == 0:
                self.notify("TOCEntry", (0, title, self.page, flowable.anchor_key))


def table(rows, styles, source, included):
    count = len(rows[0])
    if count == 2:
        widths = [CONTENT * 0.31, CONTENT * 0.69]
    elif count == 3 and rows[0][0].lower() == "id":
        widths = [40, CONTENT * 0.51, CONTENT - 40 - CONTENT * 0.51]
    else:
        widths = [CONTENT / count] * count
    formatted = [
        [
            Paragraph(
                inline(cell, source, included), styles["cell_header" if index == 0 else "cell"]
            )
            for cell in row
        ]
        for index, row in enumerate(rows)
    ]
    result = Table(
        formatted, colWidths=widths, repeatRows=1, hAlign="LEFT", spaceBefore=4, spaceAfter=11
    )
    result.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), TEAL),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f0f6f5"), colors.white]),
                ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#d6e5e3")),
            ]
        )
    )
    return result


def markdown(source, styles, included):
    lines = source.read_text().splitlines()
    story, index, first_heading = [], 0, True
    while index < len(lines):
        line = lines[index].strip()
        if not line or line.startswith("<!--"):
            index += 1
            continue
        if line.startswith("```"):
            language = line[3:]
            index += 1
            code = []
            while index < len(lines) and not lines[index].strip().startswith("```"):
                code.append(lines[index])
                index += 1
            index += 1
            if language == "mermaid":
                story.append(Diagram(aws=source.name == "aws.md"))
            else:
                escaped = "<br/>".join(escape(item).replace("  ", "&#160;&#160;") for item in code)
                story.append(Paragraph(escaped, styles["code"]))
            continue
        if line.startswith("|"):
            rows = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                cells = [part.strip() for part in lines[index].strip().strip("|").split("|")]
                if not all(re.fullmatch(r"[-: ]+", cell) for cell in cells):
                    rows.append(cells)
                index += 1
            if (
                story
                and isinstance(story[-1], Paragraph)
                and story[-1].style.name in {"h1", "h2", "h3"}
            ):
                table_heading = story.pop()
                table_heading.keepWithNext = False
                story.extend([CondPageBreak(180), table_heading])
            story.append(table(rows, styles, source, included))
            continue
        if match := re.match(r"^(#{1,3})\s+(.+)", line):
            level, title = len(match[1]), match[2]
            heading = Paragraph(inline(title, source, included), styles[f"h{level}"])
            heading.anchor_key = bookmark(source, "" if first_heading else slug(title))
            heading.outline_level = min(level - 1, 1)
            first_heading = False
            story.append(heading)
            index += 1
            continue
        paragraph = [line]
        index += 1
        if re.match(r"^(- |\d+\. )", line):
            while index < len(lines) and lines[index].startswith("  "):
                paragraph.append(lines[index].strip())
                index += 1
        else:
            while (
                index < len(lines)
                and lines[index].strip()
                and not re.match(r"^(#|\||```|- |\d+\. )", lines[index].strip())
            ):
                paragraph.append(lines[index].strip())
                index += 1
        text = " ".join(paragraph)
        if text.startswith("- "):
            text = "• " + text[2:]
        story.append(Paragraph(inline(text, source, included), styles["body"]))
    return story


def heading(text, key, styles):
    item = Paragraph(text, styles["h1"])
    item.anchor_key = key
    item.outline_level = 0
    return item


def build(kind, filename, title, styles, inventory):
    included = {(ROOT / name).resolve() for name in SOURCES[kind]}
    story = [Spacer(1, 60)]
    cover = ParagraphStyle("cover", parent=styles["h1"], fontSize=33, leading=41, spaceAfter=20)
    story += [
        Paragraph("ProofOps", cover),
        Paragraph(title, styles["h1"]),
        Spacer(1, 18),
        Paragraph("Evidence for a specific infrastructure change", styles["h2"]),
        Paragraph(
            "Working local software. Synthetic review fixtures. Measured local Docker experiments. Live AWS and paid model evaluation unrun.",
            styles["body"],
        ),
        Spacer(1, 12),
        Paragraph(f"Build date: {DATE} · Application version 0.1.0", styles["body"]),
        Paragraph(
            "Editable Markdown, machine inventories and saved result extracts accompany this searchable guide. Source links and section links are clickable.",
            styles["body"],
        ),
    ]
    story += [Spacer(1, 20), Diagram()]
    if kind == "overview":
        overview_link = bookmark(ROOT / "docs/project_overview.md")
        results_link = bookmark(ROOT / "docs/results/overview-results.md")
        story.append(
            Paragraph(
                f'<link href="#{overview_link}" color="#11666a">Read the overview</link> · <link href="#{results_link}" color="#11666a">Inspect recorded results</link>',
                styles["body"],
            )
        )
        story.append(PageBreak())
    else:
        story += [PageBreak(), Paragraph("Contents", styles["h1"])]
        toc = TableOfContents()
        toc.levelStyles = [styles["toc"]]
        story += [toc, PageBreak()]
    for position, name in enumerate(SOURCES[kind]):
        if position:
            story.extend(
                [
                    PageBreak() if name == "docs/data_sources.md" else CondPageBreak(240),
                    Spacer(1, 18),
                ]
            )
        source = ROOT / name
        story.extend(markdown(source, styles, included))
        if kind == "technical" and name == "docs/technology.md":
            inventory_heading = heading("Actual software inventory", "software-inventory", styles)
            inventory_heading.keepWithNext = False
            story += [
                CondPageBreak(240),
                Spacer(1, 18),
                inventory_heading,
            ]
            rows = [["Tool", "Version", "Role"]] + [
                [item["tool"], item["version"] or "Unavailable", item["role"]]
                for item in inventory["software"]
            ]
            story.append(table(rows, styles, source, included))
        if kind == "technical" and name == "docs/models.md":
            model_inventory = json.loads((ROOT / "docs/model_inventory.json").read_text())
            story.append(Paragraph("Configured model slots", styles["h2"]))
            rows = [["Slot / provider", "Exact model and state", "Measurements / prices"]]
            for item in model_inventory["configuration_slots"]:
                rows.append(
                    [
                        item["slot"] + " / " + item["provider_default"],
                        "ID: null; " + item["configuration_state"],
                        "All live cost, latency, quality and model prices: null. "
                        + item["unknown_reason"],
                    ]
                )
            story.append(table(rows, styles, source, included))
            story.append(
                Paragraph(
                    "No configured_models entries exist. SDK tests are mocked; these slots are not evaluated model choices.",
                    styles["body"],
                )
            )
    path = PDF_DIR / filename
    Guide(path, title, styles).multiBuild(story)
    return path


def main():
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    missing = [name for names in SOURCES.values() for name in names if not (ROOT / name).is_file()]
    if missing:
        raise SystemExit("Missing documentation inputs: " + ", ".join(sorted(set(missing))))
    inventory = software_inventory()
    styles = fonts_and_styles()
    outputs = [
        build("overview", "ProofOps_Project_Overview.pdf", "Project overview", styles, inventory),
        build(
            "technical",
            "ProofOps_Technical_and_Learning_Guide.pdf",
            "Technical and learning guide",
            styles,
            inventory,
        ),
    ]
    source_files = set(name for names in SOURCES.values() for name in names) | {
        "docs/model_inventory.json",
        "docs/software_inventory.json",
        "scripts/build_docs.py",
    }
    manifest = {
        "schema_version": 1,
        "built_at": datetime.now(UTC).isoformat(),
        "sources": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in sorted(source_files)
        },
        "outputs": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in outputs
        },
    }
    save(PDF_DIR / "build_manifest.json", manifest)
    print(
        json.dumps(
            {
                "pdfs": [str(path.relative_to(ROOT)) for path in outputs],
                "editable_sources": len(source_files),
            }
        )
    )


if __name__ == "__main__":
    main()
