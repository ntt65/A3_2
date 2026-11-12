# A3_2 · OpenCV 객체 추적

영상에서 움직이는 객체의 위치, ID와 이동 궤적을 표시하고 등록 물체를 특징점으로 찾는 Python/OpenCV 프로젝트다. 기본 구현은 MOG2 배경 차분과 모폴로지·윤곽선, 중심점 거리 기반 Greedy Tracker, ORB 매칭을 사용한다.

현재 #3의 개발 환경과 공통 데이터 계약을 준비했다. 영상 입력, 감지, 추적, 매칭과 화면 표시는 후속 이슈 #4~#9에서 구현한다. 실제 영상 측정과 한계 분석 보고서는 #10~#11에서 진행한다.

## 설치와 확인

Windows PowerShell에서 `uv`를 사용할 수 있는 상태로 저장소 루트에서 실행한다. 이 프로젝트의 개발 환경은 Python 3.11이며 OpenCV와 NumPy 버전은 `uv.lock`에 기록한다.

```powershell
uv sync --locked
uv run --locked python tools/check_environment.py
uv run --locked python -m unittest discover -s tests -v
```

환경 점검은 Python, OpenCV, NumPy와 운영체제 정보를 출력한다. 계약 테스트는 프레임 메타데이터, 추적 스냅샷, 빈 매칭과 매칭률을 검사한다. GUI, 키 입력, 웹캠과 실제 영상에서의 성능은 통합 및 평가 단계에서 확인한다.

## 프로젝트 자료

- [미션 원문](docs/A3_2_mission.pdf)
- [실행 계획 #1](https://github.com/ntt65/A3_2/issues/1)과 [요구사항 #2](https://github.com/ntt65/A3_2/issues/2)
- [모듈 공통 계약](docs/architecture.md)과 [#3 검증 기록](docs/validation/issue-3.md)
- [파일 소유권과 작업 지침](AGENTS.md) 및 [검토·인계 절차](docs/agentic-execution-framework.md)

로컬 영상과 생성 결과의 기본 경로는 각각 `data/`와 `outputs/`다. 두 디렉터리는 Git 추적에서 제외한다. 실험에서 보존할 원시 기록은 #8의 평가 프로토콜과 #10의 기록 범위를 따른다.
