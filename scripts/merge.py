import csv, re, sys
def load(p): return {r["series"]: (r["operator"], r["circle"]) for r in csv.DictReader(open(p))}
def clean(v):
    parts = [p for p in dict.fromkeys(v.split("/")) if re.fullmatch(r"[A-Z]{2}", p)]
    return "/".join(parts)
w, g = load(sys.argv[1]), load(sys.argv[2])
out = csv.writer(sys.stdout)
out.writerow(["series", "operator", "circle", "source"])
for k in sorted(set(w) | set(g)):
    wo, wc = map(clean, w.get(k, ("", "")))
    go, gc = map(clean, g.get(k, ("", "")))
    if wo and wc: row = (wo, wc, "wikipedia")
    elif go and gc: row = (go, gc, "in-mob-prefix")
    elif wo or wc or go or gc: row = (wo or go, wc or gc, "partial")
    else: continue
    out.writerow([k, *row])
