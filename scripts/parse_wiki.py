import re, sys, csv
text = open(sys.argv[1], encoding="utf-8").read()
sec = text.split("==Call No Series==")[1].split("== See also ==")[0]
cells = []
for line in sec.splitlines():
    line = line.strip()
    if not line.startswith("|") or line[:2] in ("|-", "|}", "|+"):
        continue
    cells += [c.strip() for c in line[1:].split("||")]
out, i = {}, 0
while i < len(cells):
    if re.fullmatch(r"[6-9]\d{3}", cells[i]):
        op = cells[i+1] if i+1 < len(cells) else ""
        ci = cells[i+2] if i+2 < len(cells) else ""
        if re.fullmatch(r"[6-9]\d{3}", op): op, ci, step = "", "", 1
        elif re.fullmatch(r"[6-9]\d{3}", ci): ci, step = "", 2
        else: step = 3
        out[cells[i]] = (op, ci)
        i += step
    else:
        i += 1
w = csv.writer(sys.stdout)
w.writerow(["series", "operator", "circle"])
for k in sorted(out):
    w.writerow([k, *out[k]])
