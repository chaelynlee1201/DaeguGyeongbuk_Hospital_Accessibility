"""
compute_g2sfca_timeseries.py가 만든 날짜별(perdate/<시간대>) 결과를 모아
시간대(09:00, 12:00)별로 격자(Step2)·시설(Step1)의 42일 분포 분위를 집계하고,
(1) 분위 접근성 지도 6장(시간대 2 × p05/p50/p95), 공통 색상 스케일
(2) 시간대별 '상위5%(p95) 대비 하위5%(p05) 상대 감소율(%)' 비교 지도 2장
을 생성한다.

- 각 날짜 결과는 모든 격자/시설 포함(도달 없음=0) → 분위는 '0 포함 42일' 기준.
- 해석(B): 격자별 2SFCA 접근성 점수의 날짜 간 분포.
    p05 = 하위 5%(나쁜 날), p50 = 중앙값, p95 = 상위 5%(좋은 날).
- 상대 감소율(%) = (p95 - p05) / p95 * 100  (p95=0 격자는 산정 불가 → 회색).

실행:
  conda activate <env>
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

PERIODS = {"0900": "09:00 출발", "1200": "12:00 출발"}
PCTLS = [5, 50, 95]
PCTL_LABEL = {5: "하위 5%", 50: "중앙값 50%", 95: "상위 5%"}   # p95=상위 5%
TARGET_CODES = [
    "22010", "22020", "22030", "22040", "22050", "22060", "22070", "22510", "22520",
    "37050", "37030", "37070", "37100", "37560", "37570", "37580", "37590",
]


def set_korean_font():
    from matplotlib import font_manager as fm
    for name in ["NanumGothic", "Noto Sans CJK KR", "Noto Sans KR", "Malgun Gothic",
                 "AppleGothic", "UnDotum", "NanumBarunGothic"]:
        if name in {f.name for f in fm.fontManager.ttflist}:
            plt.rcParams["font.family"] = name
            break
    else:
        print("[경고] 한글 폰트를 못 찾음 — 지도 제목의 한글이 깨질 수 있음")
    plt.rcParams["axes.unicode_minus"] = False


def load_perdate(period, kind, id_col, val_col):
    """perdate/<period>/{kind}_YYYYMMDD.csv 들을 모아 (id × date) 와이드 테이블 반환."""
    files = sorted(glob.glob(f"{PERDATE_DIR}/{period}/{kind}_*.csv"))
    if not files:
        raise SystemExit(f"[오류] {PERDATE_DIR}/{period}/{kind}_*.csv 없음 — compute 먼저 실행")
    cols = {}
    for f in files:
        date = os.path.basename(f).split("_")[1].split(".")[0]
        cols[date] = pd.read_csv(f, dtype={id_col: str}).set_index(id_col)[val_col]
    wide = pd.DataFrame(cols)
    wide.index = wide.index.astype(str)
    print(f"[{period}] {kind}: {len(files)}일치, {len(wide)}개 {id_col}")
    return wide


def add_percentiles(wide):
    """행(id)별 날짜 축 분위 p05/p50/p95 + 상대 감소율(%) 계산."""
    arr = wide.to_numpy(dtype=float)
    out = pd.DataFrame(index=wide.index)
    out["n_days"] = np.isfinite(arr).sum(axis=1)
    for p in PCTLS:
        out[f"p{p:02d}"] = np.nanpercentile(arr, p, axis=1)
    # 상대 감소율(%): (p95 - p05)/p95*100, p95<=0 이면 정의 불가(NaN → 지도에서 회색)
    with np.errstate(divide="ignore", invalid="ignore"):
        dec = (out["p95"] - out["p05"]) / out["p95"] * 100.0
    out["dec_pct"] = dec.where(out["p95"] > 0, np.nan)
    return out


def load_excluded():
    """인구 0(분석 제외) 격자(전체 격자 중 TOT_POP>0 이 아닌 것)."""
    full = gpd.read_file(GRID_SHP)
    return full[~(full["TOT_POP"] > 0)]


def main():
    set_korean_font()

    sigungu = gpd.read_file(SIGUNGU_SHP, encoding="cp949")
    demand0 = gpd.read_file(f"{OUT_DIR}/demand_ref.gpkg").set_index("GRID_CD")
    demand0.index = demand0.index.astype(str)
    crs = demand0.crs
    target = sigungu[sigungu["SIGUNGU_CD"].isin(TARGET_CODES)].to_crs(crs)
    excluded = load_excluded().to_crs(crs)
    print(f"인구 0(분석 제외) 격자: {len(excluded)}개 (회색 표시)")

    supply0 = gpd.read_file(f"{OUT_DIR}/supply_ref.gpkg").set_index("id")
    supply0.index = supply0.index.astype(str)

    grids = {}   # period -> GeoDataFrame(p05,p50,p95,dec_pct,geometry,TOT_POP)
    for period in PERIODS:
        gpct = add_percentiles(load_perdate(period, "step2", "GRID_CD", "G2SFCA"))
        g = demand0[["TOT_POP", "geometry"]].join(gpct, how="left")
        g.reset_index().to_file(f"{OUT_DIR}/g2sfca_ts_grid_percentiles_{period}.gpkg", driver="GPKG")
        grids[period] = g
        # 시설(Step1)도 저장(지도는 격자만, 시설은 데이터로 보관)
        fpct = add_percentiles(load_perdate(period, "step1", "FAC_ID", "step1"))
        keep = [c for c in ["N_DOCTOR", "FAC_NM", "FAC_TYPE", "geometry"] if c in supply0.columns]
        supply0[keep].join(fpct, how="left").reset_index().to_file(
            f"{OUT_DIR}/g2sfca_ts_facility_percentiles_{period}.gpkg", driver="GPKG")

    # ── (1) 분위 접근성 지도 6장 (2행[시간대] × 3열[분위]), 6장 공통 색상 스케일 ──
    allvals = np.concatenate([grids[p][[f"p{q:02d}" for q in PCTLS]].to_numpy(dtype=float).ravel()
                              for p in PERIODS])
    vmax = np.nanpercentile(allvals[allvals > 0], 98) if np.any(allvals > 0) else 1.0

    # 비연속(단계구분도) 공통 색상: 0~vmax 등간격 5단계 (6장 모두 동일 구간)
    N_CLASSES = 5
    bounds_p = np.linspace(0.0, vmax, N_CLASSES + 1)
    cmap_p = plt.get_cmap("YlGnBu", N_CLASSES)
    norm_p = matplotlib.colors.BoundaryNorm(bounds_p, cmap_p.N)

    fig, axes = plt.subplots(len(PERIODS), 3, figsize=(27, 19), facecolor="white")
    for r, period in enumerate(PERIODS):
        g = grids[period]
        for c, q in enumerate(PCTLS):
            ax = axes[r, c]
            if len(excluded):
                excluded.plot(ax=ax, color=EXCLUDED_COLOR, edgecolor="none", zorder=0)
            g.plot(ax=ax, column=f"p{q:02d}", cmap=cmap_p, norm=norm_p,
                   legend=True, edgecolor="none", zorder=1,
                   legend_kwds={"shrink": 0.5, "label": "G2SFCA 접근성 지수",
                                "extend": "max", "spacing": "uniform"})
            target.boundary.plot(ax=ax, color="#2c2c2c", linewidth=1.1, zorder=2)
            ax.legend(handles=[Patch(facecolor=EXCLUDED_COLOR, edgecolor="none",
                                     label="인구 0 (분석 제외)")],
                      loc="lower left", fontsize=9, frameon=True)
            ax.set_title(f"{PERIODS[period]} · {PCTL_LABEL[q]} (p{q:02d})",
                         fontsize=14, fontweight="bold")
            ax.set_axis_off()
    fig.suptitle("의료시설 Gaussian 2SFCA 접근성 분위 — 2026 7~8월 평일 42일 (d0=60분, window 2h)\n"
                 "p05=하위 5%(나쁜 날) · p50=중앙값 · p95=상위 5%(좋은 날), 6장 공통 단계구분(등간격 5단계)",
                 fontsize=17, fontweight="bold")
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    out1 = f"{OUT_DIR}/g2sfca_ts_grid_percentile_maps.png"
    plt.savefig(out1, dpi=160, facecolor="white"); plt.close(fig)
    print("저장:", out1)

    # ── (2) 시간대별 상대 감소율(%) 비교 지도 2장 (공통 스케일 0~100%) ──
    fig, axes = plt.subplots(1, len(PERIODS), figsize=(20, 11), facecolor="white")
    bounds = [0, 20, 40, 60, 80, 100]
    cmap = plt.get_cmap("OrRd")
    norm = matplotlib.colors.BoundaryNorm(bounds, cmap.N)
    for ax, period in zip(np.atleast_1d(axes), PERIODS):
        g = grids[period]
        if len(excluded):
            excluded.plot(ax=ax, color=EXCLUDED_COLOR, edgecolor="none", zorder=0)
        # p95=0 등으로 dec_pct가 NaN인 격자: 회색(missing)으로 표시
        g.plot(ax=ax, column="dec_pct", cmap=cmap, norm=norm, legend=True,
               edgecolor="none", zorder=1, missing_kwds={"color": EXCLUDED_COLOR},
               legend_kwds={"shrink": 0.5, "label": "상위5%→하위5% 상대 감소율 (%)"})
        target.boundary.plot(ax=ax, color="#2c2c2c", linewidth=1.1, zorder=2)
        ax.legend(handles=[Patch(facecolor=EXCLUDED_COLOR, edgecolor="none",
                                 label="인구 0 또는 p95=0 (산정 제외)")],
                  loc="lower left", fontsize=9, frameon=True)
        ax.set_title(f"{PERIODS[period]} · 접근성 상대 감소율", fontsize=14, fontweight="bold")
        ax.set_axis_off()
    fig.suptitle("접근성 변동성: 상위 5%(좋은 날) 대비 하위 5%(나쁜 날) 상대 감소율(%)\n"
                 "값이 클수록 '좋은 날 대비 나쁜 날' 접근성이 크게 떨어지는(불안정한) 지역",
                 fontsize=16, fontweight="bold")
    plt.tight_layout(rect=[0, 0, 1, 0.93])
    out2 = f"{OUT_DIR}/g2sfca_ts_decrease_maps.png"
    plt.savefig(out2, dpi=160, facecolor="white"); plt.close(fig)
    print("저장:", out2)

    # 요약
    for period in PERIODS:
        print(f"\n[{PERIODS[period]}] 격자 분위·감소율 요약")
        print(grids[period][["p05", "p50", "p95", "dec_pct"]].describe().round(3).to_string())


if __name__ == "__main__":
    main()
