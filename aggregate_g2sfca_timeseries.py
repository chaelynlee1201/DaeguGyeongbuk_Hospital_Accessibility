"""
compute_g2sfca_timeseries.py가 만든 날짜별(perdate) 결과를 모아
격자(Step2)·시설(Step1)별로 42일 분포의 5/50/95 분위를 집계하고,
격자 분위 접근성 지도 3장(p05/p50/p95)을 공통 색상 스케일로 시각화한다.

- 각 날짜 결과는 모든 격자/시설을 포함(도달 없음=0)하므로, 분위는 '0 포함 42일' 기준.
- 해석(B): 격자별 2SFCA 접근성 점수의 날짜 간 분포
    p50 = 중앙값(대표), p05 = 나쁜 날(하위), p95 = 좋은 날(상위).

실행:
  conda activate r5py
  python aggregate_g2sfca_timeseries.py
"""
import os
import glob

import numpy as np
import geopandas as gpd
import pandas as pd

import matplotlib
matplotlib.use("Agg")  # 서버(헤드리스)에서 저장 전용
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.patches import Patch

OUT_DIR = "data/g2sfca_timeseries"
PERDATE_DIR = f"{OUT_DIR}/perdate"
SIGUNGU_SHP = "data/BND_SIGUNGU_PG/BND_SIGUNGU_PG.shp"
GRID_SHP = "data/grid_1km_population_daegugyeongbuk/grid_1km_population_daegugyeongbuk.shp"
EXCLUDED_COLOR = "#d9d9d9"  # 인구 0(분석 제외) 격자 표시색(회색)
TARGET_CODES = [
    "22010", "22020", "22030", "22040", "22050", "22060", "22070", "22510", "22520",
    "37050", "37030", "37070", "37100", "37560", "37570", "37580", "37590",
]
PCTLS = [5, 50, 95]


def set_korean_font():
    """서버에 있을 법한 한글 폰트를 탐색해 설정(없으면 경고만)."""
    from matplotlib import font_manager as fm
    candidates = ["NanumGothic", "Noto Sans CJK KR", "Noto Sans KR", "Malgun Gothic",
                  "AppleGothic", "UnDotum", "NanumBarunGothic"]
    avail = {f.name for f in fm.fontManager.ttflist}
    for name in candidates:
        if name in avail:
            plt.rcParams["font.family"] = name
            break
    else:
        print("[경고] 한글 폰트를 못 찾음 — 지도 제목의 한글이 깨질 수 있음")
    plt.rcParams["axes.unicode_minus"] = False


def load_perdate(kind, id_col, val_col):
    """perdate/{kind}_YYYYMMDD.csv 들을 모아 (id × date) 와이드 테이블 반환."""
    files = sorted(glob.glob(f"{PERDATE_DIR}/{kind}_*.csv"))
    if not files:
        raise SystemExit(f"[오류] {PERDATE_DIR}/{kind}_*.csv 없음 — 먼저 compute 스크립트 실행 필요")
    cols = {}
    for f in files:
        date = os.path.basename(f).split("_")[1].split(".")[0]
        s = pd.read_csv(f, dtype={id_col: str}).set_index(id_col)[val_col]
        cols[date] = s
    wide = pd.DataFrame(cols)  # index=id, columns=dates
    print(f"{kind}: {len(files)}일치, {len(wide)}개 {id_col}")
    return wide


def add_percentiles(wide):
    """행(id)별로 날짜 축 분위 p05/p50/p95 계산."""
    arr = wide.to_numpy(dtype=float)
    out = pd.DataFrame(index=wide.index)
    out["n_days"] = np.isfinite(arr).sum(axis=1)
    for p in PCTLS:
        out[f"p{p:02d}"] = np.nanpercentile(arr, p, axis=1)
    return out


def main():
    set_korean_font()

    # ── Step2 (격자) 집계 ────────────────────────────────────────────────
    grid_wide = load_perdate("step2", "GRID_CD", "G2SFCA")
    grid_pct = add_percentiles(grid_wide)

    demand = gpd.read_file(f"{OUT_DIR}/demand_ref.gpkg").set_index("GRID_CD")
    demand.index = demand.index.astype(str)
    grid = demand[["TOT_POP", "geometry"]].join(grid_pct, how="left")
    grid_out = f"{OUT_DIR}/g2sfca_ts_grid_percentiles.gpkg"
    grid.reset_index().to_file(grid_out, driver="GPKG")
    print("저장:", grid_out)

    # ── Step1 (시설) 집계 ────────────────────────────────────────────────
    fac_wide = load_perdate("step1", "FAC_ID", "step1")
    fac_pct = add_percentiles(fac_wide)
    supply = gpd.read_file(f"{OUT_DIR}/supply_ref.gpkg").set_index("id")
    supply.index = supply.index.astype(str)
    keep = [c for c in ["N_DOCTOR", "FAC_NM", "FAC_TYPE", "geometry"] if c in supply.columns]
    fac = supply[keep].join(fac_pct, how="left")
    fac_out = f"{OUT_DIR}/g2sfca_ts_facility_percentiles.gpkg"
    fac.reset_index().to_file(fac_out, driver="GPKG")
    print("저장:", fac_out)

    # ── 격자 분위 지도 3장 (공통 색상 스케일) ─────────────────────────────
    sigungu = gpd.read_file(SIGUNGU_SHP, encoding="cp949")
    target = sigungu[sigungu["SIGUNGU_CD"].isin(TARGET_CODES)].to_crs(grid.crs)

    # 인구 0(분석 제외) 격자: 전체 1km 격자에서 TOT_POP>0 이 아닌 것(0·결측 포함)
    full_grid = gpd.read_file(GRID_SHP).to_crs(grid.crs)
    excluded = full_grid[~(full_grid["TOT_POP"] > 0)]
    print(f"인구 0(분석 제외) 격자: {len(excluded)}개 (회색 표시)")

    # 이상치에 색이 몰리지 않도록 세 레이어 전체의 98 분위를 공통 vmax로
    allvals = grid[[f"p{p:02d}" for p in PCTLS]].to_numpy(dtype=float)
    vmax = np.nanpercentile(allvals[allvals > 0], 98) if (allvals > 0).any() else 1.0
    vmin = 0.0
    labels = {5: "하위 5% (나쁜 날)", 50: "중앙값 50%", 95: "상위 95% (좋은 날)"}

    fig, axes = plt.subplots(1, 3, figsize=(30, 11), facecolor="white")
    for ax, p in zip(axes, PCTLS):
        # 제외 격자를 맨 아래 회색으로 먼저 깔아 "분석 대상 아님"을 명시
        if len(excluded):
            excluded.plot(ax=ax, color=EXCLUDED_COLOR, edgecolor="none", zorder=0)
        grid.plot(ax=ax, column=f"p{p:02d}", cmap="YlGnBu", vmin=vmin, vmax=vmax,
                  legend=True, edgecolor="none", zorder=1,
                  legend_kwds={"shrink": 0.5, "label": "G2SFCA 접근성 지수"})
        target.boundary.plot(ax=ax, color="#2c2c2c", linewidth=1.2, zorder=2)
        for _, row in target.iterrows():
            c = row.geometry.centroid
            ax.annotate(row["SIGUNGU_NM"], xy=(c.x, c.y), ha="center", va="center",
                        fontsize=8, fontweight="bold", color="#1a1a1a", zorder=3,
                        path_effects=[pe.withStroke(linewidth=2.2, foreground="white")])
        ax.legend(handles=[Patch(facecolor=EXCLUDED_COLOR, edgecolor="none",
                                 label="인구 0 (분석 제외)")],
                  loc="lower left", fontsize=10, frameon=True)
        ax.set_title(f"{labels[p]} (p{p:02d})", fontsize=15, fontweight="bold")
        ax.set_axis_off()

    fig.suptitle("의료시설 Gaussian 2SFCA 접근성 — 2026 7~8월 평일 42일 분포의 분위 (d0=60분, 09:00)",
                 fontsize=18, fontweight="bold")
    plt.tight_layout(rect=[0, 0, 1, 0.97])
    map_out = f"{OUT_DIR}/g2sfca_ts_grid_percentile_maps.png"
    plt.savefig(map_out, dpi=170, facecolor="white")
    print("저장:", map_out)

    # 요약
    print("\n[격자 접근성 분위 요약]")
    print(grid[[f"p{p:02d}" for p in PCTLS]].describe().round(3).to_string())


if __name__ == "__main__":
    main()
