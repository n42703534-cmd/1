# Academic Figure Skill Asset Confirmation (verified against user-supplied assets)
# (a) station geometry -> cad_geometry/longyang_station_20260815.dwg/.dxf -> param inherit
# (b) route-allocation execution -> cad_geometry/pathfinder_longyang_overview_20260815.png -> native run
# (c) dynamic network, ETA queue forecast, AA* evaluation, and rolling assignment -> network.py + single_path_routing.py -> param inherit
# RULE: "native run" = load pre-rendered PNG via Image.open().ax.imshow().
#       "param inherit" = drawing function below that copies Class A/B/C values.
#       No numerical outcome, result table, or unverified performance claim is drawn.

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyArrowPatch, Polygon, Rectangle
from PIL import Image


MM = 1 / 25.4
FIG_W_MM, FIG_H_MM = 183, 105
HERE = Path(__file__).resolve().parent
CAD_DIR = HERE / "cad_geometry"
PF_PATH = CAD_DIR / "pathfinder_longyang_overview_20260815.png"
BASE = HERE / "figures" / "fig_aa_method_architecture_template_style_en"

# Template-derived semantic palette: navy input, burnt-orange algorithm, forest-green output.
INK = "#18232F"
BLUE = "#184A86"
BLUE_LIGHT = "#EAF1FA"
ORANGE = "#C85408"
ORANGE_LIGHT = "#FFF0E5"
GREEN = "#27683C"
GREEN_LIGHT = "#EDF6EF"
PURPLE = "#7255A6"
GRAY = "#727B84"
LIGHT_GRAY = "#E6E9EC"
WHITE = "#FFFFFF"
GOLD = "#E7A922"

mpl.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 6,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
    "svg.fonttype": "none",
    "figure.facecolor": WHITE,
    "savefig.facecolor": WHITE,
})

sys.path.insert(0, str(HERE))
import build_aa_method_architecture_real_en as cad_source  # noqa: E402


def rect(ax, x, y, w, h, *, edge=INK, fill=WHITE, lw=.55, z=1):
    p = Rectangle((x, y), w, h, transform=ax.transAxes, edgecolor=edge, facecolor=fill,
                  linewidth=lw, joinstyle="round", zorder=z)
    ax.add_patch(p)
    return p


def text(ax, x, y, s, *, fs=5, color=INK, weight="normal", ha="center", va="center", z=6, style="normal"):
    return ax.text(x, y, s, transform=ax.transAxes, fontsize=fs, color=color, fontweight=weight,
                   fontstyle=style, ha=ha, va=va, zorder=z, linespacing=1.05)


def arrow(ax, start, end, *, color=INK, lw=.9, size=7, z=5, connection="arc3"):
    a = FancyArrowPatch(start, end, transform=ax.transAxes, arrowstyle="-|>", mutation_scale=size,
                        linewidth=lw, color=color, connectionstyle=connection, zorder=z)
    ax.add_patch(a)
    return a


def header(ax, x, y, w, title, color):
    rect(ax, x, y, w, .034, edge=color, fill=color, lw=.6)
    text(ax, x+w/2, y+.017, title, fs=5.55, color=WHITE, weight="bold")


def stage_box(ax, x, y, w, h, number, title):
    rect(ax, x, y, w, h, edge=ORANGE, fill=WHITE, lw=.6)
    rect(ax, x+.008, y+h-.038, .020, .026, edge=ORANGE, fill=ORANGE, lw=.4)
    text(ax, x+.018, y+h-.025, str(number), fs=5.6, color=WHITE, weight="bold")
    # Titles are left-aligned after the number badge so the badge never overlaps text.
    text(ax, x+.033, y+h-.025, title, fs=3.55, color=ORANGE, weight="bold", ha="left")


def inner_title(ax, x, y, w, h, s, *, edge=LIGHT_GRAY, fill="#FAFBFC", fs=3.25):
    rect(ax, x, y, w, h, edge=edge, fill=fill, lw=.4)
    text(ax, x+w/2, y+h-.010, s, fs=fs, weight="bold")


def people(ax, x, y, n, *, color=BLUE, spacing=.012, scale=1.0):
    for i in range(n):
        cx = x + i*spacing
        ax.add_patch(Circle((cx, y+.008*scale), .0032*scale, transform=ax.transAxes,
                            facecolor=color, edgecolor=color, zorder=5))
        rect(ax, cx-.0035*scale, y-.003*scale, .007*scale, .010*scale, edge=color, fill=color, lw=.2, z=5)


def facility_chain(ax, x, y, w):
    nodes = [(x+.01, y), (x+w*.40, y), (x+w*.72, y), (x+w-.01, y)]
    fills = ["#D7EDF8", "#FFF0C9", "#DDF0D8", "#FFD7D7"]
    labels = ["Passage", "Stair /\nEscalator", "Gate", "Exit"]
    for (cx, cy), fill, label in zip(nodes, fills, labels):
        ax.add_patch(Circle((cx,cy),.0072,transform=ax.transAxes,facecolor=fill,edgecolor=INK,linewidth=.45,zorder=4))
        text(ax,cx,cy-.018,label,fs=3.15)
    for a,b in zip(nodes[:-1],nodes[1:]):
        arrow(ax,(a[0]+.008,a[1]),(b[0]-.008,b[1]),lw=.55,size=4)


def draw_demand(ax, x, y, w, h):
    # Qualitative demand profile; no y values or outcome data.
    baseline = y+.028
    bar_w = w*.028
    vals = [.82,.67,.54,.43,.33,.23,.16,.10,.06]
    for i,v in enumerate(vals):
        rect(ax,x+.018+i*bar_w*1.32,baseline,bar_w,v*h*.55,edge=BLUE,fill=BLUE,lw=.1)
    text(ax,x+.012,baseline+h*.38,"Reference\nflow",fs=3.8,ha="left")
    for r, phase in enumerate([.60,.74,.48,.66]):
        yy=y+h*(.72-r*.15)
        text(ax,x+w*.49,yy,"Train cohort",fs=3.45,ha="left")
        for k in range(7):
            bh=(.18 + phase*max(0, 1-abs(k-3)/4))*h*.17
            rect(ax,x+w*(.72+k*.028),yy-.011, w*.014,bh,edge=BLUE,fill=BLUE,lw=.1)
    text(ax,x+w*.70,y+.014,"arrival schedule",fs=3.3,color=GRAY)


def draw_state_update(ax, x, y, w, h):
    inner_title(ax,x,y+h*.69,w,h*.25,"Accepted cohorts\n(route-locked)",fs=3.05)
    people(ax,x+w*.22,y+h*.75,4,color="#173E91",spacing=w*.16,scale=.9)
    text(ax,x+w*.82,y+h*.77,"…",fs=6,color=GRAY)
    inner_title(ax,x,y+h*.34,w,h*.29,"Shared facilities",fs=3.25)
    cx=x+w*.17; cy=y+h*.46
    pts=[(cx,cy),(x+w*.42,cy+h*.09),(x+w*.67,cy),(x+w*.84,cy+h*.10),(x+w*.53,cy-h*.10)]
    for p in pts: ax.add_patch(Circle(p,.0045,transform=ax.transAxes,facecolor="#F5E4B8",edgecolor=INK,linewidth=.35,zorder=4))
    for a,b in [(0,1),(1,2),(2,3),(0,4),(4,2),(1,4)]: arrow(ax,pts[a],pts[b],lw=.35,size=3,connection="arc3")
    inner_title(ax,x,y,w,h*.27,"Facility state variables",fs=3.15)
    labels=[r"$C$",r"$Q$",r"$R$",r"$\rho$"]
    for i,label in enumerate(labels):
        xx=x+w*(.125+i*.25)
        rect(ax,xx-w*.105,y+h*.045,w*.21,h*.115,edge=GRAY,fill="#F8F9FA",lw=.28)
        text(ax,xx,y+h*.103,label,fs=4.1,weight="bold")


def draw_queue_forecast(ax, x, y, w, h):
    inner_title(ax,x,y+h*.77,w,h*.17,"Event advancement",fs=3.2)
    yy=y+h*.84
    arrow(ax,(x+w*.12,yy),(x+w*.88,yy),lw=.6,size=4)
    for xx,label in [(x+w*.27,r"$\tau$"),(x+w*.66,r"$\tau+\Delta t$")]:
        ax.plot([xx,xx],[yy-.011,yy+.011],transform=ax.transAxes,color=INK,lw=.5); text(ax,xx,yy-.029,label,fs=3.6,style="italic")
    inner_title(ax,x,y+h*.46,w,h*.27,"Cohort ETA at\nshared facility",fs=3.0)
    fx=x+w*.81; fy=y+h*.55
    rect(ax,fx-w*.035,fy-h*.055,w*.07,h*.11,edge=INK,fill="#F8F9FA",lw=.45); text(ax,fx,fy,r"$f$",fs=7,style="italic")
    starts=[y+h*.61,y+h*.56,y+h*.50]
    cols=[BLUE,GREEN,"#C33A39"]
    for i,(sy,col) in enumerate(zip(starts,cols)):
        xx=[x+w*.12,x+w*.35,x+w*.52,fx-w*.04]; yyv=[sy,sy,sy-(i-1)*.010,fy-(i-1)*.010]
        ax.plot(xx,yyv,transform=ax.transAxes,color=col,lw=.7); arrow(ax,(xx[-2],yyv[-2]),(xx[-1],yyv[-1]),color=col,lw=.7,size=4)
        text(ax,x+w*.07,sy,f"Cohort {i+1}",fs=2.75,ha="left")
    inner_title(ax,x,y,w,h*.40,"Predicted queue at ETA",fs=3.0)
    x0=x+w*.14; y0=y+h*.08; ww=w*.72; hh=h*.23
    ax.plot([x0,x0+ww],[y0,y0],transform=ax.transAxes,color=INK,lw=.35)
    curves=[([0,.16,.34,.50,.70,1],[0,.20,.60,.90,.40,.02],INK),([0,.18,.42,.62,.85,1],[0,.10,.38,.62,.20,0],GREEN),([0,.20,.50,.72,1],[0,.05,.18,.31,0],BLUE)]
    for xs,ys,col in curves:
        ax.plot([x0+ww*a for a in xs],[y0+hh*b for b in ys],transform=ax.transAxes,color=col,lw=.65)


def draw_route_eval(ax, x, y, w, h):
    inner_title(ax,x,y+h*.62,w,h*.34,"Candidate routes\nto exits",fs=3.0)
    left=(x+w*.17,y+h*.77); mids=[(x+w*.49,y+h*.87),(x+w*.49,y+h*.76),(x+w*.49,y+h*.65)]; ends=[(x+w*.84,y+h*.87),(x+w*.84,y+h*.76),(x+w*.84,y+h*.65)]
    for p in [left]+mids+ends: ax.add_patch(Circle(p,.0045,transform=ax.transAxes,facecolor="#F5E4B8",edgecolor=INK,linewidth=.35,zorder=4))
    for mid,end,col,ls in zip(mids,ends,[BLUE,GREEN,"#C33A39"],["--","--","--"]):
        ax.plot([left[0],mid[0],end[0]],[left[1],mid[1],end[1]],transform=ax.transAxes,color=col,lw=.7,linestyle=ls)
    for j,end in enumerate(ends): text(ax,end[0]+.010,end[1],f"E{j+1}",fs=3.35,ha="left")
    rect(ax,x,y+h*.48,w,h*.105,edge=GRAY,fill="#FAFBFC",lw=.35)
    text(ax,x+w*.5,y+h*.544,r"$C(P)=T_{move}+W_{queue}$",fs=3.15,weight="bold")
    text(ax,x+w*.5,y+h*.511,r"$+\;W_{recv}+R_{density}$",fs=3.15,weight="bold")
    terms=[(r"$T_{move}$","travel time"),(r"$W_{queue}$","ETA queue wait"),(r"$W_{recv}$","receiving delay"),(r"$R_{density}$","density exposure")]
    for i,(term,desc) in enumerate(terms):
        yy=y+h*(.41-i*.095)
        rect(ax,x+w*.08,yy,w*.84,h*.075,edge=GRAY,fill=WHITE,lw=.3)
        text(ax,x+w*.21,yy+h*.038,term,fs=3.0,weight="bold")
        text(ax,x+w*.57,yy+h*.038,desc,fs=2.85)
    rect(ax,x+w*.15,y+h*.04,w*.70,h*.08,edge="#B18D67",fill="#FCE4CC",lw=.35)
    text(ax,x+w*.50,y+h*.08,"Adaptive A* search",fs=3.85,weight="bold")


def draw_assignment(ax, x, y, w, h):
    inner_title(ax,x,y+h*.70,w,h*.24,"Accepted cohorts\n(route-locked)",fs=3.0)
    people(ax,x+w*.18,y+h*.77,5,color="#173E91",spacing=w*.125,scale=.8); text(ax,x+w*.87,y+h*.79,"…",fs=5,color=GRAY)
    inner_title(ax,x,y+h*.43,w,h*.22,"Undecided cohorts\n(to be updated)",fs=3.0)
    people(ax,x+w*.18,y+h*.50,5,color="#8F949A",spacing=w*.125,scale=.8); text(ax,x+w*.87,y+h*.52,"…",fs=5,color=GRAY)
    inner_title(ax,x,y,w,h*.36,"Route choice and\nassignment",fs=3.0)
    vx=[x+w*.10,x+w*.48,x+w*.74,x+w*.93]
    for xx in vx[1:-1]: ax.plot([xx,xx],[y+h*.04,y+h*.28],transform=ax.transAxes,color=GRAY,lw=.3)
    for xx,label in zip([x+w*.29,x+w*.61,x+w*.835],["Candidates","Selected","Exit"]): text(ax,xx,y+h*.30,label,fs=2.85,weight="bold")
    cols=[BLUE,GREEN,"#C33A39"]
    for i,col in enumerate(cols):
        yy=y+h*(.23-i*.065); ax.add_patch(Circle((x+w*.14,yy),.0035,transform=ax.transAxes,facecolor=GRAY,edgecolor=GRAY)); arrow(ax,(x+w*.20,yy),(x+w*.67,yy),color=col,lw=.6,size=3); rect(ax,x+w*.80,yy-.012,w*.10,.024,edge=INK,fill="#FAFBFC",lw=.28); text(ax,x+w*.85,yy,f"E{i+1}",fs=3.0)


def draw_execution(ax, x, y, w, h):
    # Five aligned mini-cards; no feedback loop crossing their contents.
    labels=["Accepted\ncohorts continue", "Network\nadvances", "Facility state\nupdates", "Undecided\ncohorts", "Replan with\nlatest ETA"]
    card_w=w*.15; xs=[x+w*.02+i*w*.20 for i in range(5)]
    for i,(xx,label) in enumerate(zip(xs,labels)):
        rect(ax,xx,y+h*.22,card_w,h*.55,edge=GRAY if i not in {2,4} else ORANGE,fill=WHITE,lw=.4)
        text(ax,xx+card_w/2,y+h*.67,label,fs=3.2,weight="bold")
    people(ax,xs[0]+card_w*.25,y+h*.38,4,color="#173E91",spacing=card_w*.16,scale=.78)
    # clock
    cx=xs[1]+card_w/2; cy=y+h*.43; ax.add_patch(Circle((cx,cy),.014,transform=ax.transAxes,facecolor=WHITE,edgecolor=INK,linewidth=.55)); ax.plot([cx,cx],[cy,cy+.009],transform=ax.transAxes,color=INK,lw=.5); ax.plot([cx,cx+.007],[cy,cy-.005],transform=ax.transAxes,color=INK,lw=.5); text(ax,cx,y+h*.28,r"$t \rightarrow t+\Delta t$",fs=3.0,style="italic")
    # state matrix
    sx=xs[2]+card_w*.12; sy=y+h*.34
    for r in range(3):
        ax.plot([sx,sx+card_w*.76],[sy+r*.022,sy+r*.022],transform=ax.transAxes,color=GRAY,lw=.25)
    for c in range(3): ax.plot([sx+c*card_w*.25,sx+c*card_w*.25],[sy,sy+card_w*.25],transform=ax.transAxes,color=GRAY,lw=.25)
    text(ax,xs[2]+card_w*.5,y+h*.28,r"$Q$, $R$, $\rho$",fs=3.2)
    people(ax,xs[3]+card_w*.25,y+h*.38,4,color="#8F949A",spacing=card_w*.16,scale=.78)
    # ETA curve
    xx=xs[4]+card_w*.12; yy=y+h*.34; ax.plot([xx,xx+card_w*.76],[yy,yy],transform=ax.transAxes,color=INK,lw=.25); ax.plot([xx,xx+card_w*.23,xx+card_w*.43,xx+card_w*.68],[yy+.01,yy+.08,yy+.04,yy+.13],transform=ax.transAxes,color=ORANGE,lw=.65)
    for a,b in zip(xs[:-1],xs[1:]): arrow(ax,(a+card_w,y+h*.495),(b,y+h*.495),color=INK,lw=.85,size=5)
    # lower controlled iteration arrow outside cards.
    ax.plot([xs[4]+card_w*.72,xs[4]+card_w*.72,xs[0]+card_w*.30],[y+h*.13,y+h*.065,y+h*.065],transform=ax.transAxes,color=ORANGE,lw=.8)
    arrow(ax,(xs[0]+card_w*.30,y+h*.065),(xs[0]+card_w*.30,y+h*.205),color=ORANGE,lw=.8,size=5)


def draw_cross_model(ax, x, y, w, h):
    # Evidence-flow panel, intentionally no numeric comparison claims.
    cards=[("Network route\nplans", BLUE), ("Pathfinder\nexecution", GREEN), ("Spatial trajectory\nand density fields", PURPLE)]
    cw=w*.77; ch=h*.19
    for i,(lab,col) in enumerate(cards):
        yy=y+h*(.70-i*.27)
        rect(ax,x+w*.115,yy,cw,ch,edge=col,fill=WHITE,lw=.45)
        text(ax,x+w*.50,yy+ch/2,lab,fs=3.65,weight="bold")
        if i<2: arrow(ax,(x+w*.50,yy),(x+w*.50,yy-h*.07),color=GRAY,lw=.65,size=4)
    text(ax,x+w*.50,y+h*.045,"Cross-model evaluation",fs=3.65,color=GRAY,style="italic")


def draw_route_export(ax, x, y, w, h):
    """Compact data-free route-export card matching the reference table density."""
    labels = ["Origin", "Route plan", "Exit set"]
    xs = [x+w*.15, x+w*.50, x+w*.85]
    for xx, label in zip(xs, labels):
        text(ax, xx, y+h*.84, label, fs=3.05, weight="bold")
    for i, col in enumerate([BLUE, GREEN, "#C33A39"]):
        yy = y+h*(.62-i*.23)
        ax.add_patch(Circle((xs[0], yy), .004, transform=ax.transAxes, facecolor="#808891", edgecolor="#808891"))
        arrow(ax, (xs[0]+.010, yy), (xs[1]-.016, yy), color=col, lw=.75, size=4)
        ax.plot([xs[1], xs[1]], [yy-.028, yy+.028], transform=ax.transAxes, color=GRAY, lw=.3)
        rect(ax, xs[2]-.020, yy-.022, .040, .044, edge=INK, fill="#FAFBFC", lw=.32)
        text(ax, xs[2], yy, f"E{i+1}", fs=3.15)


def draw_spatial_check(ax, x, y, w, h):
    """No numerical comparison: only the verified cross-model evidence flow."""
    steps = [("Network plan", BLUE), ("Pathfinder", GREEN), ("Spatial check", PURPLE)]
    for i, (label, color) in enumerate(steps):
        yy = y+h*(.68-i*.29)
        rect(ax, x+w*.09, yy, w*.82, h*.17, edge=color, fill=WHITE, lw=.42)
        text(ax, x+w*.50, yy+h*.085, label, fs=2.75, weight="bold")
        if i < 2:
            arrow(ax, (x+w*.50, yy-.004), (x+w*.50, yy-h*.065), color=GRAY, lw=.55, size=4)


def build():
    BASE.parent.mkdir(parents=True, exist_ok=True)
    fig = plt.figure(figsize=(FIG_W_MM*MM, FIG_H_MM*MM), facecolor=WHITE)
    ax = fig.add_axes([0,0,1,1]); ax.set_xlim(0,1); ax.set_ylim(0,1); ax.axis("off")

    # Frame grid taken directly from the user-supplied template: Input | Planning | Output.
    left=(.012,.090,.252,.855); center=(.272,.090,.500,.855); right=(.780,.090,.208,.855)
    rect(ax,*left,edge=BLUE,fill=WHITE,lw=.65); header(ax,left[0],.945,left[2],"INPUT / NETWORK CONSTRUCTION",BLUE)
    rect(ax,*center,edge=ORANGE,fill=WHITE,lw=.65); header(ax,center[0],.945,center[2],"ARRIVAL-TIME-AWARE ROUTE PLANNING",ORANGE)
    rect(ax,*right,edge=GREEN,fill=WHITE,lw=.65); header(ax,right[0],.945,right[2],"OUTPUT / EVALUATION",GREEN)

    # Left strip.
    lx,ly,lw,lh=left
    rect(ax,lx+.006,.500,lw-.012,.430,edge=BLUE,fill=WHITE,lw=.38)
    text(ax,lx+.014,.914,"1. Station geometry",fs=4.65,color=BLUE,weight="bold",ha="left")
    text(ax,lx+.014,.892,"Longyang Road Station\nMulti-line transfer complex",fs=3.25,ha="left")
    cad_ax=ax.inset_axes([lx+.045,.518,lw-.085,.365]); cad_source.render_cad(cad_ax)
    text(ax,lx+lw-.017,.914,"N",fs=4.1,weight="bold"); ax.add_patch(Polygon([[lx+lw-.017,.902],[lx+lw-.026,.886],[lx+lw-.017,.892],[lx+lw-.008,.886]],transform=ax.transAxes,facecolor=INK))
    # simple scale marker, not a numerical result.
    ax.plot([lx+lw-.083,lx+lw-.026],[.514,.514],transform=ax.transAxes,color=INK,lw=.65); ax.plot([lx+lw-.083,lx+lw-.083],[.510,.518],transform=ax.transAxes,color=INK,lw=.45); ax.plot([lx+lw-.026,lx+lw-.026],[.510,.518],transform=ax.transAxes,color=INK,lw=.45)

    rect(ax,lx+.006,.300,lw-.012,.190,edge=BLUE,fill=WHITE,lw=.38)
    text(ax,lx+.014,.475,"2. Evacuation demand",fs=4.65,color=BLUE,weight="bold",ha="left")
    draw_demand(ax,lx+.008,.305,lw-.016,.158)

    rect(ax,lx+.006,.105,lw-.012,.180,edge=BLUE,fill=WHITE,lw=.38)
    text(ax,lx+.014,.270,"3. Dynamic network abstraction",fs=4.35,color=BLUE,weight="bold",ha="left")
    facility_chain(ax,lx+.026,.205,lw-.052)
    rect(ax,lx+.018,.118,lw-.036,.067,edge=BLUE,fill=BLUE_LIGHT,lw=.35)
    text(ax,lx+lw/2,.171,"Link state variables",fs=3.25,weight="bold")
    for i,s in enumerate([r"Capacity $C$",r"Receiving $R$",r"Density $\rho$",r"Speed $v(\rho)$"]):
        xx=lx+.028+i*(lw-.056)/4; ww=(lw-.065)/4
        rect(ax,xx,.126,ww,.028,edge=BLUE,fill=WHITE,lw=.3); text(ax,xx+ww/2,.140,s,fs=2.6)

    # Centre strip.
    cx,cy,cw,ch=center
    card_y=.380; card_h=.535; gap=.014; card_w=(cw-.020-3*gap)/4; card_x=[cx+.010+i*(card_w+gap) for i in range(4)]
    stage_box(ax,card_x[0],card_y,card_w,card_h,1,"Dynamic state\nupdate")
    stage_box(ax,card_x[1],card_y,card_w,card_h,2,"ETA-based\nqueue forecast")
    stage_box(ax,card_x[2],card_y,card_w,card_h,3,"AA* route\nevaluation")
    stage_box(ax,card_x[3],card_y,card_w,card_h,4,"Rolling route\nassignment")
    draw_state_update(ax,card_x[0]+.006,card_y+.018,card_w-.012,card_h-.070)
    draw_queue_forecast(ax,card_x[1]+.006,card_y+.018,card_w-.012,card_h-.070)
    draw_route_eval(ax,card_x[2]+.006,card_y+.018,card_w-.012,card_h-.070)
    draw_assignment(ax,card_x[3]+.006,card_y+.018,card_w-.012,card_h-.070)
    for i in range(3): arrow(ax,(card_x[i]+card_w+.001,card_y+card_h*.57),(card_x[i+1]-.003,card_y+card_h*.57),color=ORANGE,lw=1.35,size=8)
    rect(ax,cx+.010,.105,cw-.020,.250,edge=ORANGE,fill=WHITE,lw=.5)
    text(ax,cx+cw/2,.340,"DYNAMIC EVACUATION-FLOW EXECUTION",fs=5.15,color=ORANGE,weight="bold")
    text(ax,cx+cw/2,.323,"Accepted cohorts continue; only undecided cohorts are replanned",fs=3.45,style="italic")
    draw_execution(ax,cx+.020,.120,cw-.040,.190)

    # Right strip: the reference's three compact evidence cards, without numerical result tables.
    rx,ry,rw,rh=right
    rect(ax,rx+.006,.500,rw-.012,.430,edge=GREEN,fill=WHITE,lw=.38)
    text(ax,rx+.014,.914,"1. Route allocation",fs=4.65,color=GREEN,weight="bold",ha="left")
    pf_ax=ax.inset_axes([rx+.035,.518,rw-.070,.365]); pf_ax.imshow(Image.open(PF_PATH).convert("RGB")); pf_ax.set_xticks([]); pf_ax.set_yticks([])
    for s in pf_ax.spines.values(): s.set_color(GREEN); s.set_linewidth(.45)
    text(ax,rx+rw/2,.510,"Pathfinder execution model",fs=3.25,color=GRAY)
    rect(ax,rx+.006,.300,rw-.012,.185,edge=GREEN,fill=WHITE,lw=.38)
    text(ax,rx+.014,.470,"2. Network route export",fs=4.15,color=GREEN,weight="bold",ha="left")
    draw_route_export(ax,rx+.020,.312,rw-.040,.135)
    rect(ax,rx+.006,.105,rw-.012,.180,edge=GREEN,fill=WHITE,lw=.38)
    text(ax,rx+.014,.270,"3. Continuous-space check",fs=4.05,color=GREEN,weight="bold",ha="left")
    draw_spatial_check(ax,rx+.020,.118,rw-.040,.125)

    text(ax,.500,.042,"Fig. 1. Framework of the proposed arrival-time-aware evacuation planning method for Longyang Road Station.",fs=5.2,weight="bold")
    fig.savefig(BASE.with_suffix(".png"),dpi=360,facecolor=WHITE)
    fig.savefig(BASE.with_suffix(".pdf"),facecolor=WHITE)
    fig.savefig(BASE.with_suffix(".svg"),facecolor=WHITE)
    fig.savefig(BASE.with_suffix(".tiff"),dpi=600,facecolor=WHITE,pil_kwargs={"compression":"tiff_lzw"})
    plt.close(fig)


if __name__ == "__main__":
    build()
