# DaeguGyeongbuk_Hospital_Accessibility
대구경북권 의료시설 GTFS 대중교통 접근성 측정

[DaeguGyeongbuk_accessibility](https://github.com/chaelynlee1201/DaeguGyeongbuk_accessibility)에서 구축·검증한 GTFS 데이터셋을 바탕으로, 대구·경북 10개 시·군·구(대구광역시, 구미시, 김천시, 영천시, 경산시, 청도군, 고령군, 성주군, 칠곡군) 내 의료시설까지의 대중교통 접근성을 측정한다.

## 데이터

| 데이터 | 설명 | 출처 |
|---|---|---|
| `data/grid_100m_daegugyeongbuk` | 전국 100m 격자 중 대상 10개 시·군·구(17개 행정경계 폴리곤) 경계와 겹치는 격자만 추출 (676,339개) | [국토정보플랫폼 국토정보맵](https://map.ngii.go.kr/ms/map/NlipMap.do) |
| `data/BND_SIGUNGU_PG` | 전국 시군구 경계 (대상 지역 필터링·시각화용) | [브이월드](https://www.vworld.kr/) |
| `data/raw_hira_hospital_info` | HIRA 병원정보서비스 원본(2026.6, 전국 요양기관 79,772개) | [건강보험심사평가원 — 전국 병의원 및 약국 현황](https://www.data.go.kr/data/15051059/fileData.do) |
| `data/medical_facilities_filtered` | 위 원본 중 병원·의원·종합병원·보건소·보건지소·보건의료원·보건진료소 7개 종별만 필터링한 전국 포인트 데이터 (43,014개, EPSG:5179). 원본에 포함된 위경도 좌표를 그대로 사용(별도 지오코딩 불필요) | 자체 전처리 결과 ([`load_medical_facilities.ipynb`](load_medical_facilities.ipynb)) |
