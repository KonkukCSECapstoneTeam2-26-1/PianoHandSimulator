# 설계 다이어그램 — Mermaid 소스 (편집·재렌더용)

> 수정 후 재렌더:
> ```
> npx -y @mermaid-js/mermaid-cli -i "설계_다이어그램_mermaid소스.md" -o "images/diagrams/diagram.png" -b white -s 2
> ```
> 출력: mermaid 블록 순서대로 `diagram-1.png … diagram-8.png`.

---

## D1. 전체 시스템 컨텍스트

```mermaid
graph LR
  A["① MIDI → 운지법 생성"] --> B["② IK<br/>(손가락 포즈·관절)"]
  B --> C["③ Chaos Flesh<br/>(변형 표면 · 스트레인)"]
  V["④ 디테일 리소스<br/>텐션맵·핏줄맵·노멀맵"]
  C --> M
  B --> M
  V --> M
  subgraph SCOPE["★ 본 프로젝트 범위"]
    M["⑤ 고품질 디테일 스키닝 모듈"]
  end
  M --> R["⑥ 최종 렌더 메쉬"]

  classDef out fill:#eee,stroke:#999,color:#555;
  classDef ours fill:#ffe9b3,stroke:#e0a000,color:#000,stroke-width:2px;
  class A,B,C,V,R out;
  class M ours;
```

## D2. SW Architecture — 본 모듈 Top-Level 구조

```mermaid
graph TB
  subgraph UP["상위 모듈 / 리소스 (입력 · 범위 밖)"]
    UP2["IK / 본 : 관절 위치"]
    UP3["Chaos Flesh : 변형 표면 + 스트레인"]
    UP5["디테일 리소스<br/>텐션맵 · 핏줄맵 · 노멀맵"]
  end

  subgraph MOD["★ 고품질 디테일 스키닝 모듈"]
    A["A. 구동 신호 어댑터<br/>관절→마스크 · 스트레인→텐션 · 맵 바인딩"]
    B["B. 디테일 디스플레이스먼트 머티리얼<br/>주름·핏줄 변위 + 노멀 디테일 + Nanite 테셀"]
    A --> B
  end

  R["렌더러 (고품질 표면)"]

  UP2 --> A
  UP3 -->|"스트레인"| A
  UP5 --> A
  UP3 -->|"변형 표면 (입력 메쉬)"| B
  B --> R

  classDef ours fill:#ffe9b3,stroke:#e0a000,color:#000;
  class A,B ours;
```

## D3. 핵심 컴포넌트 분해 — B. 디테일 디스플레이스먼트 머티리얼 (3 디테일 항)

```mermaid
graph TB
  subgraph B["B. 디테일 디스플레이스먼트 머티리얼"]
    in["입력: 변형 표면"]
    tm["텐션맵<br/>(부위별 장력 필드)"]
    msk["관절 마스크"]
    vm["핏줄맵"]
    nm["디테일 노멀맵"]

    w["① 주름 변위 disp_w<br/>(텐션맵·마스크·다중사인)"]
    v["② 핏줄 변위 disp_v<br/>(핏줄맵·텐션 변조)"]
    n["③ 노멀 미세 디테일<br/>(노멀맵 ⊗ 텐션 블렌드)"]

    geo["disp = disp_w + disp_v<br/>→ ×Normal → World Position Offset"]
    tes["Nanite Tessellation<br/>(엔진 기능)"]
    nrm["섭동된 노멀 → 셰이딩"]

    in --> w
    tm --> w
    msk --> w
    tm --> v
    vm --> v
    tm --> n
    nm --> n
    w --> geo
    v --> geo
    tes --> geo
    n --> nrm
  end
```

## D4. 사용사례 다이어그램

```mermaid
graph LR
  art(("아티스트"))
  dev(("개발자 / TA"))
  ik(("«system»<br/>IK / 본"))
  flesh(("«system»<br/>Chaos Flesh"))

  subgraph S["고품질 디테일 스키닝 모듈"]
    u1(["UC1. 상위 입력·맵 수신"])
    u2(["UC2. 주름 변위 생성"])
    u3(["UC3. 핏줄 변위 생성"])
    u4(["UC4. 노멀맵 미세 디테일"])
    u5(["UC5. 테셀로 디테일 표현"])
    u6(["UC6. 디테일 맵·파라미터 저작·튜닝"])
    u7(["UC7. 결과 검증·캡처"])
  end

  ik --> u1
  flesh --> u1
  art --> u6
  dev --> u2
  dev --> u7

  u2 -.->|"«include»"| u1
  u3 -.->|"«include»"| u1
  u4 -.->|"«include»"| u1
  u2 -.->|"«include»"| u6
  u3 -.->|"«include»"| u6
  u4 -.->|"«include»"| u6
  u5 -.->|"«extend»"| u2
  u7 -.->|"«extend»"| u6
```

## D5. 클래스 다이어그램

```mermaid
classDiagram
  class DetailMaterial {
    +naniteTessellation : bool
    +WPO
    +outputNormal
    +evalDetail()
  }
  class DrivingAdapter {
    +jointMask
    +tensionMap
    +bindMaps()
  }
  class WrinkleTerm {
    +amp
    +freq
    +eval(tensionMap, mask)
  }
  class VeinTerm {
    +veinStrength
    +eval(veinMap, tension)
  }
  class NormalDetailTerm {
    +strength
    +eval(normalMap, tension)
  }
  class TensionMap
  class VeinMap
  class NormalMap

  DetailMaterial *-- WrinkleTerm
  DetailMaterial *-- VeinTerm
  DetailMaterial *-- NormalDetailTerm
  DrivingAdapter --> TensionMap : 갱신/바인딩
  WrinkleTerm ..> TensionMap
  VeinTerm ..> VeinMap
  VeinTerm ..> TensionMap
  NormalDetailTerm ..> NormalMap
  NormalDetailTerm ..> TensionMap
```

## D6. 시퀀스 다이어그램 (런타임)

```mermaid
sequenceDiagram
  autonumber
  participant IK as IK / 본
  participant CF as Chaos Flesh
  participant DA as 구동 어댑터
  participant Mat as 디테일 머티리얼
  participant GPU as Nanite 테셀 / 렌더러

  loop 매 프레임
    IK->>DA: 관절 위치
    CF->>DA: 변형 표면 + 스트레인
    DA->>DA: 마스크 갱신 · 스트레인→텐션맵 · 맵 바인딩
    DA->>Mat: 텐션맵 · 핏줄맵 · 노멀맵 · 마스크
    CF->>Mat: 변형 표면 (입력 메쉬)
    Mat->>Mat: disp = 주름(텐션맵) + 핏줄(핏줄맵)
    Mat->>Mat: 노멀 = 베이스 ⊗ 노멀맵(텐션 블렌드)
    Mat->>GPU: WPO(disp×N) + 섭동노멀 + 테셀
    GPU-->>IK: 다음 프레임
  end
```

## D7. 액티비티 다이어그램

```mermaid
flowchart TD
  s([입력·맵 수신]) --> a1["관절→마스크 / 스트레인→텐션맵 / 핏줄·노멀맵 바인딩"]
  a1 --> a2["Chaos Flesh 변형 표면을 입력 메쉬로 사용"]
  a2 --> a3["주름 변위 (텐션맵·마스크)"]
  a2 --> a4["핏줄 변위 (핏줄맵·텐션)"]
  a2 --> a5["노멀 미세 디테일 (노멀맵·텐션)"]
  a3 --> a6["disp 합성 → WPO"]
  a4 --> a6
  a6 --> a7["Nanite 테셀(엔진)"]
  a5 --> a8["섭동 노멀"]
  a7 --> a9["셰이딩·합성"]
  a8 --> a9
  a9 --> e([고품질 메쉬 출력])
```

## D8. 상태 다이어그램 (구현 단계)

```mermaid
stateDiagram-v2
  [*] --> S1
  S1 : 1단계 — 주름 변위(WPO, 전역 스칼라) [검증 완료]
  S2 : 2단계 — 텐션맵(부위별 필드) 구동
  S3 : 3단계 — 핏줄 변위(핏줄맵)
  S4 : 4단계 — 노멀맵 미세 디테일
  S5 : 5단계 — Nanite 테셀 + 실 손 메쉬 통합
  S1 --> S2 : 스칼라→텐션맵
  S2 --> S3 : 핏줄항 추가
  S3 --> S4 : 노멀 디테일 추가
  S4 --> S5 : 테셀·통합
  S5 --> [*]
```
