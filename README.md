# A3_2 · OpenCV 객체 추적

영상에서 움직이는 객체의 위치, ID와 이동 궤적을 표시하고 등록 물체를 특징점으로 찾는 Python/OpenCV 프로젝트다. 기본 구현은 MOG2 배경 차분과 모폴로지·윤곽선, 중심점 거리 기반 Greedy Tracker, ORB 매칭을 사용한다.

[한계 분석 보고서](docs/analysis_report.md)에 실제 영상에서의 추적 결과, 학습률과 거리 제한의 비교, ORB 특징점 실험을 기록했다. 과제의 앱과 보고서 요구사항은 [미션 원문](docs/A3_2_mission.pdf)과 [요구사항 #2](https://github.com/ntt65/A3_2/issues/2)에 있다.

## 30분 발표자료

| 최종안 | PowerPoint | PDF |
| --- | --- | --- |
| Codex 기술 발표 · 본편 28장 + 부록 4장 | [PPTX](docs/presentation/A3_2_technical_30min_visual.pptx) | [검색 가능한 PDF](docs/presentation/A3_2_technical_30min_visual.pdf) |
| ChatGPT Work 시각 발표 v2 · 28장 | [PPTX](docs/presentation/A3_2_visual_story_v2.pptx) | [이미지 기반 PDF](docs/presentation/A3_2_visual_story_v2.pdf) |

두 PPTX에 상세 발표자 노트가 포함돼 있다. 30분은 계획시간이며 실제 전체 리허설은 아직 하지 않았다. [제작·수정·검증 과정](docs/presentation-process.md) · [작업 이슈 #14](https://github.com/ntt65/A3_2/issues/14)

## 설치와 확인

Git과 `uv`를 사용할 수 있는 Windows PowerShell에서 저장소 루트로 이동해 실행한다. `uv.lock`은 Python 3.11 환경의 의존성을 고정한다. 검증에 사용한 버전은 Python 3.11.4, OpenCV 4.14.0(`opencv-python` 4.14.0.94), NumPy 2.4.6이다.

```powershell
uv sync --locked
uv run --locked python tools/check_environment.py
uv run --locked python -m unittest discover -s tests -v
```

최종 Windows 잠금 환경을 새로 만들어 실행한 자동 테스트 71개가 모두 통과했다. 실제 입력 장치와 창 동작을 확인한 환경도 Windows다. [환경 구성 기록](docs/validation/issue-3.md) · [앱 검증 기록](docs/validation/issue-9.md)

## 앱 실행

공개 샘플을 받은 뒤 파일 또는 카메라 중 하나를 선택한다. 자체 파일을 사용하려면 `--video`에 경로를 지정한다.

```powershell
uv run --locked python -m tools.fetch_sample_data --root . --asset vtest
uv run --locked python main.py --video data/videos/vtest.avi
uv run --locked python main.py --camera 0
```

화면에는 원본 프레임 번호, 처리 FPS, 관측된 객체의 박스·중심점·ID·궤적이 표시된다. `p`로 일시정지·재개하고 `s`로 현재 표시 프레임을 PNG로 저장하며 `q`로 종료한다. 일시정지 중에는 새 프레임을 읽거나 분석 상태를 갱신하지 않는다. 기본 스냅샷 위치는 `outputs/snapshots/`이며 `--snapshot-dir`로 바꿀 수 있다.

`--target`에 영상에서 찾을 물체 사진 한 장을 지정한다. 유효 ORB 매칭 수가 기준에 도달한 프레임에 `TARGET DETECTED`가 표시된다. 아래 예시의 사진은 사용자 영상에 실제로 등장하는 물체의 이미지 경로로 바꾼다.

```powershell
uv run --locked python main.py --video 'my-video.mp4' --target 'my-target.png'
uv run --locked python main.py --video data/videos/vtest.avi --headless --frame-log outputs/vtest/frames.jsonl --summary-json outputs/vtest/summary.json --annotated-video outputs/vtest/annotated.mkv
uv run --locked python main.py --help
```

`--headless`는 화면 없이 원본 프레임을 순서대로 처리한다. JSONL에는 각 프레임의 감지, 트랙의 현재 관측 여부, 타깃 결과와 전경 비율이 기록된다. 요약 JSON에는 처리 프레임 수, 종료 이유와 실행 설정이 남는다. 주석 영상은 가로·세로가 짝수인 프레임을 FFV1 `.mkv`로 저장한다. 소스 FPS를 확인할 수 없는 입력에서 주석 영상에 지정하는 30 FPS는 소스 타임스탬프에 사용하지 않는다.

기본값은 학습률 `-1`(자동), 윤곽선 최소 면적 `500`, 모폴로지 커널 `5`, 추적 거리 제한 `60`픽셀, 누락 허용 `5`프레임이다. 각각 `--learning-rate`, `--min-area`, `--kernel-size`, `--max-distance`, `--max-missed`로 조정한다. Windows에서 vtest 795프레임 헤드리스 처리, 실제 `p/s/q` 동작과 PNG 저장, 내장 카메라 입력을 확인했다. [앱 검증 기록](docs/validation/issue-9.md)

## 실험 재현

소스 목록은 공개 배포 URL, 파일 크기, SHA-256 및 메타데이터를 보관한다. 다운로드 도구는 해당 경로의 기존 파일도 검증한다. 다운로드 없이 이미 받은 파일만 확인하려면 `--check`를 붙인다. 최종 검증에서 목록의 원본 26개 파일이 모두 일치했다. 파생 영상을 배포하기 전에 자료별 이용 조건을 확인한다. [자료 출처와 이용 조건](docs/data_sources.md) · [원본 파일 목록](experiments/data_sources.json)

```powershell
$sourceRoot = (Get-Location).Path
$runRoot = Join-Path 'outputs' ('reproduce-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
uv run --locked python -m tools.fetch_sample_data --root $sourceRoot
uv run --locked python -m tools.evaluate_features --reference "$sourceRoot/data/targets/box.png" --positive-scene "$sourceRoot/data/targets/box_in_scene.png" --output-dir "$runRoot/features"
uv run --locked python -m tools.evaluate_learning_rates --source-root $sourceRoot --work-dir "$runRoot/learning-work" --output-dir "$runRoot/learning"
uv run --locked python -m tools.summarize_events --source-root $sourceRoot --work-dir "$runRoot/events-work" --output-dir "$runRoot/events" --manual experiments/annotations/manual_subjects.json
```

재실행의 작업 폴더에는 무손실 입력 클립, 원본 프레임 대응 CSV, 앱 JSONL과 실행 요약이 저장된다. 결과 폴더에는 특징점 5조건, 학습률 9회, 사건별 판정과 프레임 근거를 집계한 표가 생성된다. `experiments/runs/`의 제출용 실험 기록은 그대로 두고 새 폴더로 재현한다. 사건의 대상·가림 기준·실패율 분모와 두 거리 제한의 비교 절차는 평가 규약에 있다. [평가 규약](docs/evaluation_protocol.md) · [사건 계획](experiments/event_plan.json) · [제출 측정 기록](experiments/runs/) · [분석 보고서](docs/analysis_report.md)

## 구현과 검증 기록

- [실행 계획 #1](https://github.com/ntt65/A3_2/issues/1)과 [요구사항 #2](https://github.com/ntt65/A3_2/issues/2)
- [모듈 공통 계약](docs/architecture.md), [환경 검증](docs/validation/issue-3.md), [앱 통합 검증](docs/validation/issue-9.md)
- [파일 소유권과 작업 지침](AGENTS.md) 및 [검토·인계 절차](docs/agentic-execution-framework.md)
