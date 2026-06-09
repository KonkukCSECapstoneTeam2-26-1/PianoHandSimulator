# 프로젝트 13주차 활동서
**졸업프로젝트3201 2팀**
**활동 기간**: 2026년 5월 26일 ~ 2026년 6월 1일

---

1.

---

2.
**주요 활동**: 파트 간 데이터 인터페이스 설계 명세 작성

**세부 내용**: 각 파트 간에 전달되는 데이터를 명세한 인터페이스 설계 문서를 작성했음. 운지법 엔진(01_Fingering)이 IK(02_IK)로 넘기는 JSON 스키마 및 필드별 활용 목적, pitch → 건반 3D 좌표 변환 규칙, 손가락 번호 → UE5 본 이름 매핑을 정의하였음. 또한 IK가 Skinning(03_Skinning)으로 전달하는 Joint Transform 시퀀스 구조와 관절별 ROM 제약, Skinning이 Main(04_Main)으로 넘기는 Vertex Displacement 및 Tension Value 계산 수식을 포함한 전체 파이프라인의 인터페이스를 문서화하였음.

**향후 활동**: 파트 간 미확정 사항(건반 최대 누름 깊이, Vertex Displacement 전달 방식 등) 팀 내 협의 및 확정, UE5 연동을 위한 JSON → DataTable 변환 스크립트 작성 착수 예정.
