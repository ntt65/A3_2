# #3 기반 구성 검증

확인일은 2026-11-13(Asia/Seoul)이다. 작업 브랜치는 `codex/issue-3-rebuild`이며, `develop`의 `ea13297`을 기준으로 만들었다. 환경 설정은 `fef4fd3`에 커밋했다. [기반 구성 이슈 #3](https://github.com/ntt65/A3_2/issues/3)

## 환경 재현

기존 저장소에서 읽은 uv 패키지 메타데이터를 새 작업 폴더의 `.uv-cache`에 복사하고 `uv lock --offline`으로 새 잠금 파일을 생성했다. 기본 권한에서 PyPI 및 파일 서버의 DNS 조회가 실패했다. 네트워크를 허용한 재시도에서 Windows 휠을 받아 `uv sync --locked`를 완료했다. 별도 검토 환경에서도 독립 가상환경을 생성해 잠금 파일 설치와 import를 확인했다.

| 확인 항목 | 결과 |
| --- | --- |
| `uv --version` | 0.13.7 |
| `uv lock --check --offline` | 프로젝트와 잠금 파일 일치 |
| `uv sync --locked` | 새 가상환경에서 패키지 설치 성공 |
| `uv run --locked python tools/check_environment.py` | CPython 3.11.4, OpenCV 4.14.0, NumPy 2.4.6, Windows-10-10.0.26200-SP0 |
| OpenCV 배포 패키지 | `opencv-python` 4.14.0.94 |
| Git 속성과 제외 규칙 | 소스 LF, PDF·영상 바이너리, 로컬 환경·캐시·영상·출력·임시 파일 제외 확인 |

원문은 Python 3.8 이상을 요구하고 Python 3.10 이상과 OpenCV 4.5 이상을 권장한다. 재구현에서 사용한 Python은 3.11이다. [미션 원문 p.6](../A3_2_mission.pdf)

## 공통 계약 검증

```powershell
uv run --locked python -m unittest discover -s tests -p test_contracts.py -v
```

구현 환경에서 11개 테스트가 통과했다. 첫 프레임의 인덱스·선택적 시각, 잘못된 시각의 거부, 프레임 메타데이터의 불변성과 배열 공유, 감지 좌표, 미관측 트랙의 스냅샷과 궤적, 매칭 개수와 매칭률 경계를 확인했다. `AGENTS.md`와 실행 프레임워크의 Git blob은 `ef796af`의 원본과 각각 일치했다.

별도 검토자는 잠금 파일로 미리 설치한 독립 가상환경에서 `uv run --locked --no-sync python -m unittest discover -s tests -p test_contracts.py -v`를 실행했다. 11개 테스트가 통과했다.

카메라, 정상 EOF·입력 오류, 일시정지와 키 동작, GUI 출력은 #4와 #9에서 확인한다. 영상의 30개 관찰 이벤트와 특징점·배경 학습률 비교는 #10에서 실제 자료로 측정한다.
