"""
연구 방법 슬라이드용 지도 2장 생성.
 (1) 연구 지역 경계 지도 — 대구·경북 10개 시·군·구(17개 행정경계), 시군구명 라벨
 (2) 필터링된 의료시설 분포 지도 — 7종별 + 총의사수>0, 대상 20km 버퍼 내 (공급지)

실행(서버):
  conda activate GTFS
  python make_study_area_maps.py
"""
import geopandas as gpd
import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.patches import Patch
from matplotlib.lines import Line2D

SIGUNGU_SHP = "data/BND_SIGUNGU_PG/BND_SIGUNGU_PG.shp"
OUT_DIR = "data/study_area_maps"
SUPPLY_GPKG = "data/g2sfca_timeseries/supply_ref.gpkg"   # compute가 만든 최종 공급 시설
TARGET_CODES = [
    "22010", "22020", "22030", "22040", "22050", "22060", "22070", "22510", "22520",
    "37050", "37030", "37070", "37100", "37560", "37570", "37580", "37590",
]
BUFFER_KM = 20

import os
os.makedirs(OUT_DIR, exist_ok=True)


def set_korean_font():
    from matplotlib import font_manager as fm
    for name in ["NanumGothic", "Noto Sans CJK KR", "Noto Sans KR", "Malgun Gothic",
                 "AppleGothic", "UnDotum", "NanumBarunGothic"]:
        if name in {f.name for f in fm.fontManager.ttflist}:
            plt.rcParams["font.family"] = name
            break
    else:
        print("[경고] 한글 폰트 없음 — 라벨 깨질 수 있음")
    plt.rcParams["axes.unicode_minus"] = False


def main():
    set_korean_font()
    sig = gpd.read_file(SIGUNGU_SHP, encoding="cp949").to_crs("EPSG:5179")
    target = sig[sig["SIGUNGU_CD"].isin(TARGET_CODES)].copy()
    others = sig[~sig["SIGUNGU_CD"].isin(TARGET_CODES)].copy()

    # ── (1) 연구 지역 경계 지도 ──
    fig, ax = plt.subplots(figsize=(11, 12), facecolor="white")
    minx, miny, maxx, maxy = target.total_bounds
    mx, my = (maxx - minx) * 0.12, (maxy - miny) * 0.12
    others.plot(ax=ax, color="#f2f2f2", edgecolor="#cccccc", linewidth=0.5, zorder=0)
    target.plot(ax=ax, color="#cfe3f2", edgecolor="#2c2c2c", linewidth=1.3, zorder=1)
    for _, r in target.iterrows():
        c = r.geometry.representative_point()
        ax.annotate(r["SIGUNGU_NM"], xy=(c.x, c.y), ha="center", va="center",
                    fontsize=12, fontweight="bold", color="#1a1a1a", zorder=3,
                    path_effects=[pe.withStroke(linewidth=3, foreground="white")])
    ax.set_xlim(minx - mx, maxx + mx); ax.set_ylim(miny - my, maxy + my)
    ax.set_title("연구 지역: 대구·경북 10개 시·군·구", fontsize=20, fontweight="bold", pad=8)
    ax.set_axis_off()
    # 간이 스케일바(20km)
    sb = 20000; x0 = minx - mx + (maxx - minx) * 0.04; y0 = miny - my + (maxy - miny) * 0.04
    ax.plot([x0, x0 + sb], [y0, y0], color="black", lw=3, zorder=5)
    ax.text(x0 + sb / 2, y0 + (maxy - miny) * 0.012, "20 km", ha="center", fontsize=10, zorder=5)
    plt.tight_layout()
    out1 = f"{OUT_DIR}/study_area_boundary.png"
    plt.savefig(out1, dpi=200, facecolor="white", bbox_inches="tight"); plt.close(fig)
    print("저장:", out1)

    # ── (2) 필터링된 의료시설 분포 지도 ──
    fac = gpd.read_file(SUPPLY_GPKG).to_crs("EPSG:5179")   # 이미 7종·의사>0·20km버퍼 필터 완료
    buf = target.union_all().buffer(BUFFER_KM * 1000)

    fig, ax = plt.subplots(figsize=(11, 12), facecolor="white")
    others.plot(ax=ax, color="#f7f7f7", edgecolor="#dddddd", linewidth=0.4, zorder=0)
    gpd.GeoSeries([buf], crs="EPSG:5179").plot(ax=ax, color="none",
                                               edgecolor="#e07b39", linewidth=1.2,
                                               linestyle="--", zorder=1)
    target.plot(ax=ax, color="#eef4f8", edgecolor="#2c2c2c", linewidth=1.2, zorder=2)

    # 시설 유형별 색상 (FAC_TYPE 값에 맞춰 자동)
    types = list(fac["FAC_TYPE"].value_counts().index) if "FAC_TYPE" in fac.columns else []
    cmap = plt.get_cmap("tab10")
    for i, t in enumerate(types):
        sub = fac[fac["FAC_TYPE"] == t]
        sub.plot(ax=ax, color=cmap(i % 10), markersize=6, alpha=0.75,
                 label=f"{t} ({len(sub)})", zorder=3)
    if not types:   # FAC_TYPE 없으면 단색
        fac.plot(ax=ax, color="#c0392b", markersize=6, alpha=0.7, zorder=3)

    bminx, bminy, bmaxx, bmaxy = buf.bounds
    bx, by = (bmaxx - bminx) * 0.05, (bmaxy - bminy) * 0.05
    ax.set_xlim(bminx - bx, bmaxx + bx); ax.set_ylim(bminy - by, bmaxy + by)
    ax.set_title(f"의료시설 분포 (7종·총의사수>0, 20km 버퍼 내 {len(fac):,}개)",
                 fontsize=18, fontweight="bold", pad=8)
    ax.set_axis_off()
    handles = ax.get_legend_handles_labels()[0]
    handles.append(Line2D([0], [0], color="#e07b39", lw=1.2, ls="--", label="20km 버퍼"))
    ax.legend(handles=handles, loc="lower left", fontsize=9, frameon=True, title="시설 종별(개수)")
    plt.tight_layout()
    out2 = f"{OUT_DIR}/medical_facilities_supply.png"
    plt.savefig(out2, dpi=200, facecolor="white", bbox_inches="tight"); plt.close(fig)
    print("저장:", out2)

    # 참고 통계
    print(f"\n공급 시설 {len(fac):,}개 | 의사수 합 {int(fac['N_DOCTOR'].sum()):,}")
    if "FAC_TYPE" in fac.columns:
        print(fac["FAC_TYPE"].value_counts().to_string())


if __name__ == "__main__":
    main()
