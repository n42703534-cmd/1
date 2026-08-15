# Academic Figure Skill Asset Confirmation (verified against available project assets)
# (a) station-geometry input -> cad_geometry/longyang_station_20260815.dxf -> param inherit
# (b) AA* method pipeline -> supplied method text + project implementation -> param inherit
# (c) Pathfinder route allocation -> cad_geometry/pathfinder_longyang_overview_20260815.png -> native run
# (d) Pathfinder completion profile -> figures/fig2_pathfinder_high_load_validation.png -> native run
# RULE: "native run" = load source raster via Image.open().ax.imshow().
#       "param inherit" = drawing function below that copies Class A/B/C values.

"""A deliberately single-reference architecture figure using Yang et al. Fig. 1 as the layout backbone."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, Polygon, Rectangle
from PIL import Image


WORK = Path(__file__).resolve().parent
OUT = WORK / "figures"
OUT.mkdir(parents=True, exist_ok=True)
BASE = OUT / "fig_aa_method_architecture_yangfig1_en"
CAD_DIR = WORK / "cad_geometry"
DXF_PATH = CAD_DIR / "longyang_station_20260815.dxf"
PF_PATH = CAD_DIR / "pathfinder_longyang_overview_20260815.png"
PF_PROFILE_PATH = OUT / "fig2_pathfinder_high_load_validation.png"

sys.path.insert(0, str(WORK))
import build_aa_method_architecture_real_en as cad_source  # noqa: E402


MM = 1 / 25.4
FIG_W_MM, FIG_H_MM = 183, 101
FONT = "Arial"

INK = "#25323C"
GRAY = "#66727A"
BLUE = "#426FA8"
BLUE_LIGHT = "#AFC3E2"
BLUE_PALE = "#EDF4FB"
ORANGE = "#D96F1D"
ORANGE_LIGHT = "#F7D7BE"
ORANGE_PALE = "#FDF1E7"
GOLD = "#F0BF3E"
GOLD_LIGHT = "#FBE7A3"
TEAL = "#4B8C83"
PURPLE = "#7B67A2"
GREEN = "#739A78"
GREEN_LIGHT = "#DCEBDD"
WHITE = "#FFFFFF"

mpl.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": [FONT, "Helvetica", "DejaVu Sans"],
    "font.size": 7, "text.color": INK, "pdf.fonttype": 42, "ps.fonttype": 42,
    "svg.fonttype": "none", "savefig.facecolor": WHITE, "savefig.edgecolor": WHITE,
})


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def rect(ax, x, y, w, h, *, edge=INK, fill=WHITE, lw=0.75, dashed=False, z=1):
    ax.add_patch(Rectangle((x, y), w, h, transform=ax.transAxes, facecolor=fill, edgecolor=edge,
                           linewidth=lw, linestyle=(0, (5, 3)) if dashed else "-", zorder=z))


def label(ax, x, y, value, *, fs=6, weight="normal", color=INK, ha="center", va="center", **kw):
    ax.text(x, y, value, transform=ax.transAxes, fontsize=fs, fontweight=weight, color=color,
            ha=ha, va=va, **kw)


def arrow(ax, a, b, *, color=GRAY, lw=0.75, size=6):
    ax.add_patch(FancyArrowPatch(a, b, transform=ax.transAxes, arrowstyle="-|>", mutation_scale=size,
                                 linewidth=lw, color=color, shrinkA=1.5, shrinkB=1.5, zorder=8))


def chevrons(ax, x, y, n=3):
    for i in range(n):
        xx = x + i * 0.015
        ax.add_patch(Polygon([[xx, y], [xx + .008, y], [xx + .015, y + .025],
                              [xx + .008, y + .050], [xx, y + .050], [xx + .008, y + .025]],
                             transform=ax.transAxes, facecolor=BLUE, edgecolor="none", zorder=8))


def header_card(ax, x, y, w, h, title, color):
    rect(ax, x, y, w, h, edge=color, fill=WHITE, lw=.7)
    rect(ax, x, y + h - .035, w, .035, edge=color, fill=color, lw=0)
    label(ax, x + w/2, y + h - .0175, title, fs=5.5, weight="bold", color=WHITE)


def parameter_box(ax, x, y, w, label_text, color):
    rect(ax, x, y, w, .080, edge=color, fill=WHITE, lw=.7, dashed=True)
    for i, line in enumerate(label_text):
        yy = y + .061 - .021 * i
        rect(ax, x + .014, yy - .006, .009, .012, edge=color, fill=WHITE, lw=.4)
        label(ax, x + .030, yy, line, fs=4.4, ha="left")


def timeline(ax, x, y, w, labels=True):
    ax.plot([x, x + w], [y, y], transform=ax.transAxes, color=BLUE, linewidth=.9)
    for frac, txt, color in [(0.02, "$t_0$", BLUE), (.43, "a", ORANGE), (.70, "a", ORANGE), (.96, "$\tau$", PURPLE)]:
        xx = x + w * frac
        ax.plot([xx, xx], [y - .015, y + .020], transform=ax.transAxes, color=color, linewidth=1.0)
        if labels:
            label(ax, xx, y - .030, txt, fs=4.6, color=color)


def mini_service(ax, x, y, w, h):
    names = ["flow", "queue", "service"]
    for i, name in enumerate(names):
        xx = x + .06*w + i * .31*w
        rect(ax, xx, y + .36*h, .20*w, .25*h, edge=TEAL, fill=WHITE, lw=.55)
        label(ax, xx + .10*w, y + .485*h, name, fs=4.25)
        if i < 2:
            arrow(ax, (xx + .20*w, y + .485*h), (xx + .29*w, y + .485*h), color=TEAL, lw=.55, size=4)


def mini_path(ax, x, y, w, h):
    p = [(x+.07*w,y+.50*h),(x+.40*w,y+.80*h),(x+.40*w,y+.20*h),(x+.73*w,y+.50*h),(x+.94*w,y+.50*h)]
    for a,b,c in [(p[0],p[1],BLUE),(p[0],p[2],GRAY),(p[1],p[3],BLUE),(p[2],p[3],GRAY),(p[3],p[4],ORANGE)]:
        ax.plot([a[0],b[0]],[a[1],b[1]],transform=ax.transAxes,color=c,linewidth=.9)
    for px,py in p:
        ax.scatter([px],[py],transform=ax.transAxes,s=10,facecolor=WHITE,edgecolor=BLUE,linewidth=.7,zorder=5)


def mini_allocation(ax, x, y, w, h):
    starts = [y+h*.25,y+h*.50,y+h*.75]; ends = [y+h*.70,y+h*.43,y+h*.18]
    for yy in starts: ax.scatter([x+w*.13],[yy],transform=ax.transAxes,s=11,facecolor=ORANGE,edgecolor=WHITE,linewidth=.3,zorder=5)
    for yy in ends: ax.scatter([x+w*.87],[yy],transform=ax.transAxes,s=11,facecolor=GREEN,edgecolor=WHITE,linewidth=.3,zorder=5)
    for a,b in zip(starts,ends): arrow(ax,(x+w*.20,a),(x+w*.80,b),color=PURPLE,lw=.6,size=4)


def build():
    fig = plt.figure(figsize=(FIG_W_MM*MM, FIG_H_MM*MM), facecolor=WHITE)
    ax = fig.add_axes([0,0,1,1]); ax.set_xlim(0,1); ax.set_ylim(0,1); ax.axis("off")

    # Yang Fig. 1 backbone: compact left inputs, one strict central pipeline, compact right outputs.
    rect(ax,.025,.100,.190,.760,edge=ORANGE,fill=WHITE,lw=.7,dashed=True)
    rect(ax,.235,.090,.550,.780,edge=ORANGE,fill=WHITE,lw=.7,dashed=True)
    rect(ax,.805,.100,.170,.760,edge=ORANGE,fill=WHITE,lw=.7,dashed=True)

    # Left input strip — two evidence cards only.
    header_card(ax,.040,.530,.160,.245,"Station geometry",BLUE)
    cad_ax=ax.inset_axes([.050,.556,.140,.165]); cad_source.render_cad(cad_ax)
    label(ax,.120,.543,"DWG/DXF station overview",fs=4.3,color=GRAY)

    header_card(ax,.040,.245,.160,.235,"Evacuation demand",BLUE)
    label(ax,.120,.412,"Reference occupants",fs=4.9)
    label(ax,.120,.388,"+ train-arrival cohorts",fs=4.9,color=ORANGE)
    timeline(ax,.064,.315,.112)
    rect(ax,.064,.265,.112,.030,edge=BLUE,fill=BLUE_PALE,lw=.55)
    label(ax,.120,.280,"demand schedule",fs=4.45,weight="bold",color=BLUE)
    rect(ax,.078,.135,.084,.032,edge=BLUE,fill=BLUE_LIGHT,lw=.6)
    label(ax,.120,.151,"INPUT",fs=5.1,weight="bold")

    # Strict central block: all columns align vertically and share the same widths.
    label(ax,.510,.840,"ARRIVAL-TIME-AWARE PLANNING",fs=7.1,weight="bold")
    rect(ax,.255,.350,.510,.450,edge=INK,fill=WHITE,lw=.7)
    cols=[.272,.390,.508,.626]
    parameter_box(ax,cols[0],.715,.094,["capacity","service","receiving"],BLUE)
    parameter_box(ax,cols[1],.715,.094,["event time","cohort","commitment"],ORANGE)
    parameter_box(ax,cols[2],.715,.094,["queue state","ETA","density"],PURPLE)
    parameter_box(ax,cols[3],.715,.094,["route lock","exit set","update"],TEAL)
    for x in cols: arrow(ax,(x+.047,.713),(x+.047,.677),color=GRAY,lw=.6,size=5)

    stages=[("Dynamic flow\nstate",TEAL),("ETA queue\nforecast",ORANGE),("AA* path\nsearch",ORANGE),("Rolling route\nassignment",ORANGE)]
    for x,(name,color) in zip(cols,stages):
        rect(ax,x,.637,.094,.046,edge=color,fill=color,lw=.55)
        label(ax,x+.047,.660,name,fs=4.8,weight="bold",color=WHITE)
    for x in (.368,.486,.604): arrow(ax,(x,.660),(x+.020,.660),color=BLUE,lw=.8,size=5)

    # Lower local diagrams: same baseline, same size, no cross-module text.
    for x in cols: rect(ax,x,.405,.094,.205,edge=ORANGE,fill=WHITE,lw=.6)
    mini_service(ax,cols[0]+.008,.455,.078,.095); label(ax,cols[0]+.047,.424,"facility service",fs=4.35,color=GRAY)
    label(ax,cols[1]+.047,.556,"advance events",fs=4.55,weight="bold"); timeline(ax,cols[1]+.014,.505,.065); label(ax,cols[1]+.047,.458,r"$\hat Q_r(\tau)$",fs=6.7,color=ORANGE); label(ax,cols[1]+.047,.424,"queue at ETA",fs=4.35,color=GRAY)
    mini_path(ax,cols[2]+.008,.465,.078,.085); label(ax,cols[2]+.047,.424,"time-labelled paths",fs=4.15,color=GRAY)
    mini_allocation(ax,cols[3]+.008,.465,.078,.085); label(ax,cols[3]+.047,.424,"source → exit allocation",fs=3.95,color=GRAY)

    # Formula and executor sit outside the column grid, exactly once each.
    rect(ax,.272,.360,.448,.030,edge=PURPLE,fill="#F3EFF8",lw=.6)
    label(ax,.496,.375,r"$c_{uv}(\tau)$: movement + ETA queue + receiving + density exposure",fs=4.95)
    arrow(ax,(.496,.404),(.496,.392),color=GRAY,lw=.55,size=4)
    rect(ax,.325,.255,.340,.070,edge=GOLD,fill=GOLD_LIGHT,lw=.75)
    label(ax,.495,.292,"DYNAMIC EVACUATION-FLOW EXECUTION",fs=6.2,weight="bold")
    label(ax,.495,.270,"accepted routes → capacity competition → state update → route lock",fs=4.65)
    arrow(ax,(.496,.358),(.496,.327),color=GOLD,lw=1.0,size=7)
    rect(ax,.421,.155,.150,.038,edge=GOLD,fill=GOLD,lw=.55); label(ax,.496,.174,"EVACUATION PLAN",fs=5.2,weight="bold")
    arrow(ax,(.496,.253),(.496,.195),color=GOLD,lw=.8,size=6)
    rect(ax,.622,.155,.070,.038,edge=ORANGE,fill=ORANGE,lw=.55); label(ax,.657,.174,"EXPORT",fs=4.9,weight="bold",color=WHITE)

    # Right output strip — two actual output panels with equal visual weight.
    header_card(ax,.820,.530,.140,.245,"Route allocation",GREEN)
    pf_ax=ax.inset_axes([.833,.556,.114,.165]); pf_ax.imshow(Image.open(PF_PATH).convert("RGB")); pf_ax.set_xticks([]); pf_ax.set_yticks([])
    for spine in pf_ax.spines.values(): spine.set_color(GREEN); spine.set_linewidth(.5)
    label(ax,.890,.543,"Pathfinder execution",fs=4.2,color=GRAY)

    header_card(ax,.820,.245,.140,.235,"Completion profile",GREEN)
    if PF_PROFILE_PATH.exists():
        img=Image.open(PF_PROFILE_PATH).convert("RGB"); w,h=img.size; crop=img.crop((0,0,int(w*.52),int(h*.54)))
        prof_ax=ax.inset_axes([.833,.285,.114,.132]); prof_ax.imshow(crop); prof_ax.set_xticks([]); prof_ax.set_yticks([])
        for spine in prof_ax.spines.values(): spine.set_color(GREEN); spine.set_linewidth(.5)
    label(ax,.890,.260,"cross-model check",fs=4.2,color=GRAY)
    rect(ax,.848,.135,.084,.032,edge=GREEN,fill=GREEN_LIGHT,lw=.6); label(ax,.890,.151,"OUTPUT",fs=5.1,weight="bold")

    chevrons(ax,.215,.472); chevrons(ax,.785,.472)

    fig.savefig(BASE.with_suffix(".png"),dpi=320,facecolor=WHITE)
    fig.savefig(BASE.with_suffix(".pdf"),facecolor=WHITE)
    fig.savefig(BASE.with_suffix(".svg"),facecolor=WHITE)
    fig.savefig(BASE.with_suffix(".tiff"),dpi=600,facecolor=WHITE,pil_kwargs={"compression":"tiff_lzw"})
    plt.close(fig)

    manifest={
        "figure":str(BASE),"dimensions_mm":[FIG_W_MM,FIG_H_MM],"archetype":"schematic-led",
        "primary_visual_reference":"Yang et al. (2024) Fig. 1",
        "secondary_visual_references":["Wei et al. (2026) Fig. 1 colour hierarchy","Junfeng et al. (2026) Fig. 1 step hierarchy"],
        "sources":{"dwg_sha256":sha256(CAD_DIR / "longyang_station_20260815.dwg"),"dxf_sha256":sha256(DXF_PATH),"pathfinder_overview_sha256":sha256(PF_PATH),"completion_profile":str(PF_PROFILE_PATH)},
        "text_language":"English","quantitative_claims_added":False,
    }
    BASE.with_suffix(".source_manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    BASE.with_suffix(".caption.txt").write_text(
        "Fig. X. Arrival-time-aware evacuation planning and execution framework. Station geometry and evacuation demand feed a four-stage planning pipeline: dynamic flow state, ETA queue forecast, AA* path search and rolling route assignment. Accepted routes are executed through a common dynamic evacuation-flow model and exported to Pathfinder for route-allocation and completion-profile checking.\n",
        encoding="utf-8")
    return manifest


if __name__ == "__main__":
    print(json.dumps(build(),indent=2))
