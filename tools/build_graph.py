#!/usr/bin/env python3
"""Regenerate assets/commits-{dark,light}.svg from local git history.

GitHub's public graph cannot see private repositories, which is where nearly all
of the work lives. This walks every git repo on the machine, counts the commits
Darien authored, and draws the same calendar GitHub would have drawn if it could
see them.

    python3 tools/build_graph.py            # scans $HOME, writes both SVGs
    python3 tools/build_graph.py ~/code     # scan somewhere else

Re-run it whenever the graph looks stale, then commit the two SVGs.
"""
import subprocess, collections, datetime as dt, os, sys, re

HOME = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~")
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
AUTHORS = ("Darien", "darienbathalter", "bathalter")
SKIP = ("/node_modules/", "/Library/", "/.Trash/", "/vendor/", "/.venv")

CELL, GAP = 11, 3
PITCH = CELL + GAP
LEFT, TOP = 34, 60

THEMES = {
    "dark":  dict(bg="#08090A", ink="#ECEFEE", dim="#6B7570",
                  scale=["#101514", "#14432C", "#1C7A4A", "#2AA862", "#3BE07E"]),
    "light": dict(bg="#FFFFFF", ink="#1A1D1B", dim="#6B7570",
                  scale=["#EDF0EE", "#A9E9C4", "#5FD096", "#2AA862", "#177F4C"]),
}


def find_repos():
    out = subprocess.run(["find", HOME, "-maxdepth", "4", "-name", ".git", "-type", "d"],
                         capture_output=True, text=True)
    for line in out.stdout.splitlines():
        if not any(s in line for s in SKIP):
            yield line[:-len("/.git")]


def harvest():
    """Commits per day, deduped by (day, subject) so clones don't double-count."""
    days, per_repo, seen = collections.Counter(), collections.Counter(), set()
    for repo in find_repos():
        cmd = ["git", "-C", repo, "log", "--all", "--no-merges", "--regexp-ignore-case",
               "--date=format:%Y-%m-%d", "--pretty=%ad%x09%s"]
        cmd[6:6] = [f"--author={a}" for a in AUTHORS]
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        except subprocess.SubprocessError:
            continue
        if out.returncode:
            continue
        n = 0
        for line in out.stdout.splitlines():
            date, _, subject = line.partition("\t")
            key = (date, subject[:80])
            if key in seen:
                continue
            seen.add(key)
            days[date] += 1
            n += 1
        if n:
            per_repo[os.path.basename(repo)] = n
    return days, per_repo


def draw(days, repo_count, theme_name, end):
    T = THEMES[theme_name]
    start = end - dt.timedelta(days=364)
    start -= dt.timedelta(days=(start.weekday() + 1) % 7)   # rewind to Sunday

    streak = best = 0
    day = start
    while day <= end:
        streak = streak + 1 if days.get(day.isoformat()) else 0
        best = max(best, streak)
        day += dt.timedelta(days=1)

    window = {k: v for k, v in days.items() if start.isoformat() <= k <= end.isoformat()}
    total, active = sum(window.values()), len(window)

    def level(n):
        return 0 if not n else 1 if n <= 2 else 2 if n <= 5 else 3 if n <= 10 else 4

    cells, months, cols, seen_month = [], [], 0, None
    day = start
    while day <= end:
        col, row = (day - start).days // 7, (day.weekday() + 1) % 7
        cols = max(cols, col)
        n = days.get(day.isoformat(), 0)
        x, y = LEFT + col * PITCH, TOP + row * PITCH
        cells.append(f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2" '
                     f'fill="{T["scale"][level(n)]}"><title>{day}: {n} '
                     f'commit{"" if n == 1 else "s"}</title></rect>')
        if day.day <= 7 and day.month != seen_month:
            seen_month = day.month
            months.append(f'<text x="{x}" y="{TOP-8}" fill="{T["dim"]}" '
                          f'font-size="10">{day.strftime("%b")}</text>')
        day += dt.timedelta(days=1)

    W = LEFT + (cols + 1) * PITCH + 12
    gb = TOP + 7 * PITCH
    H = gb + 64
    labels = "".join(f'<text x="4" y="{TOP + r*PITCH + 9}" fill="{T["dim"]}" '
                     f'font-size="9">{lbl}</text>'
                     for r, lbl in ((1, "Mon"), (3, "Wed"), (5, "Fri")))
    lx = W - 12 - 5 * PITCH - 76
    legend = f'<text x="{lx}" y="{gb+19}" fill="{T["dim"]}" font-size="10">Less</text>'
    for i in range(5):
        legend += (f'<rect x="{lx+30+i*PITCH}" y="{gb+10}" width="{CELL}" height="{CELL}" '
                   f'rx="2" fill="{T["scale"][i]}"/>')
    legend += (f'<text x="{lx+30+5*PITCH+5}" y="{gb+19}" fill="{T["dim"]}" '
               f'font-size="10">More</text>')

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="ui-monospace,SFMono-Regular,Menlo,monospace">
<rect width="{W}" height="{H}" fill="{T['bg']}" rx="6"/>
<text x="{LEFT}" y="18" fill="{T['ink']}" font-size="12" font-weight="700">Commits authored, last 12 months</text>
<text x="{LEFT}" y="32" fill="{T['dim']}" font-size="10">every repository on my machine, public and private</text>
{''.join(months)}
{labels}
{''.join(cells)}
<text x="{LEFT}" y="{gb+19}" fill="{T['ink']}" font-size="11" font-weight="700">{total:,} commits</text>
<text x="{LEFT}" y="{gb+35}" fill="{T['dim']}" font-size="10">{repo_count} repositories &#183; {active} active days &#183; longest streak {best} days</text>
{legend}
</svg>'''
    open(os.path.join(OUT, f"commits-{theme_name}.svg"), "w").write(svg)
    return total, active, best


if __name__ == "__main__":
    days, per_repo = harvest()
    end = dt.date.today()
    for name in THEMES:
        total, active, best = draw(days, len(per_repo), name, end)
    print(f"{total:,} commits · {len(per_repo)} repositories · {active} active days · "
          f"longest streak {best} days")
    print("heaviest:", ", ".join(f"{r} ({n})" for r, n in per_repo.most_common(6)))
