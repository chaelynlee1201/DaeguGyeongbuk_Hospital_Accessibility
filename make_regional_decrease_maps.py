"""
Figure 2: 지역별 상대 감소율 평균 단계구분도 (시간대별 별도, 등간격).

- 각 1km 격자를 '교차 면적이 가장 큰' 시군구에 배정(경계 격자 처리).
- 시군구별 상대 감소율(dec_pct) 평균을 산정.
- 메인 지도: 경북 8개 시·군 + 대구광역시(자치구 통합) = 9개 지역.
- 삽도(inset): 대구광역시만 확대, 자치구(중·동·서·남·북·수성·달서구, 달성·군위군) 단위.
- 메인/삽도 색 구간(등간격)·범례 동일.

입력:
  data/g2sfca_timeseries/g2sfca_ts_grid_percentiles_{0900,1200}.gpkg  (GRID_CD, dec_pct)
  data/grid_1km_population_daegugyeongbuk/...shp  (격자 폴리곤, GRID_CD)
  data/BND_SIGUNGU_PG/...shp

실행(서버):
  conda activate GTFS
  python make_regional_decrease_maps.py
"""
import os
import numpy as np
import geopandas as gpd
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from mpl_toolkits.axes_grid1.inset_locator import inset_axes

GRID_SHP = "data/grid_1km_population_daegugyeongbuk/grid_1km_population_daegugyeongbuk.shp"
SIGUNGU_SHP = "data/BND_SIGUNGU_PG/BND_SIGUNGU_PG.shp"
PCT_GPKG = "data/g2sfca_timeseries/g2sfca_ts_grid_percentiles_{period}.gpkg"
OUT_DIR = "data/regional_maps"
PERIODS = {"0900": "09:00 출발", "1200": "12:00 출발"}

DAEGU_CODES = ["22010", "22020", "22030", "22040", "22050", "22060", "22070", "22510", "22520"]
GYEONGBUK_CODES = ["37030", "37050", "37070", "37100", "37560", "37570", "37580", "37590"]
TARGET_CODES = DAEGU_CODES + GYEONGBUK_CODES
N_CLASSES = 5
CMAP = "OrRd"

os.makedirs(OUT_DIR, exist_ok=True)


def set_korean_font():
    from matplotlib import font_manager as fm
    for name in ["NanumGothic", "Noto Sans CJK KR", "Noto Sans KR", "Malgun Gothic",
                 "AppleGothic", "UnDotum", "NanumBarunGothic"]:
        if name in {f.name for f in fm.fontManager.ttflist}:
            plt.rcParams["font.family"] = name
            break
    else:
        print("[경고] 한글 폰트 없음")
    plt.rcParams["axes.unicode_minus"] = False


def assign_grid_to_sigungu(grid, sig):
    """각 격자를 교차 면적이 최대인 시군구(SIGUNGU_CD)에 배정 → GRID_CD별 코드 매핑."""
    ov = gpd.overlay(grid[["GRID_CD", "geometry"]], sig[["SIGUNGU_CD", "geometry"]],
                     how="intersection", keep_geom_type=True)
    ov["a"] = ov.geometry.area
    idx = ov.groupby("GRID_CD")["a"].idxmax()
    best = ov.loc[idx, ["GRID_CD", "SIGUNGU_CD"]].set_index("GRID_CD")["SIGUNGU_CD"]
    return best


def regional_means(period, grid, assign):
    """시군구별 dec_pct 평균(시군구 코드 → 값). dec_pct는 결과 gpkg에서 조인."""
    pct = gpd.read_file(PCT_GPKG.format(period=period))[["GRID_CD", "dec_pct"]]
    pct["GRID_CD"] = pct["GRID_CD"].astype(str)
    df = pct.merge(assign.rename("SIGUNGU_CD"), left_on="GRID_CD", right_index=True)
    # dec_pct가 NaN(상위5%=0 등 산정불가)인 격자는 평균에서 제외
    means = df.dropna(subset=["dec_pct"]).groupby("SIGUNGU_CD")["dec_pct"].mean()
    return means


def main():
    set_korean_font()
    grid = gpd.read_file(GRID_SHP).to_crs("EPSG:5179")
    grid["GRID_CD"] = grid["GRID_CD"].astype(str)
    sig = gpd.read_file(SIGUNGU_SHP, encoding="cp949").to_crs("EPSG:5179")
    sig_t = sig[sig["SIGUNGU_CD"].isin(TARGET_CODES)].copy()

    # 격자→시군구 면적 최대 배정(1회)
    assign = assign_grid_to_sigungu(grid, sig_t)
    print(f"격자 배정 완료: {len(assign):,}개")

    # 메인 지도용 지오메트리: 경북 8개(개별) + 대구 1개(통합)
    gb = sig_t[sig_t["SIGUNGU_CD"].isin(GYEONGBUK_CODES)][["SIGUNGU_CD", "SIGUNGU_NM", "geometry"]].copy()
    daegu_geom = sig_t[sig_t["SIGUNGU_CD"].isin(DAEGU_CODES)].union_all()
    daegu_row = gpd.GeoDataFrame({"SIGUNGU_CD": ["DAEGU"], "SIGUNGU_NM": ["대구광역시"],
                                  "geometry": [daegu_geom]}, crs=sig.crs)
    main_regions = pd.concat([gb, daegu_row], ignore_index=True)
    daegu_districts = sig_t[sig_t["SIGUNGU_CD"].isin(DAEGU_CODES)][
        ["SIGUNGU_CD", "SIGUNGU_NM", "geometry"]].copy()

    for period in PERIODS:
        means = regional_means(period, grid, assign)
        # 대구 통합값 = 대구 자치구에 배정된 격자 전체의 평균(코드 묶어 재계산)
        pct = gpd.read_file(PCT_GPKG.format(period=period))[["GRID_CD", "dec_pct"]]
        pct["GRID_CD"] = pct["GRID_CD"].astype(str)
        df = pct.merge(assign.rename("SIGUNGU_CD"), left_on="GRID_CD", right_index=True).dropna(subset=["dec_pct"])
        daegu_mean = df[df["SIGUNGU_CD"].isin(DAEGU_CODES)]["dec_pct"].mean()

        mr = main_regions.copy()
        mr["val"] = mr["SIGUNGU_CD"].map(lambda c: daegu_mean if c == "DAEGU" else means.get(c, np.nan))
        dd = daegu_districts.copy()
        dd["val"] = dd["SIGUNGU_CD"].map(lambda c: means.get(c, np.nan))

        # 등간격 공통 구간(메인+삽도 전체 값 기준)
        allv = np.concatenate([mr["val"].dropna().values, dd["val"].dropna().values])
        vmin, vmax = float(np.nanmin(allv)), float(np.nanmax(allv))
        bounds = np.linspace(vmin, vmax, N_CLASSES + 1)
        cmap = plt.get_cmap(CMAP, N_CLASSES)
        norm = matplotlib.colors.BoundaryNorm(bounds, cmap.N)

        fig, ax = plt.subplots(figsize=(12, 12), facecolor="white")
        mr.plot(ax=ax, column="val", cmap=cmap, norm=norm, edgecolor="#2c2c2c",
                linewidth=1.2, legend=True,
                legend_kwds={"label": "상대 감소율 평균 (%)", "shrink": 0.5},
                missing_kwds={"color": "#eeeeee", "label": "값 없음"})
        for _, r in mr.iterrows():
            c = r.geometry.representative_point()
            lab = r["SIGUNGU_NM"] + (f"\n{r['val']:.0f}%" if pd.notna(r["val"]) else "")
            ax.annotate(lab, xy=(c.x, c.y), ha="center", va="center", fontsize=10,
                        fontweight="bold", color="#1a1a1a",
                        path_effects=[pe.withStroke(linewidth=2.5, foreground="white")])
        ax.set_title(f"지역별 접근성 상대 감소율 평균 — {PERIODS[period]}",
                     fontsize=18, fontweight="bold", pad=8)
        ax.set_axis_off()

        # 삽도: 대구광역시 구 단위 (동일 norm·cmap)
        axins = inset_axes(ax, width="38%", height="38%", loc="upper right", borderpad=1.2)
        dd.plot(ax=axins, column="val", cmap=cmap, norm=norm, edgecolor="#2c2c2c",
                linewidth=0.8, legend=False,
                missing_kwds={"color": "#eeeeee"})
        for _, r in dd.iterrows():
            c = r.geometry.representative_point()
            lab = r["SIGUNGU_NM"].replace("군위군", "군위").replace("달성군", "달성") \
                  + (f"\n{r['val']:.0f}%" if pd.notna(r["val"]) else "")
            axins.annotate(lab, xy=(c.x, c.y), ha="center", va="center", fontsize=7,
                           fontweight="bold", color="#1a1a1a",
                           path_effects=[pe.withStroke(linewidth=1.8, foreground="white")])
        axins.set_title("대구광역시 (자치구)", fontsize=11, fontweight="bold")
        axins.set_xticks([]); axins.set_yticks([])

        plt.tight_layout()
        out = f"{OUT_DIR}/regional_decrease_{period}.png"
        plt.savefig(out, dpi=200, facecolor="white", bbox_inches="tight"); plt.close(fig)
        print("저장:", out)
        print(f"  [{period}] 지역 평균(%): " +
              ", ".join(f"{n}={v:.0f}" for n, v in zip(mr['SIGUNGU_NM'], mr['val']) if pd.notna(v)))


if __name__ == "__main__":
    main()
