# A3_2 · OpenCV 영상 객체 추적과 등록 물체 재인식

영상 파일이나 웹캠에서 움직이는 사람과 물체를 감지하고, 객체마다 ID를 부여해 위치와 이동 궤적을 표시하는 Python/OpenCV 앱이다. 참조 이미지 한 장을 등록하면 매 프레임에서 ORB 특징점을 비교해 해당 물체의 발견 여부를 표시한다.

| 제출물 | 내용 |
| --- | --- |
| [비디오 분석 앱](main.py) | 영상·카메라 입력, 움직임 감지, ID와 궤적 추적, 등록 물체 매칭 |
| [한계 분석 보고서](docs/analysis_report.md) | 실제 추적 관찰 30건, 학습률 9회 비교, ORB 5조건, 실패 원인과 개선 시도 |
| [미션 원문](docs/A3_2_mission.pdf) · [요구사항 추적표](docs/analysis_report.md#요구사항과-검증-근거) | 과제 원문과 요구사항별 코드·검증·측정 근거 |

## 설치와 확인

원문 6쪽의 최소 환경은 Python 3.8 이상이며, 권장 환경은 Python 3.10 이상과 OpenCV 4.5 이상이다. 이 저장소의 잠금 환경은 **Python 3.11 계열**을 사용한다. Windows에서 Python 3.11.4, OpenCV 4.14.0(`opencv-python` 4.14.0.94), NumPy 2.4.6으로 검증했다. [환경 검증 기록](docs/validation/issue-3.md)

Git과 [uv](https://docs.astral.sh/uv/)가 준비된 Windows PowerShell에서 실행한다. 이미 저장소를 받았다면 해당 폴더에서 `uv sync --locked`부터 실행한다.

```powershell
git clone https://github.com/ntt65/A3_2.git
Set-Location A3_2
uv sync --locked
uv run --locked python tools/check_environment.py
uv run --locked python -m unittest discover -s tests -v
```

환경 점검은 Python·운영체제·OpenCV·NumPy 버전을 출력한다. 새 Windows 잠금 환경에서 자동 테스트 71개가 통과했다. 다른 운영체제의 GUI·웹캠 동작은 별도로 확인해야 한다. [앱 검증 기록](docs/validation/issue-9.md)

## 앱 실행

### 영상 파일과 웹캠

첫 번째 명령은 공식 OpenCV 샘플 `vtest.avi`를 받아 파일 크기와 SHA-256을 확인한다. 자체 영상을 쓸 때는 `--video`에 파일 경로를 지정한다.

```powershell
uv run --locked python -m tools.fetch_sample_data --root . --asset vtest
uv run --locked python main.py --video data/videos/vtest.avi
```

웹캠에는 샘플 영상이 필요 없다. 기본 장치는 보통 인덱스 `0`이며, 카메라가 여러 대면 시스템에 연결된 다른 인덱스를 지정할 수 있다.

```powershell
uv run --locked python main.py --camera 0
```

`--video`와 `--camera` 중 하나를 지정한다. 앱 창에 초점을 두면 다음 키를 사용할 수 있다.

| 키 | 동작 |
| --- | --- |
| `p` | 일시정지·재개. 정지 중에는 새 프레임을 읽거나 배경 모델과 추적 상태를 갱신하지 않는다. |
| `s` | 표시 중인 프레임을 오버레이와 함께 PNG로 저장한다. 기본 경로는 `outputs/snapshots/frame-000000.png` 형식이며, 정지 중에도 저장할 수 있다. |
| `q` | 실행을 종료하고 영상 입력과 창을 정리한다. |

화면은 프레임 번호, 처리 FPS, 현재 관측된 트랙의 박스·중심점·ID·궤적을 표시한다. 처리 FPS는 최근 처리 프레임의 읽기·감지·추적·매칭 시간으로 계산한다. 입력 영상의 FPS는 영상의 시간과 재생 속도를 해석하는 데 사용한다.

### 참조 이미지 등록

영상에 실제로 등장하는 물체를 사진 한 장으로 준비하고 `--target`에 지정한다. 경로에 공백이 있으면 따옴표를 사용한다. 발견 기준을 통과한 프레임에는 원문 5쪽의 표기인 `TARGET DETECTED`가 표시된다.

```powershell
uv run --locked python main.py --video 'C:\videos\my-video.mp4' --target 'C:\videos\my-target.png'
```

참조를 지정하면 앱이 각 프레임에서 최대 1,000개의 ORB 특징점을 추출한다. Hamming 거리의 최근접 두 후보에 비율 0.75를 적용하고 중복된 프레임 특징점은 한 번만 센다. 유효 매칭이 12개 이상이면 발견으로 기록한다. 영상 속 물체를 등록한 실제 확인에서는 vtest의 주차 차량과 주변 배경을 잘라 참조로 사용했고, 참조에 사용한 프레임을 뺀 44개 프레임에서 모두 발견 상태가 나왔다. 같은 카메라 시점의 고정 물체 확인이다. [매칭 구현](target_matcher.py) · [차량 보조 확인 기록](experiments/runs/vtest_target_smoke.json)

### 창 없이 실행하고 결과 저장

헤드리스는 창과 키 입력 없이 원본 프레임을 순서대로 처리한다. `--target`과 `--frame-log`를 함께 지정하면 JSONL의 `target.detected`로 발견 여부를 확인할 수 있다.

```powershell
uv run --locked python main.py --video data/videos/vtest.avi --headless --frame-log outputs/vtest/frames.jsonl --summary-json outputs/vtest/summary.json --annotated-video outputs/vtest/annotated.mkv
uv run --locked python main.py --help
```

| 출력 | 읽는 방법 |
| --- | --- |
| `frames.jsonl` | 한 줄에 한 프레임이다. `frame_index`는 0부터 시작한다. `detections`에는 박스와 중심점, `tracks`에는 ID·궤적·미관측 상태, `target`에는 특징점·매칭 수와 발견 여부, `foreground_fraction`에는 후처리 전경 픽셀 비율이 담긴다. 참조를 지정하지 않으면 `target`은 `null`이다. |
| `summary.json` | 실행 설정, 환경 버전, Git 정보, 처리 프레임 수와 종료 이유를 확인한다. 파일 전체를 읽으면 `completed/source_eof`, `q`로 종료하면 `stopped/user_quit`, 실행 중 오류는 `failed/runtime_error`로 기록한다. |
| `annotated.mkv` | 표시 오버레이가 포함된 FFV1 무손실 영상이다. 가로·세로가 짝수인 입력을 사용한다. 소스 FPS가 없으면 출력 영상에 30 FPS를 사용하고, 원본 시각은 기존 계약에 따라 기록한다. |

파일의 `source_timestamp_s`는 소스 FPS가 유효할 때 `frame_index / source_fps`다. FPS를 알 수 없으면 `null`이다. 카메라에서는 캡처 시작 후 경과 초를 기록한다. 박스는 `(x, y, w, h)`, 중심점은 `(x, y)` 순서다. `observed_this_frame=false`인 트랙은 마지막 위치를 내부적으로 유지하는 중이며 그 프레임의 검출 증거로 세지 않는다. [프레임·트랙 계약](docs/architecture.md)

### 조정 가능한 값

| 옵션 | 기본값 | 조정 효과 |
| --- | --- | --- |
| `--learning-rate` | `-1` | 자동 학습률이다. 직접 지정할 때는 0~1을 사용한다. 빠르게 학습하면 조명 급변에 일찍 적응할 수 있고 정지한 대상도 배경에 더 빨리 흡수될 수 있다. |
| `--min-area` | `500` | 최소 윤곽선 면적(px²). 값을 낮추면 작은 대상과 작은 잡음이 함께 늘어날 수 있다. |
| `--kernel-size` | `5` | 열림·닫힘에 사용할 양의 홀수 커널 크기. 영상 해상도와 대상 크기에 맞춰 조정한다. |
| `--max-distance` | `60` | 이전 중심점과 현재 중심점을 연결할 최대 거리(px). |
| `--max-missed` | `5` | 연속 미관측 상태로 트랙을 보존할 최대 프레임 수. 평가의 연속 10프레임 실패 기준은 별도다. |
| `--snapshot-dir` | `outputs/snapshots` | `s` 키로 만든 PNG의 저장 폴더. |

파일이 열리지 않으면 입력 경로와 영상 디코딩 가능 여부를 확인한다. 카메라 입력이 실패하면 장치 인덱스, 다른 앱의 카메라 사용 여부, Windows의 카메라 접근 권한을 확인한다. FFV1 저장이 필요한 경우 `.mkv` 확장자와 짝수 프레임 크기를 확인한다.

## 미션 요구사항과 구현

1. **영상 입출력과 제어 · 원문 4쪽** — `cv2.VideoCapture`로 파일과 웹캠을 연다. 입력과 시간 처리는 [video.py](video.py), 처리 루프와 키 조작은 [main.py](main.py), 화면 출력은 [visualizer.py](visualizer.py)에 있다.
2. **배경 차분과 감지 · 원문 4쪽** — MOG2로 전경 후보를 구한 뒤 그림자를 제외하고 열림·닫힘을 적용한다. 윤곽선 면적을 걸러 박스와 중심점을 계산한다. [motion_detector.py](motion_detector.py)
3. **거리 기반 추적 · 원문 4~6쪽** — [tracker.py](tracker.py)의 `Tracker`가 중심점 거리 순으로 검출과 트랙을 일대일 연결한다. 새 관측에 새 ID를 부여하고, 허용 누락을 넘긴 트랙을 만료시키며, 관측한 중심점을 궤적으로 저장한다.
4. **등록 물체 재인식 · 원문 5쪽** — 참조 한 장의 ORB 특징을 준비하고 프레임마다 매칭한다. 모션 추적의 ID와 타깃 발견 여부는 각각 계산한다. [target_matcher.py](target_matcher.py)
5. **정량 평가와 보고서 · 원문 2~7쪽** — 겹침 20~30초 표준 시나리오를 포함한 실제 영상 관찰, 학습률 3개와 ORB 5조건을 비교했다. 보고서는 배경 모델링·거리 기반 추적·설계된 특징의 한계와 외형·변형·환경을 학습하는 접근이 도움이 될 조건을 다룬다. [평가 규약](docs/evaluation_protocol.md) · [분석 보고서](docs/analysis_report.md)

과제 제약에 따라 딥러닝 객체 탐지 모델, `cv2.dnn`, MediaPipe를 사용하지 않는다. 추적 구현은 중심점 거리를 사용하며, 평가에서 IoU는 관측 박스와 원본 주석을 대조하는 데 사용한다. Hungarian, 침입 구역, IoU 기반 트래커와 Kalman 예측은 선택 과제다. [선택 과제 #12](https://github.com/ntt65/A3_2/issues/12)

## 실측 결과 요약

### 추적 관찰 30건

원본 FPS로 길이를 확인한 20~30초 클립에서 단일 이동 10건, 겹침 10건, 정지 5건, 조명 변화 5건을 관찰했다. vtest 원본은 겹침·정지, CAVIAR는 단일 이동·정지, Wallflower는 조명 급변 3건과 점진적 변화 2건에 사용했다. 조명 클립은 원본 4 Hz에서 각각 100프레임, 25초다. 원본 영상의 대상과 가시성을 확인하고, CAVIAR XML 또는 주요 프레임의 수동 주석을 바탕으로 앱이 현재 관측한 박스와 일대일로 대응시켰다. [자료 출처](docs/data_sources.md) · [사건 계획](experiments/event_plan.json) · [프레임별 근거](experiments/runs/event_frames.csv)

| 조건 | 유효 사건 | 실패한 사건 | 추적 실패 구간 | 실패율 | 겹침 ID Switch |
| --- | ---: | ---: | ---: | ---: | ---: |
| 단일 객체 이동 | 10 | 9 | 9 | 90% | 해당 없음 |
| 두 객체 겹침 | 10 | 0 | 0 | 0% | 5 |
| 객체 일시정지 | 5 | 5 | 5 | 100% | 해당 없음 |
| 조명 변화 | 5 | 2 | 2 | 40% | 해당 없음 |

- **ID Switch**는 겹치기 전 기준 ID를 확인한 대상이 겹침에서 분리된 뒤 다른 ID로 연속 5프레임 이상 관측될 때 집계한다. 기본 거리 60픽셀에서 대상 20명 중 판정 가능한 7명에게서 5건을 확인했다. 같은 입력에서 거리만 30픽셀로 좁히면 6건이었다.
- **추적 실패**는 화면에 있는 가시 대상에 연속 10프레임 이상 현재 관측 또는 ID 부여가 없을 때 집계한다. 몸이 50% 이상 가려진 프레임은 실패 판단에서 제외한다. 화면 밖 또는 가시성 미확인도 사유를 기록하고 연속 구간을 끊는다.
- **실패율**은 실패 구간이 한 번 이상 나온 유효 사건 수를 전체 유효 사건 수로 나눈 값이다. 겹침 실패율 0%는 이 표본에서 연속 10프레임 기준에 도달한 미관측이 없었다는 뜻이다. 겹침 외 조건의 지속 ID 변경은 별도 지표로 기록한다.

원문 기록 양식에 맞춰 영상명, 조건, 원본 프레임 범위, ID Switch, 실패 수, 관찰 메모를 사건별로 남겼다. 조명 실패 두 건은 점진적 조명 변화 중 인물이 앉는 장면으로, 조명과 정지의 기여를 분리해서 측정하지 않았다. [사건별 결과](experiments/runs/event_results.csv) · [조건별 집계](experiments/runs/event_summary.csv) · [대상별 연속 구간](experiments/runs/event_details.json)

### 학습률 3개와 ORB 5조건

동일한 클립 3개에서 학습률 `-1`(자동), `0.005`, `0.05`를 비교해 9회·1,800프레임을 처리했다. Wallflower 점등 장면에서 전경 비율 10% 이하가 5프레임 연속 유지되기 시작한 시점은 점등 기준 각각 17, 26, 2프레임 뒤였다. 이 수치는 마스크의 적응 속도를 비교하는 지표다. [학습률 요약](experiments/runs/learning_rates.csv) · [프레임별 전경 기록](experiments/runs/learning_rate_frames.csv)

| ORB 비교 조건 | 참조 / 검사 특징점 | 유효 매칭 | 매칭률 |
| --- | ---: | ---: | ---: |
| 정면 | 1,000 / 1,000 | 625 | 62.5% |
| 평면 30° 회전 | 1,000 / 1,000 | 535 | 53.5% |
| 평면 60° 회전 | 1,000 / 1,000 | 539 | 53.9% |
| 왼쪽 약 30% 가림 | 1,000 / 1,000 | 287 | 28.7% |
| 왼쪽 50% 가림 | 1,000 / 1,000 | 70 | 7.0% |

매칭률은 유효 매칭 수를 참조 특징점 수로 나눈 값이며 참조 특징점이 0개면 정의하지 않는다. 약 30% 가림의 실제 마스크 면적은 29.94%였다. 다섯 조건 모두 발견 임계값을 통과했다. 같은 참조 사진을 평면에서 회전하거나 가린 실험이므로 다른 카메라 시점에서 촬영한 물체까지 일반화할 근거는 없다. [ORB 조건별 기록](experiments/runs/feature_conditions.csv) · [실험 메타데이터](experiments/runs/feature_metadata.json)

## 실험 재현

### 원본 준비

저장소 루트에서 실행한다. 전체 평가 원본 26개는 약 450 MB이며, 재현할 때 생성되는 클립과 로그에는 별도 공간이 필요하다. 이미 받은 원본은 크기와 SHA-256을 비교한다. 일부 원본만 받으려면 `--asset`을 반복해서 지정할 수 있다. `--check`는 기존 파일만 검증한다. 원본은 [출처 목록](experiments/data_sources.json)의 상대 경로에 저장된다. 파생 영상의 배포에는 자료별 이용 조건이 적용된다. [자료 이용 조건](docs/data_sources.md)

```powershell
$sourceRoot = (Get-Location).Path
uv run --locked python -m tools.fetch_sample_data --root $sourceRoot
uv run --locked python -m tools.fetch_sample_data --root $sourceRoot --check
```

### 겹침 표준 클립만 먼저 확인하기

아래는 vtest 원본 f500~749의 250프레임을 뽑는 25초 예시다. 클립과 프레임 대응표는 새 경로에 생성한다. 클립 번호 0은 원본 500에 대응한다. f622, f690, f727의 겹침 사건을 포함하며, 해당 사건의 자세한 관찰 범위는 [사건 계획](experiments/event_plan.json)에 있다.

```powershell
$demoRoot = Join-Path 'outputs' ('overlap-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
uv run --locked python -m tools.prepare_evaluation_clips --source data/videos/vtest.avi --start 500 --end 749 --output "$demoRoot/overlap.avi" --mapping "$demoRoot/frame-map.csv"
uv run --locked python main.py --video "$demoRoot/overlap.avi"
```

### 제출 기록과 같은 방식으로 재현하기

같은 PowerShell에서 다음 명령을 실행한다. 새 출력 폴더에서 재현하고, 검증된 제출 기록은 [experiments/runs/](experiments/runs/)에서 볼 수 있다.

```powershell
$sourceRoot = (Get-Location).Path
$runRoot = Join-Path 'outputs' ('reproduce-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
uv run --locked python -m tools.evaluate_features --reference "$sourceRoot/data/targets/box.png" --positive-scene "$sourceRoot/data/targets/box_in_scene.png" --output-dir "$runRoot/features"
uv run --locked python -m tools.evaluate_learning_rates --source-root $sourceRoot --work-dir "$runRoot/learning-work" --output-dir "$runRoot/learning" --rates -1 0.005 0.05
uv run --locked python -m tools.summarize_events --source-root $sourceRoot --work-dir "$runRoot/events-work" --output-dir "$runRoot/events" --manual experiments/annotations/manual_subjects.json
```

| 결과 | 확인할 파일 |
| --- | --- |
| ORB 조건별 특징점·매칭·비율 | [feature_conditions.csv](experiments/runs/feature_conditions.csv), [feature_metadata.json](experiments/runs/feature_metadata.json) |
| 학습률별 전경 비율과 안정화 | [learning_rates.csv](experiments/runs/learning_rates.csv), [learning_rate_frames.csv](experiments/runs/learning_rate_frames.csv), [learning_rate_metadata.json](experiments/runs/learning_rate_metadata.json) |
| 30개 사건과 거리 제한 비교 | [event_results.csv](experiments/runs/event_results.csv), [event_summary.csv](experiments/runs/event_summary.csv), [event_details.json](experiments/runs/event_details.json) |
| 원본 대상과 앱 출력의 대조·실행 이력 | [event_frames.csv](experiments/runs/event_frames.csv), [event_metadata.json](experiments/runs/event_metadata.json), [수동 대상 주석](experiments/annotations/manual_subjects.json) |

재실행의 작업 폴더에는 무손실 입력 클립, 원본 프레임 대응 CSV, 앱 JSONL과 실행 요약이 남는다. 실측 메타데이터에서 입력 SHA-256, 실행 명령, 코드 버전, 주요 설정과 프레임 수를 확인할 수 있다.

## 검증과 인계

- 자동 테스트 71개와 평가 원본 26개 해시를 확인했다. vtest 파일 전체 795프레임은 헤드리스에서 정상 종료했다.
- 실제 GUI의 일시정지·재개와 PNG 저장·종료를 검증했다. 스냅샷 두 장은 저장된 FFV1의 해당 표시 프레임과 픽셀 단위로 일치했다. 내장 웹캠은 351프레임 처리 후 `q`로 종료했다. [앱 검증 기록](docs/validation/issue-9.md)
- 원본 대상·프레임 기록 3,479행을 별도로 재검산했다. 보고서에서 판정 기준, 원본 출처, 실행 기록과 결과를 대조할 수 있다. [분석 보고서](docs/analysis_report.md) · [실험 규약](docs/evaluation_protocol.md)
- [실행 계획 #1](https://github.com/ntt65/A3_2/issues/1) · [요구사항 #2](https://github.com/ntt65/A3_2/issues/2) · [미션 제출 PR #13](https://github.com/ntt65/A3_2/pull/13) · [프로젝트 작업 지침](AGENTS.md)
