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
# 계산 백분위수(q) → (표시명, 초과확률 기준 P-코드)
#  q=95(높은 값, 좋은 날) = '상위 5%' → 초과확률 5% → P05
#  q=5 (낮은 값, 나쁜 날) = '하위 5%' → 초과확률 95% → P95
DISPLAY = {5: ("하위 5%", "P95"), 50: ("중앙값", "P50"), 95: ("상위 5%", "P05")}
SCALE = 1000   # 설명 편의를 위해 G2SFCA 값에 곱하는 배율(지도·요약 표시용; 지니·감소율은 배율 무관)
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


def gini(values, weights=None):
    """지니계수(0 포함). weights 주면 인구가중. 전부 0이면 NaN."""
    x = np.asarray(values, dtype=float)
    mask = np.isfinite(x)
    w = np.ones_like(x) if weights is None else np.asarray(weights, dtype=float)
    mask &= np.isfinite(w)
    x, w = x[mask], np.clip(w[mask], 0, None)
    if w.sum() == 0 or (x * w).sum() == 0:
        return float("nan")
    order = np.argsort(x, kind="mergesort")
    x, w = x[order], w[order]
    cw = np.concatenate([[0.0], np.cumsum(w) / w.sum()])
    cxw = np.concatenate([[0.0], np.cumsum(w * x) / (w * x).sum()])
    return float(1.0 - np.sum((cw[1:] - cw[:-1]) * (cxw[1:] + cxw[:-1])))


def gini_ci(values, weights=None, B=500, seed=0):
    """지니계수와 부트스트랩 95% 신뢰구간(격자 재표집)."""
    x = np.asarray(values, dtype=float)
    w = None if weights is None else np.asarray(weights, dtype=float)
    g = gini(x, w)
    n = len(x)
    rng = np.random.default_rng(seed)
    boots = [gini(x[idx], None if w is None else w[idx])
             for idx in (rng.integers(0, n, n) for _ in range(B))]
    lo, hi = np.nanpercentile(boots, [2.5, 97.5])
    return g, lo, hi


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
        gwide = load_perdate(period, "step2", "GRID_CD", "G2SFCA") * SCALE   # 설명 편의 ×1000
        gpct = add_percentiles(gwide)
        g = demand0[["TOT_POP", "geometry"]].join(gpct, how="left")
        g.reset_index().to_file(f"{OUT_DIR}/g2sfca_ts_grid_percentiles_{period}.gpkg", driver="GPKG")
        grids[period] = g

        # ── 진단: G2SFCA=0 비율 ──
        arr = gwide.to_numpy(dtype=float)
        byday_zero = (arr == 0).mean(axis=0)   # 날짜별 0 격자 비율
        always_zero = (np.nanmax(arr, axis=1) == 0).mean() * 100   # 42일 내내 0(완전 미도달)
        print(f"[{period}] 42일 내내 G2SFCA=0 (완전 미도달) 격자: {always_zero:.1f}%")
        print(f"[{period}] 일평균 G2SFCA=0 격자 비율: {np.nanmean(byday_zero)*100:.1f}% "
              f"(일자별 {np.nanmin(byday_zero)*100:.1f}~{np.nanmax(byday_zero)*100:.1f}%)")
        for q in PCTLS:
            name, pcode = DISPLAY[q]
            print(f"      {name}({pcode}) 값=0 격자 비율: {(g[f'p{q:02d}']==0).mean()*100:.1f}%")
        # 시설(Step1)도 저장(지도는 격자만, 시설은 데이터로 보관)
        fpct = add_percentiles(load_perdate(period, "step1", "FAC_ID", "step1") * SCALE)
        keep = [c for c in ["N_DOCTOR", "FAC_NM", "FAC_TYPE", "geometry"] if c in supply0.columns]
        supply0[keep].join(fpct, how="left").reset_index().to_file(
            f"{OUT_DIR}/g2sfca_ts_facility_percentiles_{period}.gpkg", driver="GPKG")

    # ── (1) 분위 접근성 지도 (2행[시간대] × 3열[분위]) — 단계구분도 2종: 등간격 / Natural Breaks ──
    allvals = np.concatenate([grids[p][[f"p{q:02d}" for q in PCTLS]].to_numpy(dtype=float).ravel()
                              for p in PERIODS])
    finite = allvals[np.isfinite(allvals)]
    vmax = np.nanpercentile(finite[finite > 0], 98) if np.any(finite > 0) else 1.0
    N_CLASSES = 5

    def plot_percentile_grid(cmap_p, norm_p, out_path, extend="max"):
        """6장(시간대×분위) 단계구분도 생성. 모든 패널 동일 구간(norm_p)."""
        # 높이를 줄여 셀 내 세로 여백 축소 → 상·하단 행 간격, 제목-지도 간격 감소
        fig, axes = plt.subplots(len(PERIODS), 3, figsize=(24, 11.5), facecolor="white")
        fig.suptitle("Gaussian 2SFCA 의료접근성 분위 (평일 42일)",
                     fontsize=26, fontweight="bold", y=0.975)
        for r, period in enumerate(PERIODS):
            g = grids[period]
            for c, q in enumerate(PCTLS):
                ax = axes[r, c]
                if len(excluded):
                    excluded.plot(ax=ax, color=EXCLUDED_COLOR, edgecolor="none", zorder=0)
                g.plot(ax=ax, column=f"p{q:02d}", cmap=cmap_p, norm=norm_p,
                       legend=False, edgecolor="none", zorder=1)
                target.boundary.plot(ax=ax, color="#2c2c2c", linewidth=1.0, zorder=2)
                ax.legend(handles=[Patch(facecolor=EXCLUDED_COLOR, edgecolor="none",
                                         label="인구 0 (분석 제외)")],
                          loc="lower left", fontsize=8, frameon=True)
                name, pcode = DISPLAY[q]
                ax.set_title(f"{PERIODS[period]} · {name} ({pcode})",
                             fontsize=15, fontweight="bold", pad=1)
                ax.set_axis_off(); ax.set_anchor("N")   # 지도를 셀 상단에 붙임
                sm = matplotlib.cm.ScalarMappable(norm=norm_p, cmap=cmap_p); sm.set_array([])
                cb = fig.colorbar(sm, ax=ax, shrink=0.55, extend=extend)
                cb.ax.set_xlabel("G2SFCA 접근성 지수 (×1000)", fontsize=9, labelpad=6)
        fig.subplots_adjust(top=0.93, bottom=0.01, hspace=-0.15, wspace=0.02)
        plt.savefig(out_path, dpi=160, facecolor="white", bbox_inches="tight"); plt.close(fig)
        print("저장:", out_path)

    # 등간격(Equal Interval) 단계구분도
    bounds_eq = np.linspace(0.0, vmax, N_CLASSES + 1)
    cmap_eq = plt.get_cmap("YlGnBu", N_CLASSES)
    plot_percentile_grid(cmap_eq, matplotlib.colors.BoundaryNorm(bounds_eq, cmap_eq.N),
                         f"{OUT_DIR}/g2sfca_ts_grid_percentile_maps.png", extend="max")

    # ── (2) 시간대별 상대 감소율(%) 비교 지도 2장 (공통 스케일 0~100%) ──
    fig, axes = plt.subplots(1, len(PERIODS), figsize=(18, 10), facecolor="white")
    fig.suptitle("접근성 상대 감소율: 상위 5%(P05) 대비 하위 5%(P95)", fontsize=24, fontweight="bold", y=0.97)
    bounds = [0, 20, 40, 60, 80, 100]
    cmap = plt.get_cmap("OrRd")
    norm = matplotlib.colors.BoundaryNorm(bounds, cmap.N)
    for ax, period in zip(np.atleast_1d(axes), PERIODS):
        g = grids[period]
        if len(excluded):
            excluded.plot(ax=ax, color=EXCLUDED_COLOR, edgecolor="none", zorder=0)
        # 상위5%(P05)=0 등으로 dec_pct가 NaN인 격자: 회색(missing)으로 표시
        g.plot(ax=ax, column="dec_pct", cmap=cmap, norm=norm, legend=False,
               edgecolor="none", zorder=1, missing_kwds={"color": EXCLUDED_COLOR})
        target.boundary.plot(ax=ax, color="#2c2c2c", linewidth=1.0, zorder=2)
        ax.legend(handles=[Patch(facecolor=EXCLUDED_COLOR, edgecolor="none",
                                 label="인구 0 또는 상위5%(P05)=0 (산정 제외)")],
                  loc="lower left", fontsize=9, frameon=True)
        ax.set_title(f"{PERIODS[period]}", fontsize=16, fontweight="bold", pad=2)
        ax.set_axis_off()
        ax.set_anchor("N")      # 지도를 셀 상단에 붙여 제목-지도 간격 최소화
        sm = matplotlib.cm.ScalarMappable(norm=norm, cmap=cmap); sm.set_array([])
        cb = fig.colorbar(sm, ax=ax, shrink=0.55)
        cb.ax.set_xlabel("상대 감소율 (%)", fontsize=10, labelpad=6)
    fig.subplots_adjust(top=0.92, bottom=0.01, wspace=0.02)
    out2 = f"{OUT_DIR}/g2sfca_ts_decrease_maps.png"
    plt.savefig(out2, dpi=160, facecolor="white", bbox_inches="tight"); plt.close(fig)
    print("저장:", out2)

    # ── (3) 지니계수: 접근성 공간 불평등 (0 포함, 수요격자 기준) ──
    #   상위 5%(P05) = 계산상 95백분위(높은 값) / 하위 5%(P95) = 계산상 5백분위(낮은 값)
    print("\n[지니계수] 접근성 공간 불평등  (0 포함, 값 클수록 불평등 / [ ]=부트스트랩 95% CI)")
    print(f"{'구분':<22}{'비가중 [95% CI]':<26}{'인구가중 [95% CI]':<26}")
    layers = [("p95", "상위5%(P05)"), ("p50", "중앙값(P50)"), ("p05", "하위5%(P95)")]
    for period in PERIODS:
        g = grids[period]
        for col, disp in layers:
            gu, gul, guh = gini_ci(g[col].values)
            gw, gwl, gwh = gini_ci(g[col].values, g["TOT_POP"].values)
            label = f"{PERIODS[period]} {disp}"
            print(f"{label:<22}{f'{gu:.3f} [{gul:.3f},{guh:.3f}]':<26}"
                  f"{f'{gw:.3f} [{gwl:.3f},{gwh:.3f}]':<26}")

    # 요약
    for period in PERIODS:
        print(f"\n[{PERIODS[period]}] 격자 분위·감소율 요약 "
              f"(p95=상위5%/P05, p05=하위5%/P95)")
        print(grids[period][["p05", "p50", "p95", "dec_pct"]].describe().round(4).to_string())


if __name__ == "__main__":
    main()
