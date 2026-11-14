# Ondos Module Design Document

Final version sent to the instructor on Nov 9, 2026 (CSE396 Group 2). This is the design the code follows.

| File | What |
| --- | --- |
| `CSE396 Group 2 - Ondos Module Design Document.pdf` | The document as submitted |
| `Ondos Module Design.md` | Source of the document (edit this, never the DOCX/PDF) |
| `ondos-diagrams/` | Figures used by the document |
| `diagrams-src/` | Mermaid sources of the figures |
| `build/` | Markdown → DOCX → PDF build |

## Build

Needs Python 3, pandoc and LibreOffice.

```
python build/lint.py "Ondos Module Design.md"
python build/build.py "Ondos Module Design.md" <workdir> <outdir>
```

Run `lint.py` first; its 16 known findings are false positives.

## Known difference from the repository

D.4 and D.5 say the Auto Controller code lives in the `ai/` folder. The repository uses `auto-controller/`, with the AI-only parts in `auto-controller/ai/`, so the paths `ai/common/`, `ai/models/` and `ai/requirements.txt` stay valid inside the module folder. To be corrected in the next revision of the document.
