"""Validate searchable PDF text/fonts/links and render every page for inspection."""

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

import pymupdf
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
PDF_DIR = ROOT / "docs/pdf"


def validate_markdown_links():
    broken = []
    documents = [
        ROOT / "README.md",
        *sorted((ROOT / "docs").glob("*.md")),
        ROOT / "evaluation/README.md",
    ]
    for document in documents:
        for target in re.findall(r"\[[^\]]+\]\(([^\s)]+)\)", document.read_text()):
            if urlparse(target).scheme or target.startswith("#"):
                continue
            path = (document.parent / unquote(target.split("#")[0])).resolve()
            if not path.exists():
                broken.append({"source": str(document.relative_to(ROOT)), "target": target})
    if broken:
        raise ValueError("Broken Markdown file links: " + json.dumps(broken))
    return len(documents)


def validate_pdf(path, expected, minimum_pages, maximum_pages):
    document = pymupdf.open(path)
    if not minimum_pages <= len(document) <= maximum_pages:
        raise ValueError(f"Unexpected page count in {path.name}: {len(document)}")
    text = "\n".join(page.get_text() for page in document)
    for phrase in expected:
        if phrase not in text:
            raise ValueError(f"Missing searchable text {phrase!r} in {path.name}")
    if not document.get_toc():
        raise ValueError("PDF has no bookmarks")
    destination = PDF_DIR / "rendered" / path.stem
    destination.mkdir(parents=True, exist_ok=True)
    for existing in destination.iterdir():
        match = re.fullmatch(r"(page|contact)-(\d+)\.png", existing.name)
        if match and existing.is_file() and not existing.is_symlink():
            maximum = len(document) if match[1] == "page" else (len(document) + 5) // 6
            if int(match[2]) > maximum:
                existing.unlink()
    fonts, links, pages, issues = {}, [], [], []
    for index, page in enumerate(document):
        body = page.get_text("dict")
        spans = [
            span
            for block in body["blocks"]
            if block["type"] == 0
            for line in block["lines"]
            for span in line["spans"]
        ]
        if len(page.get_text().strip()) < 100:
            issues.append(f"page {index + 1}: nearly empty")
        used_fonts = {span["font"] for span in spans}
        for span in spans:
            x0, y0, x1, y1 = span["bbox"]
            if x0 < 20 or y0 < 8 or x1 > page.rect.width - 20 or y1 > page.rect.height - 6:
                issues.append(
                    f"page {index + 1}: text outside safe page bounds: {span['text'][:50]}"
                )
            if span["size"] < 7.4:
                issues.append(f"page {index + 1}: unreadable font size {span['size']}")
            if "\ufffd" in span["text"] or "\x00" in span["text"]:
                issues.append(f"page {index + 1}: missing glyph")
        for font in page.get_fonts():
            name = font[3].split("+")[-1]
            if name in used_fonts:
                embedded = bool(document.extract_font(font[0])[3])
                fonts[name] = embedded
                if not embedded:
                    issues.append(f"page {index + 1}: used font {name} is not embedded")
        for link in page.get_links():
            if link["kind"] == pymupdf.LINK_GOTO:
                if not 0 <= link["page"] < len(document):
                    issues.append("Invalid internal PDF page link")
                links.append({"kind": "internal", "page": link["page"] + 1})
            elif "uri" in link:
                target = link["uri"]
                if target.startswith("https://"):
                    if not urlparse(target).netloc or " " in target:
                        issues.append("Malformed source URI")
                    links.append({"kind": "source", "uri": target})
                elif not (path.parent / unquote(target)).resolve().exists():
                    issues.append("Missing relative linked file: " + target)
                else:
                    links.append({"kind": "local", "uri": target})
            elif "file" in link:
                if not (path.parent / link["file"]).resolve().exists():
                    issues.append("Missing launched file: " + link["file"])
        image = destination / f"page-{index + 1:03d}.png"
        page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False).save(image)
        pages.append(image)
    if (
        not any(item["kind"] == "internal" for item in links)
        or sum(item["kind"] == "source" for item in links) < 5
    ):
        issues.append("Missing internal or source links")
    if not fonts:
        issues.append("No embedded text fonts detected")
    contact_sheets = []
    for offset in range(0, len(pages), 6):
        group = pages[offset : offset + 6]
        sheet = Image.new("RGB", (840, 1810), "#dce6e6")
        draw = ImageDraw.Draw(sheet)
        for position, page_path in enumerate(group):
            with Image.open(page_path) as rendered:
                rendered.thumbnail((400, 566))
                x, y = (position % 2) * 420 + 10, (position // 2) * 600 + 26
                sheet.paste(rendered, (x, y))
                draw.text(
                    (x, y - 19), f"{path.stem} | page {offset + position + 1}", fill="#213547"
                )
        filename = destination / f"contact-{offset // 6 + 1:02d}.png"
        sheet.save(filename)
        contact_sheets.append(str(filename.relative_to(ROOT)))
    return {
        "file": str(path.relative_to(ROOT)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "pages": len(document),
        "searchable_characters": len(text),
        "bookmarks": len(document.get_toc()),
        "embedded_fonts": fonts,
        "links": len(links),
        "rendered_pages": len(pages),
        "contact_sheets": contact_sheets,
        "issues": issues,
    }


def main():
    sources = validate_markdown_links()
    manifest = json.loads((PDF_DIR / "build_manifest.json").read_text())
    for name, expected in {**manifest["sources"], **manifest["outputs"]}.items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Documentation source/output changed since build: " + name)
    reports = [
        validate_pdf(
            PDF_DIR / "ProofOps_Project_Overview.pdf",
            ["ProofOps", "Recorded results", "synthetic", "AWS"],
            4,
            16,
        ),
        validate_pdf(
            PDF_DIR / "ProofOps_Technical_and_Learning_Guide.pdf",
            [
                "Module reference",
                "Actual software inventory",
                "Learning path",
                "T01",
                "T24",
                "unconfigured",
                "PostgreSQL",
            ],
            15,
            80,
        ),
    ]
    result = {
        "schema_version": 1,
        "markdown_documents_checked": sources,
        "pdfs": reports,
        "external_link_note": "URI syntax checked; no claim every external website is reachable offline.",
        "visual_review": "All pages rendered; inspect contact sheets and detailed pages before recording human layout approval.",
    }
    (PDF_DIR / "validation.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                "pdfs": [
                    {key: value for key, value in item.items() if key not in {"contact_sheets"}}
                    for item in reports
                ]
            }
        )
    )
    return 1 if any(item["issues"] for item in reports) else 0


if __name__ == "__main__":
    raise SystemExit(main())
