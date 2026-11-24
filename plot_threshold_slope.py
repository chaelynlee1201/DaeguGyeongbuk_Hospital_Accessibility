"""
임계시간 결정용 '한계 커버율(기울기)' 곡선.
analyze_threshold.py가 저장한 nearest_times_*.csv를 읽어(재계산 불필요),
10분 구간별로 '새로 도달되는 격자 비율(%p)'을 그린다.
누적 커버율과 함께 표시하고, 기울기가 급감하는 꺾임 후보를 자동 탐지한다.

실행: python plot_threshold_slope.py
"""
import os
import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

DIR = "data/threshold_analysis"
CSV = f"{DIR}/nearest_times_20260811_09.csv"
BINW = 10          # 구간 폭(분)
XMAX = 180         # 표시 상한(분)


def set_korean_font():
    from matplotlib import font_manager as fm
    for name in ["NanumGothic", "Noto Sans CJK KR", "Noto Sans KR", "Malgun Gothic",
                 "AppleGothic", "UnDotum", "NanumBarunGothic"]:
        if name in {f.name for f in fm.fontManager.ttflist}:
            plt.rcParams["font.family"] = name
            break
    plt.rcParams["axes.unicode_minus"] = False


def main():
    set_korean_font()
    df = pd.read_csv(CSV)
    n_total = len(df)

    for col, nth in [("t_nearest1", 1), ("t_nearest3", 3)]:
        v = df[col].dropna().values
        edges = np.arange(0, XMAX + BINW, BINW)
        # 각 구간에서 새로 도달된 격자 수 → 전체 대비 %p
        counts, _ = np.histogram(v[v <= XMAX], bins=edges)
        marg = counts / n_total * 100.0            # 한계 커버(%p, 전체 대비)
        centers = (edges[:-1] + edges[1:]) / 2
        cum = np.cumsum(counts) / n_total * 100.0  # 누적 커버(%)

        # 꺾임 후보: 한계값이 '최댓값의 절반' 아래로 처음 떨어지는 구간
        peak = marg.max()
        below = np.where(marg < peak * 0.5)[0]
        knee = None
        for i in below:
            if centers[i] > centers[np.argmax(marg)]:   # 피크 이후
                knee = edges[i]        # 그 구간 시작점을 꺾임 임계 후보로
                break

        fig, ax = plt.subplots(figsize=(9, 5.5), facecolor="white")
        ax.bar(centers, marg, width=BINW*0.9, color="#4a7fb5", alpha=0.8,
               label=f"{BINW}분 구간별 한계 커버(%p)")
        ax.set_xlabel("통행시간 임계값 (분)", fontsize=12)
        ax.set_ylabel("한계 커버율 (%p, 전체 격자 대비)", fontsize=12, color="#2c6fbb")
        ax.tick_params(axis="y", labelcolor="#2c6fbb")
        ax.set_title(f"임계시간별 한계 커버율 — 의료시설 {nth}개 포함 (2026-08-11 09:00)",
                     fontsize=14, fontweight="bold")

        ax2 = ax.twinx()
        ax2.plot(centers, cum, "o-", color="#e07b39", lw=2, ms=5, label="누적 커버율(%)")
        ax2.set_ylabel("누적 커버율 (%, 전체 격자 대비)", fontsize=12, color="#e07b39")
        ax2.tick_params(axis="y", labelcolor="#e07b39"); ax2.set_ylim(0, 105)
        # 누적 곡선 위에 '구간 기울기(%p/구간)' 수치를 겹쳐 표시
        for ce, m, c in zip(centers, marg, cum):
            ax2.annotate(f"+{m:.1f}", (ce, c), textcoords="offset points", xytext=(0, 8),
                         ha="center", fontsize=8, color="#b5560f", fontweight="bold")

        for thr in (30, 60, 90):
            ax.axvline(thr, color="#999", ls=":", lw=1)
        if knee is not None:
            ax.axvline(knee, color="#c0392b", lw=2, ls="--")
            ax.text(knee, ax.get_ylim()[1]*0.9, f"꺾임 후보\n{knee:.0f}분", color="#c0392b",
                    ha="center", va="top", fontsize=10, fontweight="bold")

        # 범례 병합
        h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
        ax.legend(h1+h2, l1+l2, loc="upper right", fontsize=10)
        plt.tight_layout()
        out = f"{DIR}/slope_nearest{nth}.png"
        plt.savefig(out, dpi=180, facecolor="white", bbox_inches="tight"); plt.close(fig)
        print(f"[{nth}개] 꺾임 후보: {knee}분 | 저장: {out}")
        # 수치표
        print("    구간(분)  한계%p  누적%")
        for ce, m, c in zip(centers, marg, cum):
            if ce <= XMAX:
                print(f"    {ce-BINW/2:3.0f}-{ce+BINW/2:3.0f}  {m:5.1f}  {c:5.1f}")


if __name__ == "__main__":
    main()
