"""
연구 흐름 파이프라인 다이어그램(한 장).
  데이터 → (42일 반복) G2SFCA 접근성 산출 → 분포(분위) → 상대 감소율 → 지역별 평균 시각화
matplotlib만 사용(지도 데이터 불필요). 서버/로컬 어디서든 실행 가능.

실행: python make_pipeline_figure.py
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

OUT = "data/pipeline/research_pipeline.png"
os.makedirs(os.path.dirname(OUT), exist_ok=True)


def set_korean_font():
    from matplotlib import font_manager as fm
    for name in ["NanumGothic", "Noto Sans CJK KR", "Noto Sans KR", "Malgun Gothic",
                 "AppleGothic", "UnDotum", "NanumBarunGothic"]:
        if name in {f.name for f in fm.fontManager.ttflist}:
            plt.rcParams["font.family"] = name
            break
    plt.rcParams["axes.unicode_minus"] = False


def box(ax, x, y, w, h, title, lines, fc, ec, tcol="#1a1a1a"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.06",
                                linewidth=2, edgecolor=ec, facecolor=fc, zorder=2))
    cx = x + w / 2
    ax.text(cx, y + h - 0.22, title, ha="center", va="top", fontsize=13.5,
            fontweight="bold", color=tcol, zorder=3)
    if lines:
        ax.text(cx, y + h - 0.62, "\n".join(lines), ha="center", va="top",
                fontsize=10.5, color="#333333", zorder=3, linespacing=1.5)


def arrow(ax, x0, y0, x1, y1, label=None):
    ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle="-|>", mutation_scale=22,
                                 linewidth=2.2, color="#555555", zorder=1))
    if label:
        ax.text((x0 + x1) / 2, (y0 + y1) / 2 + 0.12, label, ha="center", va="bottom",
                fontsize=9.5, color="#555555", style="italic")


def main():
    set_korean_font()
    fig, ax = plt.subplots(figsize=(15, 8.6), facecolor="white")
    ax.set_xlim(0, 15); ax.set_ylim(0, 8.6); ax.axis("off")

    ax.text(7.5, 8.35, "연구 흐름 (Research Pipeline)", ha="center", fontsize=18,
            fontweight="bold", color="#1a1a1a")

    # 색
    C_DATA = ("#eef4f8", "#4a7fb5")     # 데이터(파랑)
    C_CORE = ("#fdf1e3", "#e07b39")     # 산출(주황)
    C_RESULT = ("#f3eafb", "#8e5ab5")   # 결과(보라)

    # ── 1행: 입력 데이터 3개 → 통행시간 ──
    box(ax, 0.3, 6.4, 2.6, 1.7, "수요", ["1km 인구격자", "(총인구 > 0)"], *C_DATA)
    box(ax, 0.3, 4.3, 2.6, 1.7, "공급", ["의료시설", "(총의사수 > 0)"], *C_DATA)
    box(ax, 0.3, 2.2, 2.6, 1.7, "대중교통망", ["실시간 GTFS", "평일 42일 + OSM"], *C_DATA)

    # 통행시간 계산 (세 데이터 박스의 중심 y를 향해 화살표)
    box(ax, 3.7, 4.3, 3.0, 3.8, "통행시간 계산",
        ["r5py (R5 엔진)", "도보+대중교통", "09:00 · 12:00", "방향별(시설↔격자)"], *C_CORE)
    for yy in (7.25, 5.15, 3.05):                 # 데이터 3박스의 세로 중심
        arrow(ax, 2.9, yy, 3.7, 6.2)              # 통행시간 박스 좌측 중앙으로 수렴

    # G2SFCA
    box(ax, 7.5, 4.3, 3.0, 3.8, "G2SFCA 접근성 산출",
        ["Gaussian 2SFCA", "(d0 = 60분)", "Step1: 공급-수요비", "Step2: 격자 접근성"], *C_CORE)
    arrow(ax, 6.7, 6.2, 7.5, 6.2)
    # 42일 반복 루프 표시
    ax.annotate("", xy=(7.6, 8.15), xytext=(10.4, 8.15),
                arrowprops=dict(arrowstyle="<->", color="#e07b39", lw=1.8,
                                connectionstyle="arc3,rad=-0.4"))
    ax.text(9.0, 8.5, "42일 각각 반복", ha="center", fontsize=10,
            color="#e07b39", fontweight="bold")

    # ── 결과 단계 (하단으로) ──
    box(ax, 11.3, 5.6, 3.4, 2.5, "① 접근성 분포",
        ["격자별 42일 분포", "P05(상위5%)·P50", "·P95(하위5%)"], *C_RESULT)
    arrow(ax, 10.5, 6.85, 11.3, 6.85)

    box(ax, 11.3, 3.0, 3.4, 2.1, "② 상대 감소율",
        ["(P05 − P95) / P05", "× 100 (%)", "= 변동성 지표"], *C_RESULT)
    arrow(ax, 13.0, 5.6, 13.0, 5.1)

    box(ax, 7.5, 0.4, 7.2, 2.0, "③ 지역별 상대 감소율 평균 시각화",
        ["격자→시군구 면적 배정 · 시군구별 평균",
         "9개 지역 단계구분도 + 대구 자치구 삽도"], *C_RESULT)
    arrow(ax, 12.2, 3.0, 11.1, 2.4)

    plt.tight_layout()
    plt.savefig(OUT, dpi=200, facecolor="white", bbox_inches="tight")
    print("저장:", OUT)


if __name__ == "__main__":
    main()
