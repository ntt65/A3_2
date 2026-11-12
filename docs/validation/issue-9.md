# #9 앱 통합 검증

확인일 2026-11-13 (Asia/Seoul). Python 3.11.4, OpenCV 4.14.0, NumPy 2.4.6에서 실행했다. [이슈 #9](https://github.com/ntt65/A3_2/issues/9)

| 검증 | 결과 |
| --- | --- |
| `python -m unittest discover -s tests -v` | 61개 통과, 통합 테스트 6개 포함 |
| 독립 검토의 vtest 헤드리스 실행 | `completed/source_eof`, 795프레임, 원본 f0–794, 0.0–79.4초, 10 FPS |
| 실제 vtest 화면 | FPS·원본 프레임 번호·관측 트랙의 박스와 ID·궤적을 확인했다. |
| 실제 `p/s/s/p/s/q` | 일시정지 중 두 번 `s`를 눌러 f404를 저장했다. 재개 후 `s`는 f449를 저장했다. 두 PNG는 기록된 FFV1의 해당 프레임과 픽셀이 같았다. `q` 후 `stopped/user_quit`, 로그·FFV1 모두 499프레임이었다. |
| 내장 카메라 0 | Media Foundation 진단에서 640×480 BGR 프레임을 확인했다. 실제 앱에서 351프레임을 처리한 뒤 `q`로 종료했다. f0–350의 카메라 경과 시간이 단조 비감소했고 기록 범위는 약 0.438–12.094초였다. |

## 실행

```powershell
uv run --locked python -m unittest discover -s tests -v
uv run --locked python main.py --video data/videos/vtest.avi --target data/targets/box.png --headless --frame-log outputs/vtest.jsonl --summary-json outputs/vtest.json
uv run --locked python main.py --video data/videos/vtest.avi --frame-log outputs/gui.jsonl --summary-json outputs/gui.json --annotated-video outputs/displayed.mkv --snapshot-dir outputs/snapshots
uv run --locked python main.py --camera 0 --frame-log outputs/camera.jsonl --summary-json outputs/camera.json
```

독립 검토는 참조 사진을 켠 상태에서도 vtest의 795개 JSONL 행과 매칭률 분모를 확인했다. 해당 참조 사진은 vtest 영상 속 물체가 아니며, ORB 양성 사례는 앱 통합 테스트와 별도 특징점 실험에서 확인한다.

기본 실행 권한에서는 카메라 0 열기가 실패했다. 장치 접근이 허용된 실행에서 프레임을 읽고 종료했으며, Windows 설정 변경 없이 진행했다. 카메라 실행은 JSONL 메타데이터와 요약을 저장했다.
