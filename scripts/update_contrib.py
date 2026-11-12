#!/usr/bin/env python3
"""Build an animated 12-month contribution chart (dark + light).

Data comes from the GitHub GraphQL contribution calendar. The SVG draws itself
on load and keeps a soft pulse on the latest week, so it stays alive without
looping something that would look glitchy.

Run it as the account owner (an Actions GITHUB_TOKEN undercounts: it cannot see
contributions to repos the app has no access to). Refresh it whenever you want
the window to roll forward:

    python scripts/update_contrib.py CaoLongyang
"""
import json
import os
import subprocess
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("ASSET_DIR", os.path.join(HERE, "..", "assets"))
W, H = 900, 250

QUERY = """
query($login:String!) {
  user(login:$login) {
    contributionsCollection {
      contributionCalendar { totalContributions weeks { contributionDays { date contributionCount } } }
    }
  }
}
"""


def fetch(login):
    token = os.environ.get("GITHUB_TOKEN") or subprocess.run(
        ["gh", "auth", "token"], capture_output=True, text=True).stdout.strip()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": login}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.load(r)
    return d["data"]["user"]["contributionsCollection"]["contributionCalendar"]


def smooth_path(pts):
    """Catmull-Rom -> cubic bezier, so weekly spikes read as a curve, not a saw."""
    if len(pts) < 2:
        return ""
    d = [f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"]
    for i in range(len(pts) - 1):
        p0 = pts[i - 1] if i > 0 else pts[i]
        p1, p2 = pts[i], pts[i + 1]
        p3 = pts[i + 2] if i + 2 < len(pts) else p2
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d.append(f"C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}")
    return " ".join(d)


def build(cal, theme):
    dark = theme == "dark"
    P = dict(
        line="#8B7CFF" if dark else "#6E56CF",
        line2="#38D9F5" if dark else "#0E7490",
        text="#8B949E" if dark else "#57606A",
        strong="#E6EDF3" if dark else "#1F2328",
        grid="#1E2A3A" if dark else "#E6E9EF",
        panel="none",
        border="#1E2A3A" if dark else "#E2E8F0",
    )

    weeks = [sum(d["contributionCount"] for d in w["contributionDays"]) for w in cal["weeks"]]
    total = cal["totalContributions"]
    n = len(weeks)
    peak = max(weeks) or 1

    x0, x1 = 46, W - 46
    y0, y1 = 104, 196          # plot top / baseline
    step = (x1 - x0) / (n - 1)
    pts = [(x0 + i * step, y1 - (v / peak) * (y1 - y0 - 8)) for i, v in enumerate(weeks)]

    line = smooth_path(pts)
    area = f"{line} L{pts[-1][0]:.1f},{y1} L{pts[0][0]:.1f},{y1} Z"
    # approximate path length for the draw-on animation
    plen = int(sum(((pts[i + 1][0] - pts[i][0]) ** 2 + (pts[i + 1][1] - pts[i][1]) ** 2) ** .5
                   for i in range(len(pts) - 1)) * 1.12)

    month_ticks = []
    seen = set()
    for i, w in enumerate(cal["weeks"]):
        m = w["contributionDays"][0]["date"][:7]
        if m not in seen and i < n - 2:
            seen.add(m)
            label = w["contributionDays"][0]["date"][5:7] + "/" + w["contributionDays"][0]["date"][2:4]
            month_ticks.append((x0 + i * step, label))

    lx, ly = pts[-1]

    o = []
    a = o.append
    a(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
      f'viewBox="0 0 {W} {H}" role="img" aria-label="Contribution chart">')
    a("<title>Contributions over the last 12 months</title>")
    a("<defs>")
    a(f'<linearGradient id="ar" x1="0" y1="0" x2="0" y2="1">'
      f'<stop offset="0" stop-color="{P["line"]}" stop-opacity=".42"/>'
      f'<stop offset="1" stop-color="{P["line"]}" stop-opacity="0"/></linearGradient>')
    a(f'<linearGradient id="ln" x1="0" y1="0" x2="1" y2="0">'
      f'<stop offset="0" stop-color="{P["line"]}"/><stop offset="1" stop-color="{P["line2"]}"/></linearGradient>')
    a("</defs>")
    a("<style>")
    a(f".lab{{font:600 10px ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;"
      f"letter-spacing:3.4px;fill:{P['text']}}}")
    a(f".big{{font:700 40px ui-sans-serif,-apple-system,'Segoe UI',Roboto,sans-serif;"
      f"letter-spacing:-1.4px;fill:{P['strong']}}}")
    a(f".sub{{font:400 11.5px ui-sans-serif,-apple-system,'Segoe UI',Roboto,sans-serif;fill:{P['text']}}}")
    a(f".tick{{font:400 9px ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;fill:{P['text']}}}")
    # static state is the finished state: if a client ignores CSS animations the
    # chart still shows a complete line instead of an empty panel
    a(f".ln{{fill:none;stroke:url(#ln);stroke-width:2.4;stroke-linecap:round;"
      f"stroke-dasharray:{plen};animation:draw 2.6s cubic-bezier(.4,0,.2,1) forwards}}")
    a(".area{animation:areafade 2.6s ease both}")
    a(".dot{animation:pulse 2.4s ease-out infinite;transform-box:fill-box;transform-origin:center}")
    a(f"@keyframes draw{{from{{stroke-dashoffset:{plen}}}to{{stroke-dashoffset:0}}}}")
    a("@keyframes areafade{0%,25%{opacity:0}100%{opacity:1}}")
    a("@keyframes pulse{0%{opacity:.55;transform:scale(.4)}70%{opacity:0;transform:scale(2.6)}"
      "100%{opacity:0;transform:scale(2.6)}}")
    a("@media (prefers-reduced-motion:reduce){.ln{animation:none;stroke-dashoffset:0}"
      ".area{animation:none;opacity:1}.dot{animation:none;opacity:0}}")
    a("</style>")

    a(f'<rect x=".5" y=".5" width="{W-1}" height="{H-1}" rx="18" fill="{P["panel"]}" '
      f'stroke="{P["border"]}"/>')
    a(f'<text class="lab" x="46" y="44">CONTRIBUTIONS · LAST 12 MONTHS</text>')
    a(f'<text class="big" x="44" y="88">{total}</text>')
    a(f'<text class="sub" x="{48 + len(str(total)) * 24}" y="86">contributions in the last year</text>')

    for gy in (y1, y0 + 30):
        a(f'<line x1="{x0}" y1="{gy}" x2="{x1}" y2="{gy}" stroke="{P["grid"]}" '
          f'stroke-width="1" stroke-dasharray="2 6"/>')

    a(f'<path class="area" d="{area}" fill="url(#ar)"/>')
    a(f'<path class="ln" d="{line}"/>')

    a(f'<circle class="dot" cx="{lx:.1f}" cy="{ly:.1f}" r="5" fill="{P["line2"]}" opacity=".55"/>')
    a(f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="3.4" fill="{P["line2"]}"/>')

    for tx, label in month_ticks:
        a(f'<text class="tick" x="{tx:.0f}" y="222" text-anchor="middle">{label}</text>')

    a("</svg>")
    dest = os.path.join(OUT, f"contrib-{theme}.svg")
    open(dest, "w", encoding="utf-8").write("\n".join(o))
    print(f"{dest}  total={total} weeks={n} peak={peak}")


if __name__ == "__main__":
    login = sys.argv[1] if len(sys.argv) > 1 else "CaoLongyang"
    cal = fetch(login)
    for t in ("dark", "light"):
        build(cal, t)
