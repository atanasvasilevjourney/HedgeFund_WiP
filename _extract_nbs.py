import json
from pathlib import Path

p = Path(r"C:\Users\atanas.vasilev\OneDrive - FlixBus GmbH (B2E B2B) - Prod\Desktop\algo")
lines = []
for nb_path in sorted(p.glob("*.ipynb")):
    nb = json.loads(nb_path.read_text(encoding="utf-8"))
    lines.append("=" * 90)
    size_kb = round(nb_path.stat().st_size / 1024, 1)
    lines.append(f"{nb_path.name} | cells: {len(nb['cells'])} | size_kb: {size_kb}")
    for i, cell in enumerate(nb["cells"]):
        src = "".join(cell.get("source", []))
        ctype = cell["cell_type"]
        n = len(src.splitlines())
        preview = src[:220].replace("\n", " | ")
        lines.append(f"[{i:02d}] {ctype:8s} ({n:4d} lines) {preview}")
    lines.append("")
    full = []
    for i, cell in enumerate(nb["cells"]):
        src = "".join(cell.get("source", []))
        full.append(f"\n\n########## CELL {i} ({cell['cell_type']}) ##########\n")
        full.append(src)
    Path(str(nb_path) + ".extract.md").write_text("".join(full), encoding="utf-8")

out = p / "_nb_extract.txt"
out.write_text("\n".join(lines), encoding="utf-8")
print("wrote", out)
