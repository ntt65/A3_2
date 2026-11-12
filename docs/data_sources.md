# 공개 평가 자료

[출처 목록](../experiments/data_sources.json)에 원본별 다운로드 URL, 바이트 수, SHA256, 확인한 영상 메타데이터를 기록했다. [사건 계획](../experiments/event_plan.json)은 원본 프레임 번호로 표기한다. 평가 자료의 원본 경로와 준비한 클립은 실행 기록에 각각 남긴다.

| 자료 | 원본 구성 | 사용 범위 |
| --- | --- | --- |
| OpenCV vtest | 768×576, 10 FPS, 795프레임 | 보행자 겹침과 정지. OpenCV 4.12.0 샘플을 사용한다. |
| OpenCV box 사진 쌍 | 참조 324×223, 장면 512×384 | 특징점 비교. 사진 속 상자는 vtest의 보행자 타깃과 별개다. |
| CAVIAR INRIA 로비 | MPEG2 10개, 384×288, 25 FPS, 수동 주석 XML | 단독 이동과 정지. XML의 객체 ID로 원본 장면의 인물을 지정한다. |
| Microsoft Wallflower LightSwitch | 160×120 BMP 2,715장, 4 Hz | 실제 소등·점등·소등. 원본 촬영 설명 `script.txt`를 함께 확인한다. |
| Microsoft Wallflower TimeOfDay | 160×120 BMP 5,890장, 4 Hz | 실제로 밝아지는 구간과 어두워지는 구간을 각각 25초 선택한다. 두 구간에서 사람이 소파로 이동해 앉는다. |

vtest는 기본 추적 영상이다. 영상 속 특정 보행자를 등록할 때는 평가 프레임과 분리한 원본 프레임의 좌표와 SHA256을 기록한다. 상자 사진 쌍의 통제 실험과 영상 추적은 입력과 관찰 결과를 별도로 기록한다. [OpenCV 4.12.0 샘플](https://github.com/opencv/opencv/tree/4.12.0/samples/data) · [OpenCV 배경 차분 예제](https://docs.opencv.org/4.12.0/d1/dc5/tutorial_background_subtraction.html)

CAVIAR의 공식 페이지에는 Creative Commons BY-SA 및 EC Funded CAVIAR project/IST 2001 37540 출처 표기 요청이 있다. 영상은 실제 사람이 시나리오를 연기한 고정 카메라 촬영이다. 동일 장면의 다른 각도나 반복 재생은 별도 사건으로 세지 않는다. 사용한 파일은 INRIA 로비 시퀀스다. MPEG 헤더의 프레임 수에는 오차가 있어 순차 디코딩 결과를 기록했다. 각 XML은 영상 마지막 프레임 직전까지 이어지고, 표본 원본 프레임에서 주석 상자가 지정 인물과 맞는 것을 확인했다. [CAVIAR 공식 데이터 및 이용 조건](https://homepages.inf.ed.ac.uk/rbf/CAVIARDATA1/)

Wallflower 원논문에서 실제 촬영과 4 Hz 샘플링을 확인했다. `LightSwitch.zip`의 소등 f812, 점등 f1853, 소등 f2188은 각각 원본 100프레임을 포함한 25초 클립으로 준비할 수 있다. 연구 또는 비상업 용도의 MSR 이용 조건은 `data/videos/wallflower/LICENSE.docx`에 있다. 파생 자료를 배포할 때는 같은 조건을 적용하고 변경 사실과 변경일을 명시한다. [Microsoft 배포처](https://www.microsoft.com/en-us/download/details.aspx?id=54651) · [Wallflower 원논문 §3](https://www.microsoft.com/en-us/research/wp-content/uploads/1999/09/wallflower_final_published.pdf)

`TimeOfDay.zip`의 `script.txt`에는 f0부터 밝아지고 최대 밝기에서 f3244부터 어두워지는 두 변화가 기록돼 있다. 밝아지는 중의 f1810–1909와 어두워지는 중의 f4718–4817을 사용한다. 사람이 각 구간의 f1831과 f4739에 들어온다. 4 Hz의 원본 100프레임은 각각 25초다. 각 클립의 첫 8프레임과 마지막 8프레임의 평균 회색조 이미지 차이를 확인했다. 밝아지는 구간의 전체 픽셀 중앙값은 +1.75, 어두워지는 구간은 −2.88이었다. 사람이 지나지 않는 우상단에서도 평균 변화가 각각 +2.72, −8.93이었다. [TimeOfDay 원본 ZIP](https://download.microsoft.com/download/E/7/6/E76CBD7B-7C3A-4D18-AA87-FC4B57DCCDAA/WallFlower/TimeOfDay.zip) · [Wallflower 원논문 §3](https://www.microsoft.com/en-us/research/wp-content/uploads/1999/09/wallflower_final_published.pdf)

예비 평가에서는 SBMnet `I_IL_01`의 실제 전등 점등과 `I_IL_02`의 블라인드 개방을 검토했다. 해당 배포본의 촬영 간격과 LASIESTA 전체 시퀀스에 대응하는 프레임 번호를 확인할 수 없어, 최종 두 사건의 입력을 원본 시간 간격이 확인된 TimeOfDay로 교체했다. [SBMnet 배포 목록](https://scenebackgroundmodeling.net/dataset/) · [LASIESTA 촬영 설명](https://ftp.gti.ssr.upm.es/data2/lasiesta_database.html)

## 확인과 클립 생성

저장소와 동일한 원본 경로 구성을 쓰는 디렉터리를 `--root`로 전달한다. `--check`를 지정하면 로컬 원본만 검증한다. 파일이 없을 때는 `--check`를 빼고 필요한 `--asset` ID를 선택할 수 있다. 이미 존재하는 파일은 SHA256을 확인한다.

```powershell
uv run --locked python tools/fetch_sample_data.py --root D:/git/A3_2 --check
uv run --locked python tools/prepare_evaluation_clips.py --source D:/git/A3_2/data/videos/vtest.avi --start 500 --end 749 --output outputs/evaluation/vtest-c.avi --mapping outputs/evaluation/vtest-c-frames.csv
uv run --locked python tools/prepare_evaluation_clips.py --source D:/git/A3_2/data/videos/wallflower/LightSwitch.zip --start 760 --end 859 --member-pattern 'b(?P<frame>\d{5})\.bmp' --fps 4 --output outputs/evaluation/wallflower-off-1.avi --mapping outputs/evaluation/wallflower-off-1-frames.csv
uv run --locked python tools/prepare_evaluation_clips.py --source D:/git/A3_2/tmp/rebuild-data/lasiesta/TimeOfDay.zip --start 1810 --end 1909 --member-pattern 'b(?P<frame>\d{5})\.bmp' --fps 4 --output outputs/evaluation/wallflower-brightening.avi --mapping outputs/evaluation/wallflower-brightening-frames.csv
```

도구는 FFV1 AVI를 다시 디코딩해 선택한 입력 픽셀, 프레임 수, 재생 FPS를 검증한다. CSV는 클립 프레임 번호, 원본 프레임 번호와 아카이브 파일명을 연결한다. 선택 구간의 모든 프레임을 순서대로 쓰며 프레임 추가나 보간을 하지 않는다.
