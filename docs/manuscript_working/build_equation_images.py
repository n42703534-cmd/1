from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "manuscript_working" / "figures" / "equations"
OUT.mkdir(parents=True, exist_ok=True)

EQUATIONS = {
    1: (r"$\rho:E\rightarrow\mathcal{R}\cup\{\varnothing\}$", 12.0, 0.42),
    2: (
        r"$v(k)=1.427\ (k\leq0.2);\quad "
        r"\max(1.427-0.3549k,0)\ (0.2<k\leq4.0);\quad 0\ (k>4.0)$",
        10.6,
        0.48,
    ),
    3: (
        r"$c^{\mathrm{Imp}}_e(t)=\alpha l_e+\beta\,t^{\mathrm{move}}_e(t),\qquad "
        r"h(n)=\gamma d(n,\mathcal{X})$",
        11.2,
        0.46,
    ),
    4: (
        r"$\widehat{Q}_r(\tau)=\max\!\left\{0,\,Q_r(t)+A_r(t,\tau)-\mu_r(\tau-t)\right\}$",
        11.2,
        0.46,
    ),
    5: (r"$w_r(\tau)=\widehat{Q}_r(\tau)/\mu_r$", 12.0, 0.42),
    6: (
        r"$\tau_j=\tau_i+w_{\rho(e)}(\tau_i)+s^{\mathrm{batch}}_{\rho(e)}+"
        r"t^{\mathrm{move}}_e(\tau_i)+w^{\mathrm{space}}_j(\tau_j)$",
        10.4,
        0.48,
    ),
    7: (r"$L_1\prec L_2\ \Longleftrightarrow\ \tau_1\leq\tau_2\ \wedge\ g_1\leq g_2$", 11.5, 0.44),
    8: (
        r"$T_p=\min\{t:E^{\mathrm{out}}(t)\geq pN\},\qquad "
        r"p\in\{0.50,0.80,0.90,0.95,0.99,1.00\}$",
        10.5,
        0.48,
    ),
    9: (r"$W^{\mathrm{stat}}=\sum_t N^{\mathrm{stationary}}(t)\,\Delta t$", 11.5, 0.44),
}


def main() -> None:
    mpl.rcParams.update(
        {
            "font.family": "serif",
            "mathtext.fontset": "stix",
            "text.color": "#1F2933",
            "figure.facecolor": "white",
            "savefig.facecolor": "white",
        }
    )
    for number, (latex, fontsize, height) in EQUATIONS.items():
        fig = plt.figure(figsize=(6.15, height), dpi=300)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_axis_off()
        ax.text(0.5, 0.5, latex, ha="center", va="center", fontsize=fontsize, color="#1F2933")
        fig.savefig(OUT / f"eq{number:02d}.png", dpi=300, transparent=False, facecolor="white", pad_inches=0)
        plt.close(fig)
    print(OUT)


if __name__ == "__main__":
    main()
