# A3_2 모듈 공통 계약

`contracts.py`는 #4~#9가 공유하는 데이터와 호출 규약을 정의한다. 기본 흐름은 `FrameSource`에서 프레임을 읽고, MOG2 기반 감지 결과를 Greedy Tracker에 전달하고, 같은 영상으로 ORB 타깃 매칭을 수행한 뒤 통합 코드에서 결과를 표시하고 기록하는 순서다. [미션 원문](A3_2_mission.pdf) [계획 #1](https://github.com/ntt65/A3_2/issues/1) [요구사항 #2](https://github.com/ntt65/A3_2/issues/2) [기반 #3](https://github.com/ntt65/A3_2/issues/3)

| 이슈 | 모듈 | 공유 인터페이스 |
| --- | --- | --- |
| #4 | `video.py` | `source_fps: float \| None`, `read() -> Frame \| None`, `close() -> None` |
| #5 | `motion_detector.py` | `detect(image: BGRImage) -> list[Detection]` |
| #6 | `tracker.py` | `Tracker.update(detections: Sequence[Detection]) -> list[TrackSnapshot]` |
| #7 | `target_matcher.py` | `match(image: BGRImage) -> TargetMatch` |
| #8 | `experiments/`, 평가 문서와 도구 | 원본 프레임 번호, 관측 상태, 특징점 수와 매칭률을 평가 기록에 사용 |
| #9 | `main.py`, `visualizer.py` | 영상 처리·표시·저장·입력 제어를 조정 |

## 프레임과 영상 입력

- `Frame.image`는 `(높이, 너비, 3)` 모양의 BGR `numpy.uint8` 배열이다. `frame_index`는 소스별 첫 읽기에서 0으로 시작하고 성공적으로 읽은 프레임마다 1씩 증가한다.
- 파일의 `source_fps`는 유한한 양수일 때 사용하며 그 외에는 `None`이다. 파일 프레임의 `source_timestamp_s`는 `frame_index / source_fps`이며 FPS가 유효하지 않으면 `None`이다. 카메라 프레임의 시각은 캡처 시작 이후 monotonic 경과 초다. 화면에 표시할 처리 FPS는 별도로 계산한다.
- `read()`는 정상적인 파일 끝에서 `None`을 반환한다. 열기 실패, 카메라 읽기 실패, 확인 가능한 파일의 조기 종료 등 입력 실패는 오류로 드러낸다. 통합 코드는 종료 경로에서 `close()`로 입력 자원을 해제한다.
- 영상 배열은 읽기 전용으로 빌려 쓰는 규약을 따른다. 감지, 매칭, 시각화에 원본 배열을 전달할 수 있으며 픽셀을 변경하는 작업은 복사본에 한다. `Frame`의 동결은 메타데이터 대입을 막고 배열의 쓰기 가능 상태는 유지한다. 영상 소스가 배열 저장 공간을 재사용하는 경우, 반환한 프레임은 최소한 다음 읽기까지 유효하게 유지한다.
- 파일 평가는 원본의 모든 프레임을 처음부터 순서대로 한 번씩 읽고 처리한다. 화면 표시 모드도 같은 처리 경로를 사용한다. 일시정지 중에는 현재 화면을 유지하며 새 프레임을 읽거나 인덱스·감지·배경 모델·추적·매칭 상태를 갱신하지 않는다.

## 움직임 감지와 추적

- `BBox`는 왼쪽 위의 `(x, y)`와 픽셀 단위 너비·높이 `(w, h)`를 담는 `(x, y, w, h)`다. `Point`는 `(x, y)`이며 `Detection`에는 `bbox`와 `centroid`가 있다. 모든 좌표는 원본 프레임 기준 정수다.
- 감지 결과는 각 호출에서 새 리스트를 반환한다. 감지가 없으면 `[]`를 반환한다. 같은 감지 집합은 `bbox`, `centroid` 좌표 순으로 반환한다. 원시·후처리 마스크 확인 경로는 #5가 담당한다.
- `Tracker`는 매 프레임의 감지 목록을 받는다. 감지가 비어 있어도 `update([])`로 해당 프레임의 누락 상태를 반영한다. 트랙이 없으면 `[]`를 반환하며 활성 트랙은 `track_id` 오름차순의 새 리스트로 반환한다. 트랙 ID는 해당 Tracker 실행에서 새로 할당하며 삭제된 ID를 재사용하지 않는다.
- `TrackSnapshot`은 `track_id`, `bbox`, `centroid`, `trajectory`, `missed_frames`, `observed_this_frame`을 담는다. `trajectory`는 실제 관측된 중심점의 시간순 튜플이며 이전에 반환한 스냅샷은 후속 갱신과 독립적이다. `missed_frames`는 연속 미관측 프레임 수로, 현재 관측되면 0이다.
- 유지 중인 미관측 트랙은 `observed_this_frame=False`로 표시한다. 이때 남겨 둔 박스·중심점·궤적은 마지막 관측을 나타내며 현재 검출의 증거로 집계하지 않는다. `max_missed`는 Tracker 내부 유지 정책이다. 실제 대상이 있는 상태에서 연속 10프레임 이상 미검출 또는 ID 미부여인지 판단하는 실험 기준은 #8의 평가 규약을 따른다.
- `Tracker`는 영상 읽기, ORB 매칭과 GUI에 의존하지 않는다. 거리 계산, 일대일 매칭, 거리 제한과 동점 처리의 결정 규칙은 #6에서 검증한다.

## 등록 물체 매칭

- `TargetMatch`는 한 프레임의 `detected`, `reference_keypoints`, `frame_keypoints`, `good_matches`를 담는다. 두 특징점 수는 각 이미지에서 추출한 개수다. `good_matches`는 #7의 매칭 필터를 통과한 일대일 짝 개수로, 참조와 프레임 양쪽에서 같은 특징점을 중복 계산하지 않는다.
- `match_rate`는 `good_matches / reference_keypoints`로 계산한 0~1 사이의 비율이다. 참조 특징점이 0개이면 `None`으로 표시하고, 참조 특징점이 있고 유효 매칭이 0개이면 `0.0`이다. 참조 또는 프레임 특징점이 없으면 `good_matches=0`이고 `detected=False`다. 추출된 쪽의 특징점 수는 그대로 유지한다.
- `detected`는 #7의 발견 기준을 통과한 결과다. 유효한 매칭이 있어도 발견 기준에 미달할 수 있다. 타깃 매칭 기능이 꺼진 상태는 통합 코드에서 관리하며, 설정된 매처는 매 프레임에 `TargetMatch`를 반환한다.

파일과 테스트별 담당 범위는 작업 지침에 있다. 공통 계약과 변경 순서는 #3 조정 담당이 관리한다. [작업 지침](../AGENTS.md)
