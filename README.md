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
| `data/grid_100m_daegugyeongbuk_with_buildings` | `grid_100m_daegugyeongbuk` 중 건물 폴리곤과 교차하는 격자만 추출 (144,528개, 21.4%) — 실거주·이용 가능성이 없는 산지·농지 등 격자를 제외해 접근성 계산 대상을 실질화 | 자체 전처리 결과 ([`filter_grid_by_buildings.ipynb`](filter_grid_by_buildings.ipynb)), 원본은 [브이월드 — GIS건물일반공간정보](https://www.vworld.kr/dtmk/dtmk_ntads_s002.do?svcCde=NA&dsId=5) |
| `data/raw_gtfs_network` | 대구경북 GTFS(2026-09-01 서비스일) + OSM 네트워크(daegyeong.osm.pbf) | GTFS_realtime_Korea 프로젝트(자체 구축) · OpenStreetMap |
| `data/accessibility_ttm_20260901_0900` | r5py `TravelTimeMatrix`로 계산한, 건물 존재 100m 격자 중심점→가장 가까운 의료시설까지의 대중교통 통행시간 (2026-09-01 09:00 오전 첨두, 144,528개 격자) | 자체 계산 결과 ([`compute_ttm_nearest_facility.py`](compute_ttm_nearest_facility.py), [`accessibility_ttm_20260901_0900.ipynb`](accessibility_ttm_20260901_0900.ipynb)) |
| `data/isochrones_20260901_0900` | r5py `Isochrones`로 계산한, 의료시설까지 30분/60분 이내 도달 가능 영역(isochrone 폴리곤) (2026-09-01 09:00 오전 첨두) | 자체 계산 결과 ([`compute_isochrones.py`](compute_isochrones.py), [`isochrones_20260901_0900.ipynb`](isochrones_20260901_0900.ipynb)) |

`data/raw_vworld_buildings`(브이월드 건물 원본, 대구·경북 용량이 커서 `.gitignore` 처리)는 저장소에 포함되지 않는다. 재현하려면 위 브이월드 링크에서 로그인 후 대구광역시(`AL_D010_27_*`)·경상북도(`AL_D010_47_*`) GIS건물일반공간정보 SHP를 받아 `data/raw_vworld_buildings/`에 두고 `filter_grid_by_buildings.ipynb`를 실행하면 된다.

### 의료시설 접근성 계산 (r5py TravelTimeMatrix)

`compute_ttm_nearest_facility.py`가 [r5py](https://r5py.readthedocs.io/)의 `TravelTimeMatrix`로 계산을 수행한다.

| 파라미터 | 값 |
|---|---|
| Origin | 건물 존재 100m 격자 중심점 (144,528개) |
| Destination | 의료시설 7종별, 대상 지역 20km 버퍼 내 (3,887개) — 버퍼 없이 대상 지역만 쓰면 경계 인접 격자의 접근성이 실제보다 나쁘게 왜곡되는 것을 방지 |
| 출발일시 | 2026-09-01(화) 09:00:00 (오전 첨두) |
| departure_time_window | 1시간 |
| transport_modes | TRANSIT, WALK |
| speed_walking | 4.5 km/h |
| max_time | 60분 |
| max_time_walking | 15분 |
| max_public_transport_rides | 5회 |

144,528×3,887쌍 전체를 한 번에 들고 있으면 5억 6천만 행이 되어 메모리를 감당할 수 없으므로, origin을 3,000개씩 청크로 나눠 처리하며 청크마다 origin별 최솟값(가장 가까운 의료시설까지의 시간)만 남기고 버린다. 결과는 4단계(0~15/15~30/30~45/45~60분) + 60분 초과·도달불가(회색)로 시각화한다.

**참고**: 이 방식(가장 가까운 시설까지의 시간)은 4단계 단계구분도용이며, 추후 log-logistic 거리조락 Gravity model(30/60분 접근성)을 계산하려면 "가장 가까운 시설"이 아니라 "도달 가능한 모든 시설까지의 시간"이 필요해 저장 전략을 다시 설계해야 한다.

### 의료시설 접근성 Isochrone (r5py Isochrones)

`compute_isochrones.py`가 [r5py](https://r5py.readthedocs.io/)의 `Isochrones`로 30분·60분 isochrone을 계산한다.
`Isochrones`는 origin을 여러 개 넣으면 **"이들 중 어느 것으로부터든 최소 이동시간" 기준의 통합 isochrone**을
반환하므로, 의료시설(20km 버퍼 내 3,887개)을 origin으로 넣으면 "가장 가까운 의료시설까지 30분/60분 내 도달
가능한 영역"을 그대로 얻을 수 있다. 나머지 파라미터(출발일시·departure_time_window·transport_modes·
speed_walking·max_time_walking·max_public_transport_rides)는 위 TravelTimeMatrix 계산과 동일하다
(`max_time`은 `isochrones` 임계값에서 자동으로 유도되므로 별도로 넘기지 않는다).

`Isochrones`는 목적지 수와 무관하게 origin 수가 비용을 지배해 origin당 약 0.6~1초로 `TravelTimeMatrix`보다
훨씬 무겁다. 그래서 origin(의료시설 3,887개)을 500개씩 청크로 나눠 처리했다. 반환되는 geometry는
등고선(MULTILINESTRING)이라 `shapely.ops.polygonize`로 닫힌 폴리곤으로 변환한 뒤, 청크 간에는 폴리곤
union으로 합쳤다(min(A∪B) 도달영역 = min(A) 도달영역 ∪ min(B) 도달영역이 성립하므로 청크 분할이 안전).

## 전체 프로젝트 데이터 요약

이 저장소는 [DaeguGyeongbuk_accessibility](https://github.com/chaelynlee1201/DaeguGyeongbuk_accessibility)(GTFS 구축·검증)의 후속 저장소다. 두 저장소에서 사용한 데이터를 모두 정리하면 다음과 같다.

### DaeguGyeongbuk_accessibility (GTFS 검증)

| 데이터명 | 설명 | 출처 |
|---|---|---|
| BND_SIGUNGU_PG | 전국 시군구 경계 | 브이월드 (V-World) |
| BND_UA_PG | 전국 도시화지역 경계 | 브이월드 (V-World) |
| 빈격자(500m) | 전국 500m 격자 | 국토정보플랫폼 국토정보맵 (국토교통부 국토지리정보원) |
| grid_500m_daegugyeongbuk_urban | 위 세 데이터를 10개 시군구→도시화지역 순으로 필터링한 최종 격자 (1,992개) | 자체 전처리 |
| 대구경북 GTFS (daegyung_gtfs) | 실시간 버스·도시철도 API 기반 자체 구축 GTFS | GTFS_realtime_Korea 프로젝트 |
| gtfs_validation_sample_points | GTFS 검증용 무작위 표본 50지점(좌표+주소) | 자체 추출, 역지오코딩은 Kakao 지도 API |

### DaeguGyeongbuk_Hospital_Accessibility (이 저장소, 의료접근성)

| 데이터명 | 설명 | 출처 |
|---|---|---|
| grid_100m_daegugyeongbuk | 전국 100m 격자 중 대상 17개 행정경계와 겹치는 격자 (676,339개) | 국토정보플랫폼 국토정보맵 |
| BND_SIGUNGU_PG | 전국 시군구 경계 (위 저장소에서 재사용) | 브이월드 |
| raw_hira_hospital_info (1.병원정보서비스) | 전국 요양기관 현황(2026.6, 79,772개, 좌표 포함) | 건강보험심사평가원(HIRA) — 「전국 병의원 및 약국 현황」, data.go.kr |
| medical_facilities_filtered | 위 원본 중 병원·의원·종합병원·보건소·보건지소·보건의료원·보건진료소 7개 종별만 필터링 (43,014개) | 자체 전처리 |
| AL_D010_27 / AL_D010_47 (건물 폴리곤) | 대구광역시·경상북도 GIS건물일반공간정보 | 브이월드 — GIS건물일반집합정보 |
| grid_100m_daegugyeongbuk_with_buildings | 100m 격자 중 건물과 교차하는 격자만 추출 (144,528개, 21.4%) | 자체 전처리 |
| raw_gtfs_network | 대구경북 GTFS(2026-09-01) + OSM 네트워크 | GTFS_realtime_Korea 프로젝트 · OpenStreetMap |
| accessibility_ttm_20260901_0900 | r5py TravelTimeMatrix로 계산한 격자→최근접 의료시설 통행시간(2026-09-01 09:00) | 자체 계산 결과 |
| isochrones_20260901_0900 | r5py Isochrones로 계산한 의료시설 30분/60분 도달 가능 영역(2026-09-01 09:00) | 자체 계산 결과 |

### 출처 기관 요약

- **브이월드(V-World)**: 시군구 경계, 도시화지역 경계, 건물 폴리곤
- **국토정보플랫폼 국토정보맵(국토교통부 국토지리정보원)**: 500m·100m 격자
- **건강보험심사평가원(HIRA)/공공데이터포털**: 전국 병의원·약국·보건기관 현황
- **Kakao 지도 API**: 좌표↔주소 변환(지오코딩/역지오코딩)
- **자체 구축**: GTFS(실시간 API 기반), 각 단계 필터링·전처리 결과물
