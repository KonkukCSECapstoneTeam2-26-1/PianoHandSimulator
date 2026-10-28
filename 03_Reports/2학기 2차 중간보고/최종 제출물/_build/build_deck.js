// 2학기 2차 중간발표 PPT 생성기
const path = require("path");
const pptxgen = require("pptxgenjs");

const REPO = "D:/Git/PianoHandSimulator";
const R2 = REPO + "/03_Reports/2학기 2차 중간보고";
const FIG = REPO + "/02_Implementation/01_Fingering/results/report_imgs";
const SKIN = REPO + "/02_Implementation/03_Skinning/Document/images";
const CROP = path.join(__dirname, "img");
const EMBED_VIDEO = process.env.EMBED_VIDEO !== "0";

const THEME = {
  name: "PianoHand Dark",
  headFontFace: "맑은 고딕",
  bodyFontFace: "맑은 고딕",
  colors: {
    dk1: "111111",   // 슬라이드 배경
    lt1: "FFFFFF",   // 밝은 본문/제목
    dk2: "1C1C21",   // 카드 면
    lt2: "9C9CA6",   // 보조 텍스트
    accent1: "D9A441", // 브라스 (주 강조)
    accent2: "4E9AC7", // 블루
    accent3: "D1544F", // 레드 (문제)
    accent4: "4FA87A", // 그린 (해결)
    accent5: "8B6FB0", // 퍼플
    accent6: "5E5E68", // 라인
    hlink: "D9A441",
    folHlink: "9C9CA6",
  },
};

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";            // 13.333 x 7.5
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.author = "정근녕";
pres.company = "졸업프로젝트 3201 2팀";
pres.subject = "IK와 Skinning을 통한 Piano Hand Simulator";
pres.title = "2학기 2차 중간발표";

const C = pres.SchemeColor;
const BG = C.text1, CARD = C.text2, WHITE = C.background1, MUTED = C.background2;
const GOLD = C.accent1, BLUE = C.accent2, RED = C.accent3, GREEN = C.accent4, LINE = C.accent6;

const H = { GOLD: "D9A441", CARD: "1C1C21", BG: "111111", LINE: "5E5E68",
            MUTED: "9C9CA6", RED: "D1544F", GREEN: "4FA87A", BLUE: "4E9AC7" };

const M = 0.62;            // 좌우 여백
const W = 13.333 - M * 2;  // 12.093
const BODY_Y = 1.62;

// ───────────────────────── 레이아웃 ─────────────────────────
const FOOTER = [
  { text: {
      text: "졸업프로젝트[3201] 2팀 · IK와 Skinning을 통한 Piano Hand Simulator",
      options: { x: M, y: 6.96, w: 9.0, h: 0.3, fontSize: 9, color: LINE, align: "left", isTextBox: true, margin: 0 },
  }},
];

pres.defineSlideMaster({ title: "COVER", background: { color: BG }, objects: [] });

pres.defineSlideMaster({
  title: "SECTION",
  background: { color: BG },
  objects: [
    { placeholder: { options: { name: "num", type: "body", x: M, y: 1.95, w: 3.2, h: 1.9,
        fontSize: 108, bold: true, color: GOLD, align: "left", valign: "middle", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "title", type: "title", x: 3.55, y: 2.14, w: 9.1, h: 0.9,
        fontSize: 40, bold: true, color: WHITE, align: "left", valign: "bottom", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: 3.62, y: 3.3, w: 9.1, h: 1.4,
        fontSize: 15, color: MUTED, align: "left", valign: "top", margin: 0 }, text: "" } },
  ],
  slideNumber: { x: 12.5, y: 6.96, w: 0.5, h: 0.3, fontSize: 9, color: LINE, align: "right" },
});

pres.defineSlideMaster({
  title: "CONTENT",
  background: { color: BG },
  objects: [
    { placeholder: { options: { name: "kicker", type: "body", x: M, y: 0.4, w: W, h: 0.26,
        fontSize: 11, bold: true, color: GOLD, charSpacing: 2, align: "left", valign: "middle", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "title", type: "title", x: M, y: 0.72, w: W, h: 0.66,
        fontSize: 29, bold: true, color: WHITE, align: "left", valign: "middle", margin: 0 }, text: "" } },
    ...FOOTER,
  ],
  slideNumber: { x: 12.5, y: 6.96, w: 0.5, h: 0.3, fontSize: 9, color: LINE, align: "right" },
});

// ───────────────────────── 헬퍼 ─────────────────────────
let _n = 0;
const oname = (p) => `${p}_${++_n}`;

function card(s, o) {
  s.addShape(pres.ShapeType.roundRect, {
    x: o.x, y: o.y, w: o.w, h: o.h, rectRadius: o.r === undefined ? 0.08 : o.r,
    fill: { color: o.fill || CARD },
    line: o.line === null ? { type: "none" } : { color: o.line || LINE, width: o.lw || 0.75 },
    objectName: oname("card"),
  });
}

function txt(s, text, o) {
  s.addText(text, Object.assign({ isTextBox: true, margin: 0, objectName: oname("txt") }, o));
}

function badge(s, x, y, label, d, fill, fg) {
  const dia = d || 0.44;
  s.addShape(pres.ShapeType.ellipse, {
    x, y, w: dia, h: dia, fill: { color: fill || H.GOLD }, line: { type: "none" },
    objectName: oname("badge"),
  });
  txt(s, label, { x, y, w: dia, h: dia, fontSize: dia > 0.5 ? 16 : 13, bold: true,
    color: fg || H.BG, align: "center", valign: "middle" });
}

// 큰 수치 타일 — 값과 라벨이 겹치지 않도록 고정 간격
function stat(s, o) {
  card(s, { x: o.x, y: o.y, w: o.w, h: o.h, fill: CARD, line: o.line || LINE });
  txt(s, [{ text: o.value, options: { fontSize: o.vs || 34, bold: true, color: o.color || WHITE } },
          { text: o.unit ? " " + o.unit : "", options: { fontSize: 14, bold: true, color: o.color || MUTED } }],
      { x: o.x + 0.22, y: o.y + 0.18, w: o.w - 0.44, h: 0.58, align: "left", valign: "middle" });
  txt(s, o.label, { x: o.x + 0.22, y: o.y + 0.82, w: o.w - 0.44, h: o.h - 0.94,
    fontSize: o.ls || 11.5, color: MUTED, align: "left", valign: "top", lineSpacingMultiple: 1.2 });
}

// 납작한 수치 카드 — 값과 라벨을 가로로 둔다
function statRow(s, o) {
  card(s, { x: o.x, y: o.y, w: o.w, h: o.h, fill: CARD, line: o.line || LINE });
  txt(s, [{ text: o.value, options: { fontSize: o.vs || 26, bold: true, color: o.color || WHITE } },
          { text: o.unit ? " " + o.unit : "", options: { fontSize: 12, bold: true, color: o.color || MUTED } }],
      { x: o.x + 0.24, y: o.y + 0.08, w: o.vw || 1.6, h: o.h - 0.16, align: "left", valign: "middle" });
  txt(s, o.label, { x: o.x + 0.26 + (o.vw || 1.6), y: o.y + 0.08, w: o.w - 0.5 - (o.vw || 1.6), h: o.h - 0.16,
    fontSize: 11, color: MUTED, align: "left", valign: "middle", lineSpacingMultiple: 1.2 });
}

function bullets(s, items, o) {
  const runs = items.map((it, i) => {
    const t = typeof it === "string" ? it : it.text;
    const b = typeof it === "string" ? {} : it;
    return {
      text: t,
      options: Object.assign({
        bullet: b.bullet === false ? false : { code: "2022", indent: 14 },
        color: b.color || MUTED,
        bold: !!b.bold,
        fontSize: b.fontSize || o.fontSize || 14,
        paraSpaceAfter: b.gap !== undefined ? b.gap : (o.gap === undefined ? 9 : o.gap),
        breakLine: i !== items.length - 1,
      }, b.options || {}),
    };
  });
  txt(s, runs, { x: o.x, y: o.y, w: o.w, h: o.h, align: "left", valign: "top",
    lineSpacingMultiple: o.lsm || 1.25 });
}

function chip(s, x, y, label, color, w) {
  const cw = w || 1.0;
  s.addShape(pres.ShapeType.roundRect, {
    x, y, w: cw, h: 0.26, rectRadius: 0.13, fill: { color: H.BG },
    line: { color: color, width: 0.75 }, objectName: oname("chip"),
  });
  txt(s, label, { x, y, w: cw, h: 0.26, fontSize: 9.5, bold: true, color: color,
    align: "center", valign: "middle" });
}

function newContent(kicker, title, section) {
  const s = pres.addSlide({ masterName: "CONTENT", sectionTitle: section });
  txt(s, kicker, { placeholder: "kicker" });
  txt(s, title, { placeholder: "title" });
  return s;
}

function lead(s, text) {
  txt(s, text, { x: M, y: BODY_Y - 0.08, w: W, h: 0.32, fontSize: 13, color: MUTED, valign: "middle" });
}

function divider(num, title, desc, owner, section) {
  const s = pres.addSlide({ masterName: "SECTION", sectionTitle: section });
  txt(s, num, { placeholder: "num" });
  txt(s, title, { placeholder: "title" });
  txt(s, desc, { placeholder: "body" });
  txt(s, owner, { x: 3.62, y: 4.46, w: 9.1, h: 0.3, fontSize: 12, bold: true,
    color: GOLD, align: "left", valign: "middle" });
  return s;
}

const SEC = { intro: "도입", fing: "01 운지법", ik: "02 IK",
              gpu: "03 GPU 스키닝", flesh: "04 Chaos Flesh", wrap: "05 통합과 마무리" };

// ═══════════════════ 1. 표지 ═══════════════════
pres.addSection({ title: SEC.intro });
{
  const s = pres.addSlide({ masterName: "COVER", sectionTitle: SEC.intro });
  s.addImage({ path: R2 + "/각종 손 캡쳐/비교사진_0_1.png",
    x: 6.9, y: 0, w: 6.433, h: 7.5, sizing: { type: "cover", w: 6.433, h: 7.5 },
    objectName: "cover_hands" });
  s.addImage({ path: CROP + "/veil.png", x: 6.9, y: 0, w: 2.4, h: 7.5, objectName: "cover_veil" });

  txt(s, "졸업프로젝트[3201] 2팀 · 2차 중간발표", { x: M, y: 1.46, w: 6.4, h: 0.3,
    fontSize: 12, bold: true, color: GOLD, charSpacing: 2, valign: "middle" });
  txt(s, "IK와 Skinning을 통한\nPiano Hand Simulator", { x: M, y: 1.92, w: 6.6, h: 1.85,
    fontSize: 40, bold: true, color: WHITE, valign: "top", lineSpacingMultiple: 1.18 });
  txt(s, "MIDI 파일 하나를 입력으로 받아, 사람이 실제로 칠 수 있는 운지법을 정하고\n그 손을 관절 단위로 움직여 살의 변형까지 그려 낸다.",
    { x: M, y: 3.82, w: 6.3, h: 0.8, fontSize: 13, color: MUTED, lineSpacingMultiple: 1.35 });

  s.addShape(pres.ShapeType.line, { x: M, y: 4.82, w: 2.2, h: 0,
    line: { color: H.GOLD, width: 1.5 }, objectName: "cover_rule" });

  const mem = [["정근녕", "운지법 결정 엔진"], ["한승현", "역운동학 (IK)"],
               ["이수민", "GPU 스키닝"], ["곽경민", "Chaos Flesh"]];
  mem.forEach((m, i) => {
    const col = i % 2, row = Math.floor(i / 2);
    const x = M + col * 3.1, y = 5.08 + row * 0.44;
    txt(s, m[0], { x, y, w: 0.9, h: 0.34, fontSize: 12.5, bold: true, color: WHITE, valign: "middle" });
    txt(s, m[1], { x: x + 0.95, y, w: 2.1, h: 0.34, fontSize: 11.5, color: MUTED, valign: "middle" });
  });

  txt(s, "지도교수  김형석          2026. 10. 30", { x: M, y: 6.22, w: 6.4, h: 0.3,
    fontSize: 11, color: LINE, valign: "middle" });

  s.addNotes("2팀 발표 시작합니다. 저희 주제는 MIDI 파일을 입력으로 받아 피아노를 치는 손을 시뮬레이션하는 것입니다.\n모듈은 네 개로 나뉘어 있고, 2차 발표의 핵심은 '각 모듈이 실제로 돌아가게 되었고, 서로 붙기 시작했다'는 점입니다.");
}

// ═══════════════════ 2. 목차 ═══════════════════
{
  const s = newContent("CONTENTS", "오늘 말씀드릴 것", SEC.intro);
  const items = [
    ["01", "프로젝트 개요와 2학기 변화", "무엇이 어떻게 달라졌는지"],
    ["02", "운지법 결정 엔진", "제약을 거는 단위를 바꾼 이야기 · 정근녕"],
    ["03", "역운동학 (IK)", "Weighted DLS와 건반 모델 연동 · 한승현"],
    ["04", "GPU 스키닝", "6‑Pass 정점 파이프라인 · 이수민"],
    ["05", "Chaos Flesh", "사면체 물리와 부피 보존 · 곽경민"],
    ["06", "모듈 통합과 남은 과제", "붙여 보니 드러난 것들"],
  ];
  items.forEach((it, i) => {
    const col = i % 2, row = Math.floor(i / 2);
    const x = M + col * (W / 2 + 0.16), y = BODY_Y + 0.18 + row * 1.62;
    const cw = W / 2 - 0.16;
    card(s, { x, y, w: cw, h: 1.34, line: LINE });
    badge(s, x + 0.3, y + 0.41, it[0], 0.52);
    txt(s, it[1], { x: x + 1.02, y: y + 0.3, w: cw - 1.28, h: 0.36, fontSize: 16, bold: true,
      color: WHITE, valign: "middle" });
    txt(s, it[2], { x: x + 1.02, y: y + 0.72, w: cw - 1.28, h: 0.42, fontSize: 11.5,
      color: MUTED, valign: "top" });
  });
  s.addNotes("순서는 개요 먼저, 그다음 모듈 네 개, 마지막에 통합과 남은 과제입니다.\n모듈별 발표자는 해당 파트 담당자가 이어서 말씀드립니다.");
}

// ═══════════════════ 3. 1학기 대비 2학기 ═══════════════════
{
  const s = newContent("OVERVIEW", "1학기와 2학기, 무엇이 달라졌는가", SEC.intro);
  lead(s, "1학기는 \"이 방법이 되는가\"를 확인하는 단계였고, 2학기는 \"실제로 돌아가게 만들고 서로 붙이는\" 단계다.");

  const rows = [
    ["각 모듈", "알고리즘이 성립하는지 검증", "실제 데이터로 동작하는 구현"],
    ["모듈 간", "문서상의 인터페이스 약속", "코드 수준 공유 상수 · 실파일 연동"],
    ["스키닝", "포스트프로세스 사전 검증", "정점 처리 단계 6‑Pass 파이프라인"],
    ["물리", "Chaos Flesh 적용 가능성 확인", "TetWild 사면체 + 렌더 메시 바인딩"],
    ["검증", "눈으로 보고 판단", "지표 자동 측정 + 회귀 테스트 5종"],
  ];
  const ty = BODY_Y + 0.82, rh = 0.84;
  const colX = [M, M + 2.5, M + 7.0];
  const colW = [2.5, 4.5, W - 7.0];
  txt(s, "1학기", { x: colX[1] + 0.2, y: ty - 0.36, w: colW[1], h: 0.28, fontSize: 11, bold: true,
    color: MUTED, charSpacing: 1.5, valign: "middle" });
  txt(s, "2학기", { x: colX[2] + 0.2, y: ty - 0.36, w: colW[2], h: 0.28, fontSize: 11, bold: true,
    color: GOLD, charSpacing: 1.5, valign: "middle" });
  rows.forEach((r, i) => {
    const y = ty + i * rh;
    if (i % 2 === 0) card(s, { x: M, y: y, w: W, h: rh - 0.1, fill: CARD, line: null, r: 0.05 });
    txt(s, r[0], { x: colX[0] + 0.2, y: y + 0.06, w: colW[0] - 0.3, h: rh - 0.22,
      fontSize: 13.5, bold: true, color: WHITE, valign: "middle" });
    txt(s, r[1], { x: colX[1] + 0.2, y: y + 0.06, w: colW[1] - 0.6, h: rh - 0.22,
      fontSize: 12.5, color: LINE, valign: "middle" });
    s.addShape(pres.ShapeType.rightArrow, { x: colX[1] + colW[1] - 0.42, y: y + rh / 2 - 0.17,
      w: 0.3, h: 0.14, fill: { color: H.GOLD }, line: { type: "none" }, objectName: oname("arr") });
    txt(s, r[2], { x: colX[2] + 0.2, y: y + 0.06, w: colW[2] - 0.3, h: rh - 0.22,
      fontSize: 12.5, color: WHITE, valign: "middle" });
  });
  s.addNotes("왼쪽이 1학기, 오른쪽이 2학기입니다.\n핵심은 '검증' 줄입니다. 1학기에는 눈으로 보고 괜찮다고 판단했는데, 그 방식으로는 놓치는 결함이 많았습니다. 뒤에서 그 이야기를 하겠습니다.");
}

// ═══════════════════ 4. 전체 파이프라인 ═══════════════════
{
  const s = newContent("ARCHITECTURE", "전체 파이프라인과 모듈 간 인터페이스", SEC.intro);

  const boxes = [
    { label: "MIDI 파일", sub: "실곡 13곡 + 기준 8곡", color: H.LINE, owner: "" },
    { label: "01 운지법", sub: "화음 DP + 시간 제약", color: H.GOLD, owner: "정근녕" },
    { label: "02 IK", sub: "Weighted DLS", color: H.BLUE, owner: "한승현" },
    { label: "03 스키닝", sub: "GPU 6‑Pass · Chaos Flesh", color: H.GREEN, owner: "이수민 · 곽경민" },
    { label: "UE5 렌더", sub: "최종 영상", color: H.MUTED, owner: "" },
  ];
  const bw = 2.12, gap = 0.44, by = 3.30, bh = 1.5;
  const startX = M + 0.18;
  boxes.forEach((b, i) => {
    const x = startX + i * (bw + gap);
    card(s, { x, y: by, w: bw, h: bh, line: b.color, lw: 1.1 });
    txt(s, b.label, { x: x + 0.1, y: by + 0.32, w: bw - 0.2, h: 0.34, fontSize: 14.5, bold: true,
      color: WHITE, align: "center", valign: "middle" });
    txt(s, b.sub, { x: x + 0.1, y: by + 0.72, w: bw - 0.2, h: 0.46, fontSize: 10,
      color: MUTED, align: "center", valign: "top", lineSpacingMultiple: 1.2 });
    if (b.owner) txt(s, b.owner, { x: x, y: by + bh + 0.14, w: bw, h: 0.26, fontSize: 10,
      bold: true, color: b.color, align: "center", valign: "middle" });
    if (i < boxes.length - 1) {
      s.addShape(pres.ShapeType.rightArrow, { x: x + bw + 0.09, y: by + bh / 2 - 0.09,
        w: 0.26, h: 0.18, fill: { color: H.LINE }, line: { type: "none" }, objectName: oname("flow") });
    }
  });

  const ifs = [
    { i: 1, name: "A", desc: "*_polyphonic_result.json\n*_fingering.csv" },
    { i: 2, name: "B", desc: "joints.csv + wrist.csv\n30 FPS → AnimSequence" },
    { i: 3, name: "C", desc: "정점 버퍼\nlerp(스키닝, Flesh, Blend)" },
  ];
  ifs.forEach((f) => {
    const cx = startX + f.i * (bw + gap) - gap / 2;
    s.addShape(pres.ShapeType.line, { x: cx, y: by - 0.5, w: 0, h: 0.5,
      line: { color: H.GOLD, width: 0.75, dashType: "sysDot" }, objectName: oname("ifl") });
    badge(s, cx - 0.16, by - 0.84, f.name, 0.32);
    txt(s, f.desc, { x: cx - 1.35, y: by - 1.52, w: 2.7, h: 0.58, fontSize: 9.5,
      color: MUTED, align: "center", valign: "bottom", fontFace: "Consolas", lineSpacingMultiple: 1.2 });
  });

  card(s, { x: M, y: 5.52, w: W, h: 1.16, fill: CARD, line: null });
  txt(s, [
    { text: "2차에서 달라진 점 — ", options: { bold: true, color: H.GOLD, fontSize: 13.5 } },
    { text: "A·B·C 모두 실제 파일이 오가는 상태가 되었다. 1차에서는 전부 문서상의 약속이었다.",
      options: { color: "FFFFFF", fontSize: 13.5, breakLine: true } },
    { text: "좌표 단위는 mm로 통일하고, UE5(cm)는 소비하는 쪽에서 ÷10 한다.",
      options: { color: H.MUTED, fontSize: 11.5 } },
  ], { x: M + 0.32, y: 5.72, w: W - 0.64, h: 0.8, valign: "middle", lineSpacingMultiple: 1.4 });

  s.addNotes("왼쪽부터 MIDI가 들어와서 운지법이 손가락을 정하고, IK가 관절 각도를 만들고, 스키닝이 살을 그립니다.\n박스 사이 A·B·C가 모듈 간 인터페이스입니다. 2차에서는 이 세 군데 모두 실제 파일이 흐릅니다.\n단위는 mm로 통일했습니다. 이게 왜 중요한지는 뒤에서 말씀드립니다.");
}

// ═══════════════════ 01 운지법 ═══════════════════
pres.addSection({ title: SEC.fing });
divider("01", "운지법 결정 엔진",
  "MIDI의 음표 하나하나에 어느 손 몇 번 손가락을 쓸지 정한다.\n사람이 실제로 칠 수 있는 손 모양이어야 하므로, 물리 제약을 만족하는 배정만 허용한다.",
  "정근녕", SEC.fing);

{
  const s = newContent("01 운지법", "모듈의 역할과 처리 흐름", SEC.fing);
  const steps = [
    ["MIDI 파싱", "전 트랙 템포맵을 모아\ntick → ms 로 변환", false],
    ["손 분리 · 화음 그룹화", "양손에 음을 나누고\n동시 타건을 묶는다", false],
    ["화음 단위 DP", "빔 폭 120으로 가지치기한\n동적 계획법", false],
    ["시간 제약 해소", "순간 단위로 손가락 충돌과\n손 범위를 다시 검사", true],
    ["점유 구간 산출", "페달을 걷어내고\nkey_hold_ms 를 계산", true],
    ["출력", "JSON / UE5 DataTable CSV\n+ 평가 지표", false],
  ];
  const cw = (W - 0.4 * 2) / 3, ch = 2.26;
  steps.forEach((st, i) => {
    const col = i % 3, row = Math.floor(i / 3);
    const x = M + col * (cw + 0.4), y = BODY_Y + 0.1 + row * (ch + 0.3);
    card(s, { x, y, w: cw, h: ch, line: st[2] ? H.GOLD : LINE, lw: st[2] ? 1.1 : 0.75 });
    badge(s, x + 0.28, y + 0.3, String(i + 1), 0.46);
    if (st[2]) chip(s, x + cw - 1.36, y + 0.38, "2학기 신규", H.GOLD, 1.08);
    txt(s, st[0], { x: x + 0.28, y: y + 0.92, w: cw - 0.56, h: 0.38, fontSize: 15, bold: true,
      color: WHITE, valign: "middle" });
    txt(s, st[1], { x: x + 0.28, y: y + 1.36, w: cw - 0.56, h: 0.72, fontSize: 11.5,
      color: MUTED, valign: "top", lineSpacingMultiple: 1.3 });
  });
  s.addNotes("운지법 엔진은 여섯 단계로 돌아갑니다.\n1학기에는 3번 DP까지였고, 2학기에 4번과 5번이 새로 들어왔습니다. 금색으로 표시한 두 단계가 오늘 말씀드릴 핵심입니다.");
}

{
  const s = newContent("01 운지법 · 핵심", "제약을 화음 단위로 걸고 있었다", SEC.fing);
  lead(s, "손이 닿는 범위, 한 손가락은 한 건반, 손가락 순서 — 이 제약들은 모두 \"시간상의 한 순간\"에 성립해야 한다.");

  s.addImage({ path: CROP + "/diag_constraint_unit.png", x: 0.95, y: 1.94, w: 11.44, h: 3.74,
    objectName: "diag_constraint" });

  const tw = (W - 0.3 * 2) / 3;
  [
    { v: "3", u: "건", l: "화음 단위로 셌을 때의\n실제 데이터 위반", c: "FFFFFF", ln: H.LINE, vw: 1.5 },
    { v: "2,552", u: "건", l: "순간 단위로 셌을 때의\n같은 데이터 위반", c: H.RED, ln: H.RED, vs: 24, vw: 1.7 },
    { v: "0", u: "건", l: "재정의 후 현재\n21곡 전체", c: H.GREEN, ln: H.GREEN, vw: 1.5 },
  ].forEach((d, i) => {
    statRow(s, { x: M + i * (tw + 0.3), y: 5.82, w: tw, h: 1.02, value: d.v, unit: d.u,
      color: d.c, label: d.l, vs: d.vs, vw: d.vw, line: d.ln });
  });

  s.addNotes("여기가 2학기 운지법 작업의 중심입니다.\n손이 닿는 범위나 손가락 충돌 같은 제약은 '어느 순간'에 성립해야 하는 조건인데, 엔진은 화음이라는 묶음 단위로 검사하고 있었습니다.\n화음은 시간을 나누지 않습니다. 앞 화음의 지속음이 다음 화음까지 걸쳐 있으면 그 겹침이 보이지 않습니다.\n검사 단위를 바꾸자 3건이던 위반이 2,552건으로 드러났습니다. 없던 문제가 생긴 게 아니라, 원래 있었는데 못 보던 것입니다. 지금은 0건입니다.");
}

{
  const s = newContent("01 운지법 · 핵심", "소리의 지속과 손가락의 점유는 다르다", SEC.fing);

  card(s, { x: M, y: BODY_Y - 0.02, w: W, h: 0.96, fill: CARD, line: null });
  txt(s, [
    { text: "MIDI의 note_off 는 페달 때문에 늘어난 ", options: { fontSize: 14, color: "FFFFFF" } },
    { text: "소리", options: { fontSize: 14, bold: true, color: H.GOLD } },
    { text: "의 끝이지, 손가락이 건반에서 떨어진 시점이 아니다.", options: { fontSize: 14, color: "FFFFFF", breakLine: true } },
    { text: "그래서 점유 시간을 뜻하는 key_hold_ms 를 따로 두고, 제약 검사와 IK 입력은 이 값을 쓰도록 했다.",
      options: { fontSize: 12, color: H.MUTED } },
  ], { x: M + 0.32, y: BODY_Y + 0.14, w: W - 0.64, h: 0.7, valign: "middle", lineSpacingMultiple: 1.4 });

  const my = BODY_Y + 1.28;
  txt(s, "드뷔시 '달빛'에서 측정한 결과", { x: M, y: my, w: 6, h: 0.3, fontSize: 12.5,
    bold: true, color: GOLD, valign: "middle" });
  const sw = (W - 0.36 * 3) / 4;
  [
    { v: "76.7", u: "%", l: "곡 전체에서 페달이\n눌려 있던 시간 비율", c: "FFFFFF" },
    { v: "87", u: "%", l: "손가락 충돌 111건 중\n페달 구간에서 발생 (97건)", c: H.RED },
    { v: "3,000", u: "ms", l: "같은 손가락이 두 건반을\n동시에 잡던 최대 중첩", c: H.RED, vs: 30 },
    { v: "0", u: "ms", l: "key_hold_ms 적용 후\n최대 중첩", c: H.GREEN },
  ].forEach((d, i) => {
    stat(s, { x: M + i * (sw + 0.36), y: my + 0.4, w: sw, h: 1.88, value: d.v, unit: d.u,
      color: d.c, label: d.l, vs: d.vs, line: d.c === H.GREEN ? H.GREEN : H.LINE });
  });

  card(s, { x: M, y: my + 2.54, w: W, h: 1.18, fill: CARD, line: H.GOLD });
  txt(s, [
    { text: "IK 파트에 드리는 당부 — ", options: { bold: true, color: H.GOLD, fontSize: 13.5 } },
    { text: "건반에서 손가락을 떼는 시점은 반드시 ", options: { color: "FFFFFF", fontSize: 13.5 } },
    { text: "start_ms + key_hold_ms", options: { color: H.GOLD, fontSize: 13.5, fontFace: "Consolas", bold: true } },
    { text: " 를 쓸 것.", options: { color: "FFFFFF", fontSize: 13.5, breakLine: true } },
    { text: "duration_ms 로 떼면 한 손가락이 서로 다른 건반을 동시에 누르는 자세가 만들어진다.",
      options: { color: H.MUTED, fontSize: 11.5 } },
  ], { x: M + 0.32, y: my + 2.72, w: W - 0.64, h: 0.82, valign: "middle", lineSpacingMultiple: 1.4 });

  s.addNotes("두 번째 발견입니다.\n피아노는 페달을 밟으면 손가락을 떼도 소리가 계속 납니다. MIDI의 note_off는 그 소리가 끝난 시점이지 손가락이 떨어진 시점이 아닙니다.\n달빛은 곡의 76.7% 동안 페달이 밟혀 있었고, 손가락 충돌 111건 중 97건이 페달 구간이었습니다. 즉 대부분이 이 착각 때문이었습니다.\n마지막 줄이 IK 파트에 중요합니다. duration_ms로 건반을 떼면 한 손가락이 두 건반을 동시에 누르는 자세가 나옵니다.");
}

{
  const s = newContent("01 운지법 · 결과", "21곡에서 물리 제약 위반 0건", SEC.fing);
  const sw2 = (W - 0.34 * 4) / 5;
  [
    { v: "21", u: "곡", l: "실곡 13곡 + 기준 8곡", c: "FFFFFF" },
    { v: "0", u: "건", l: "물리 제약 위반", c: H.GREEN },
    { v: "0.000", u: "ms", l: "템포 변화 구간\n타이밍 오차", c: H.GREEN, vs: 28 },
    { v: "85.2", u: "%", l: "음표 보존율", c: "FFFFFF" },
    { v: "17.8", u: "초", l: "21곡 전체 처리 시간", c: "FFFFFF" },
  ].forEach((d, i) => {
    stat(s, { x: M + i * (sw2 + 0.34), y: BODY_Y, w: sw2, h: 1.56, value: d.v, unit: d.u,
      color: d.c, label: d.l, vs: d.vs, line: d.c === H.GREEN ? H.GREEN : H.LINE });
  });

  s.addImage({ path: FIG + "/fig2_finger_dist.png", x: M, y: BODY_Y + 1.84, w: 5.9, h: 2.88,
    sizing: { type: "contain", w: 5.9, h: 2.88 }, objectName: "fig_finger_dist" });
  s.addImage({ path: FIG + "/fig5_role_dist.png", x: M + 6.2, y: BODY_Y + 1.84, w: 5.89, h: 2.75,
    sizing: { type: "contain", w: 5.89, h: 2.75 }, objectName: "fig_role_dist" });
  txt(s, "손가락별 사용 분포 — 엄지와 검지에 쏠리지 않고 고르게 퍼져 있다",
    { x: M, y: BODY_Y + 4.78, w: 5.9, h: 0.26, fontSize: 10, color: LINE, align: "center" });
  txt(s, "성부 역할 분포 — 멜로디·베이스·내성을 구분해 손을 나눈다",
    { x: M + 6.2, y: BODY_Y + 4.78, w: 5.89, h: 0.26, fontSize: 10, color: LINE, align: "center" });

  s.addNotes("현재 결과입니다. 21곡에서 물리 제약 위반 0건입니다.\n타이밍 오차 0.000ms는 템포가 바뀌는 곡에서도 시간 계산이 정확하다는 뜻입니다. 전에는 템포 변화를 첫 번째 값으로만 처리해서 58.7% 오차가 났습니다.\n음표 보존율 85.2%는 나머지 15%를 버렸다는 뜻인데, 밴드 편곡 곡처럼 애초에 두 손으로 못 치는 구간에 몰려 있습니다.");
}

{
  const s = newContent("01 운지법 · 검증", "위반이 엔진 탓인지 입력 탓인지 구분할 수 없었다", SEC.fing);

  const lw2 = 5.75, ch5 = 2.62;
  card(s, { x: M, y: BODY_Y, w: lw2, h: ch5, line: H.RED });
  chip(s, M + 0.28, BODY_Y + 0.24, "문제", H.RED, 0.85);
  txt(s, "게임 음악 MIDI는 애초에\n두 손으로 칠 수 없다", { x: M + 0.28, y: BODY_Y + 0.6, w: lw2 - 0.56, h: 0.76,
    fontSize: 16, bold: true, color: WHITE, valign: "top", lineSpacingMultiple: 1.25 });
  bullets(s, [
    "밴드 편곡을 그대로 받으면 동시에 10음이 넘는다",
    "위반이 나와도 엔진 결함인지 입력 탓인지 알 수 없다",
    "1학기 내내 deb_clai 와 Super Mario 두 곡으로만 검증했다",
    "그런데 이 둘은 유독 깨끗한 샘플이었다",
  ], { x: M + 0.3, y: BODY_Y + 1.44, w: lw2 - 0.6, h: 1.1, fontSize: 11.5, gap: 6 });

  card(s, { x: M + lw2 + 0.32, y: BODY_Y, w: W - lw2 - 0.32, h: ch5, line: H.GREEN });
  chip(s, M + lw2 + 0.6, BODY_Y + 0.24, "대응", H.GREEN, 0.85);
  txt(s, "연주 가능함이 보장된\n기준 코퍼스 8곡을 직접 만들었다", { x: M + lw2 + 0.6, y: BODY_Y + 0.6,
    w: W - lw2 - 0.88, h: 0.76, fontSize: 16, bold: true, color: WHITE, valign: "top", lineSpacingMultiple: 1.25 });
  bullets(s, [
    "5지 포지션 · 블록 코드 · 알베르티 · 페달 아르페지오",
    "지속 베이스 · 포지션 이동 · 내성 · 음계",
    "여기서 나는 위반은 전부 엔진 결함이다",
    "판정의 모호함이 사라진다",
  ], { x: M + lw2 + 0.62, y: BODY_Y + 1.44, w: W - lw2 - 0.92, h: 1.1, fontSize: 11.5, gap: 6 });

  const by2 = BODY_Y + ch5 + 0.22;
  const sw3 = (W - 0.36 * 2) / 3;
  stat(s, { x: M, y: by2, w: sw3, h: 1.5, value: "81.6", unit: "%", color: "FFFFFF",
    label: "실곡 위반 시점 중, 애초에 어떤 운지법으로도\n연주가 불가능한 구간이 차지하는 비율", line: H.LINE, ls: 11 });
  stat(s, { x: M + sw3 + 0.36, y: by2, w: sw3, h: 1.5, value: "8", unit: "곡", color: H.GREEN,
    label: "기준 코퍼스 ref_01 ~ ref_08\n엔진 검증은 이쪽으로만 판단한다", line: H.GREEN, ls: 11 });
  stat(s, { x: M + (sw3 + 0.36) * 2, y: by2, w: sw3, h: 1.5, value: "5", unit: "종", color: "FFFFFF",
    label: "회귀 테스트 — 타이밍 · 건반 좌표\n지표 · 점유 산출 · 기준 코퍼스", line: H.LINE, ls: 11 });

  txt(s, "결론: 실곡에서 나오는 위반 수는 엔진의 정확도가 아니라 입력 MIDI의 연주 가능성을 나타내는 지표다. 두 가지를 섞어서 보면 안 된다.",
    { x: M, y: by2 + 1.66, w: W, h: 0.3, fontSize: 12, color: GOLD, valign: "middle" });

  s.addNotes("이 부분이 2학기에 일하는 방식을 바꾼 지점입니다.\n게임 음악 MIDI는 밴드 편곡이라 동시에 10음이 넘는 구간이 흔합니다. 위반이 나와도 엔진이 틀린 건지 입력이 못 칠 곡인 건지 알 수가 없었습니다.\n그래서 사람이 확실히 칠 수 있는 8곡을 직접 만들었습니다. 여기서 나는 위반은 전부 엔진 결함입니다.\n1학기에는 두 곡으로만 검증했는데, 공교롭게도 둘 다 깨끗한 샘플이어서 결함이 가려져 있었습니다.");
}

// ═══════════════════ 02 IK ═══════════════════
pres.addSection({ title: SEC.ik });
divider("02", "역운동학 (IK)",
  "운지법이 정한 \"어느 손가락이 어느 건반을\"을 받아, 그 손가락 끝이 건반에 닿는 관절 각도를 구한다.\n실시간이 아니라 오프라인 사전 계산이므로 수렴 속도보다 정확도를 우선한다.",
  "한승현", SEC.ik);

{
  const s = newContent("02 IK", "Weighted Damped Least Squares", SEC.ik);

  card(s, { x: M, y: BODY_Y, w: W, h: 1.26, fill: CARD, line: H.BLUE });
  txt(s, "Δθ  =  W⁻¹Jᵀ ( J W⁻¹Jᵀ + λ²I )⁻¹ Δe",
    { x: M, y: BODY_Y + 0.18, w: W, h: 0.56, fontSize: 24, bold: true, color: WHITE,
      align: "center", valign: "middle" });
  txt(s, "J 는 자코비안, W 는 관절별 가중치, λ 는 감쇠 계수, Δe 는 목표까지의 오차",
    { x: M, y: BODY_Y + 0.78, w: W, h: 0.3, fontSize: 11.5, color: MUTED, align: "center", valign: "middle" });

  const items = [
    { t: "감쇠항 λ²I", d: "특이점 근처에서 역행렬이 발산하는 것을 막는다.\n해가 조금 부정확해지는 대신 안정적으로 수렴한다." },
    { t: "가중치 W", d: "관절 한계에 가까워질수록 가중치를 낮춰\n그 관절을 덜 움직인다. 급정지 대신 부드럽게 감속." },
    { t: "수렴 조건", d: "반복 40회, 허용 오차 0.01.\n오프라인 계산이므로 반복 수에 여유를 둔다." },
    { t: "손목 궤적", d: "손목은 직선이 아니라 베지어 아치로 이동한다.\n( ) arcMultiplier · wristReachMargin" },
  ];
  const cw2 = (W - 0.36) / 2, ch2 = 1.56;
  items.forEach((it, i) => {
    const col = i % 2, row = Math.floor(i / 2);
    const x = M + col * (cw2 + 0.36), y = BODY_Y + 1.66 + row * (ch2 + 0.32);
    card(s, { x, y, w: cw2, h: ch2, line: LINE });
    txt(s, it.t, { x: x + 0.3, y: y + 0.22, w: cw2 - 0.6, h: 0.34, fontSize: 15, bold: true,
      color: GOLD, valign: "middle" });
    txt(s, it.d, { x: x + 0.3, y: y + 0.64, w: cw2 - 0.6, h: 0.78, fontSize: 12,
      color: MUTED, valign: "top", lineSpacingMultiple: 1.3 });
  });

  s.addNotes("IK는 Weighted DLS를 씁니다.\n일반 자코비안 역행렬은 특이점에서 발산하는데, 감쇠항을 넣어 막습니다.\n가중치는 관절 한계에 가까워지면 낮아져서, 한계에 부딪혀 급정지하는 대신 부드럽게 감속합니다.\n오프라인 계산이라 반복 40회까지 여유 있게 돌립니다.");
}

{
  const s = newContent("02 IK", "실제 비율 건반에 양손 10손가락 타건", SEC.ik);
  const vw = 6.95, vh = 3.9, vy = BODY_Y + 0.2;
  if (EMBED_VIDEO) {
    s.addMedia({ type: "video", path: R2 + "/KakaoTalk_20261028_173251429.mp4",
      x: M, y: vy, w: vw, h: vh });
  } else {
    s.addImage({ path: CROP + "/ik_vulkan.png", x: M, y: vy, w: vw, h: vh,
      sizing: { type: "contain", w: vw, h: vh }, objectName: "ik_vulkan" });
  }
  txt(s, "IK 솔버 출력 — 슬라이드에서 바로 재생한다  (KakaoTalk_20261028_173251429.mp4)",
    { x: M, y: vy + vh + 0.14, w: vw, h: 0.28, fontSize: 10, color: LINE, align: "center" });

  bullets(s, [
    { text: "실제 비율 건반 위에서 양손 10손가락이 움직인다", bold: true, color: "FFFFFF" },
    "흑건은 건반 안쪽, 백건은 앞쪽 — 타건 지점을 구분한다",
    "엄지 뿌리를 CMC 위치로 옮기고 타건 지점 조정",
    { text: "출력: joints.csv + wrist.csv (30 FPS)", bold: true, color: "FFFFFF" },
    "frame, time_ms, bone, flex_deg, abd_deg, twist_deg",
    "오른손 15행 / 프레임",
    "달빛 전곡 248초 · 7,447프레임 → 4초 만에 내보냄",
    { text: "검증기 RESULT: OK", bold: true, color: H.GREEN },
    { text: "A_IK_DebClai 애니메이션 생성 완료", bold: true, color: H.GREEN },
  ], { x: M + vw + 0.36, y: vy + 0.02, w: W - vw - 0.36, h: 4.3, fontSize: 12, gap: 10 });

  s.addNotes("실제 비율 건반 위에서 양손이 움직입니다. 왼쪽이 IK 솔버가 직접 그린 화면입니다.\n흑건과 백건은 타건 지점이 다릅니다. 흑건은 건반 안쪽을, 백건은 앞쪽을 누릅니다.\n출력은 관절 각도 CSV이고, 달빛 전곡 7,447프레임을 4초 만에 내보냅니다. 검증기를 통과했고 UE5 애니메이션까지 만들었습니다.\n영상을 보시면 손목이 부자연스럽게 돌아가는 구간이 있는데, 마지막 통합 파트에서 원인을 말씀드립니다.");
}

{
  const s = newContent("02 IK", "결과와 알려진 한계", SEC.ik);

  txt(s, "확보한 것", { x: M, y: BODY_Y - 0.04, w: 5.8, h: 0.3, fontSize: 12, bold: true,
    color: GOLD, charSpacing: 1.5, valign: "middle" });
  card(s, { x: M, y: BODY_Y + 0.34, w: 5.8, h: 2.1, line: H.GREEN });
  bullets(s, [
    "양손 10손가락이 실제 비율 건반을 친다",
    "관절 각도를 CSV로 내보내고 검증기로 확인한다",
    "UE5 AnimSequence 임포트까지 연결됐다",
    "달빛 전곡 248초 · 7,447프레임 변환 완료",
  ], { x: M + 0.32, y: BODY_Y + 0.6, w: 5.8 - 0.64, h: 1.7, fontSize: 12.5, gap: 10 });

  txt(s, "알려진 한계", { x: M + 6.1, y: BODY_Y - 0.04, w: W - 6.1, h: 0.3, fontSize: 12,
    bold: true, color: H.RED, charSpacing: 1.5, valign: "middle" });
  card(s, { x: M + 6.1, y: BODY_Y + 0.34, w: W - 6.1, h: 2.1, line: H.RED });
  bullets(s, [
    "마디 길이를 MetaHuman 실측값으로 바꾼 뒤 소지(5번) 오차가 35% → 57% 로 늘었다",
    "한 프레임에 관절 각도가 40~120° 점프하는 구간이 있다 (middle_02_r 123°)",
    "프레임 0에서 중간 마디가 84~97° 굽은 채 시작 — 기본 굽힘 포함 여부 확인 필요",
  ], { x: M + 6.42, y: BODY_Y + 0.6, w: W - 6.1 - 0.64, h: 1.7, fontSize: 12.5, gap: 10 });

  const by3 = BODY_Y + 2.72;
  card(s, { x: M, y: by3, w: 7.3, h: 1.94, fill: CARD, line: H.GOLD });
  txt(s, "채워야 할 수치  —  한승현", { x: M + 0.32, y: by3 + 0.2, w: 6.66, h: 0.3,
    fontSize: 12.5, bold: true, color: GOLD, valign: "middle" });
  bullets(s, [
    "손끝–건반 오차: 평균 ( ) cm, 최대 ( ) cm, 1 cm 이상 ( ) %",
    "수렴: 평균 반복 ( ) 회, 40회 안에 수렴 실패 ( ) %",
    "관절 제한에 걸린 프레임 비율 · 인접 프레임 간 각도 변화 최대값",
  ], { x: M + 0.34, y: by3 + 0.58, w: 6.62, h: 1.2, fontSize: 11.5, gap: 8 });

  s.addImage({ path: CROP + "/ik_ue5.png", x: M + 7.62, y: by3, w: W - 7.62, h: 1.94,
    sizing: { type: "cover", w: W - 7.62, h: 1.94 }, objectName: "ik_ue5" });
  txt(s, "A_IK_DebClai — UE5 AnimSequence (7,447프레임)", { x: M + 7.62, y: by3 + 1.98,
    w: W - 7.62, h: 0.26, fontSize: 9.5, color: LINE, align: "center" });

  s.addNotes("왼쪽이 된 것, 오른쪽이 아직 남은 것입니다.\n소지 오차는 손 비율을 MetaHuman 실측값으로 바꾸면서 늘었습니다. 새끼손가락이 짧아져서 닿지 않는 경우가 생긴 것으로 보고 있습니다.\n관절 각도 급점프는 Flesh 쪽에 부담을 줍니다. 프레임 0의 기본 굽힘도 확인이 필요합니다.\n아래 수치는 검증기를 확장하면 바로 나오는 값들입니다. 발표 전까지 채우는 게 목표입니다.");
}

// ═══════════════════ 03 GPU 스키닝 ═══════════════════
pres.addSection({ title: SEC.gpu });
divider("03", "GPU 스키닝",
  "뼈를 따라 정점을 옮기는 것만으로는 피부가 늘어나고 접히는 모습이 나오지 않는다.\n표면이 얼마나 늘어났는지를 직접 계산해서 주름과 핏줄 같은 미세한 디테일을 만든다.",
  "이수민", SEC.gpu);

{
  const s = newContent("03 GPU 스키닝", "왜 엔진 기본 스키닝으로는 안 되는가", SEC.gpu);

  card(s, { x: M, y: BODY_Y, w: 5.9, h: 1.86, line: H.RED });
  chip(s, M + 0.3, BODY_Y + 0.24, "엔진 기본", H.RED, 1.1);
  txt(s, "정점을 옮기기만 한다", { x: M + 0.3, y: BODY_Y + 0.62, w: 5.3, h: 0.36,
    fontSize: 17, bold: true, color: WHITE, valign: "middle" });
  txt(s, "뼈 변환을 가중 평균해 정점 위치를 구한다. 표면이 얼마나 늘어났는지는 계산하지 않으므로, 주름이 생길 자리를 알 수 없다.",
    { x: M + 0.3, y: BODY_Y + 1.06, w: 5.3, h: 0.66, fontSize: 12, color: MUTED,
      valign: "top", lineSpacingMultiple: 1.3 });

  card(s, { x: M + 6.2, y: BODY_Y, w: W - 6.2, h: 1.86, line: H.GREEN });
  chip(s, M + 6.5, BODY_Y + 0.24, "커스텀", H.GREEN, 1.1);
  txt(s, "신장률을 직접 계산한다", { x: M + 6.5, y: BODY_Y + 0.62, w: W - 6.8, h: 0.36,
    fontSize: 17, bold: true, color: WHITE, valign: "middle" });
  txt(s, "UMeshDeformer 를 상속해 정점 처리 단계에 끼어든다. 변의 길이 변화로 텐션을 구하고, 그 값으로 주름을 만든다.",
    { x: M + 6.5, y: BODY_Y + 1.06, w: W - 6.8, h: 0.66, fontSize: 12, color: MUTED,
      valign: "top", lineSpacingMultiple: 1.3 });

  s.addImage({ path: SKIN + "/skinning_pipeline/fig_skinning_08.png",
    x: M + 1.75, y: BODY_Y + 2.12, w: 8.6, h: 2.5,
    sizing: { type: "contain", w: 8.6, h: 2.5 }, objectName: "fig_wrinkle_cmp" });
  txt(s, "왼쪽: 손을 편 상태  ·  오른쪽: 손가락을 굽힌 상태 — 마디마다 가로 주름이 생긴다",
    { x: M, y: BODY_Y + 4.7, w: W, h: 0.28, fontSize: 10.5, color: LINE, align: "center" });

  s.addNotes("언리얼 기본 GPU 스키닝은 뼈 변환을 가중 평균해서 정점을 옮기기만 합니다. 표면이 얼마나 늘어났는지는 계산하지 않습니다.\n주름은 피부가 접히면서 생기는 것이라, 늘어남과 줄어듦을 알아야 만들 수 있습니다.\n그래서 UMeshDeformer를 상속해서 정점 처리 단계에 직접 끼어들었습니다.\n아래 사진이 결과입니다. 손가락을 굽히면 마디마다 가로 주름이 생깁니다.");
}

{
  const s = newContent("03 GPU 스키닝", "6‑Pass 컴퓨트 셰이더 파이프라인", SEC.gpu);
  lead(s, "UMeshDeformer 를 상속해 정점 처리 단계에서 실행된다. 패스 하나가 컴퓨트 셰이더 하나다.");
  const passes = [
    { n: "1", t: "Deform", d: "DQS/LBS 혼합으로\n정점을 변형", c: H.BLUE },
    { n: "2", t: "Tension\nAccumulate", d: "변의 신장률을 atomic int\n고정소수점으로 누적", c: H.BLUE },
    { n: "3", t: "Tension\nResolve", d: "누적값을 정점 수로 나눠\n텐션을 확정", c: H.BLUE },
    { n: "4", t: "Detail\nDisplace", d: "텐션으로 주름·핏줄\n변위를 적용", c: H.GOLD },
    { n: "5", t: "Normal\nAccumulate", d: "변위 후 면 노멀을\n정점에 누적", c: H.GREEN },
    { n: "6", t: "Normal\nResolve", d: "정규화해 최종 노멀을\n기록", c: H.GREEN },
  ];
  const pw = (W - 0.26 * 5) / 6, py = BODY_Y + 0.48, ph = 2.6;
  passes.forEach((p, i) => {
    const x = M + i * (pw + 0.26);
    card(s, { x, y: py, w: pw, h: ph, line: p.c });
    badge(s, x + pw / 2 - 0.19, py + 0.28, p.n, 0.38, p.c, H.BG);
    txt(s, p.t, { x: x + 0.1, y: py + 0.82, w: pw - 0.2, h: 0.66, fontSize: 12.5, bold: true,
      color: WHITE, align: "center", valign: "top", lineSpacingMultiple: 1.15 });
    txt(s, p.d, { x: x + 0.1, y: py + 1.56, w: pw - 0.2, h: 0.9, fontSize: 10,
      color: MUTED, align: "center", valign: "top", lineSpacingMultiple: 1.25 });
    if (i < 5) s.addShape(pres.ShapeType.rightArrow, { x: x + pw + 0.05, y: py + ph / 2 - 0.07,
      w: 0.16, h: 0.14, fill: { color: H.LINE }, line: { type: "none" }, objectName: oname("pf") });
  });

  card(s, { x: M, y: py + ph + 0.36, w: W, h: 1.42, fill: CARD, line: null });
  txt(s, "왜 누적과 확정을 나누는가", { x: M + 0.34, y: py + ph + 0.54, w: 4.0, h: 0.3,
    fontSize: 13, bold: true, color: GOLD, valign: "middle" });
  txt(s, "한 정점은 여러 삼각형에 속한다. 각 삼각형이 계산한 값을 한 정점에 모으려면 먼저 전부 더해 두고(Accumulate), 모든 삼각형이 끝난 뒤에 나눠야(Resolve) 한다. GPU는 순서를 보장하지 않으므로 atomic 연산으로 더하고 패스를 분리한다. 텐션과 노멀이 같은 이유로 각각 두 패스씩 쓴다.",
    { x: M + 0.34, y: py + ph + 0.88, w: W - 0.68, h: 0.76, fontSize: 11.5, color: MUTED,
      valign: "top", lineSpacingMultiple: 1.35 });

  s.addNotes("컴퓨트 셰이더 여섯 개가 순서대로 돕니다.\n1번이 정점을 옮기고, 2·3번이 텐션을 구하고, 4번이 그 텐션으로 주름을 만들고, 5·6번이 노멀을 다시 계산합니다.\n누적과 확정을 나눈 이유는 아래에 적어 뒀습니다. 한 정점이 여러 삼각형에 속해 있어서, 전부 더한 뒤에 나눠야 하기 때문입니다. GPU는 실행 순서를 보장하지 않아서 atomic으로 더합니다.");
}

{
  const s = newContent("03 GPU 스키닝", "텐션을 네 채널로 나눠 쓴다", SEC.gpu);
  lead(s, "정점 컬러 네 채널에 서로 다른 변형 성분을 담아, 주름의 방향과 세기를 따로 제어한다.");

  const chans = [
    { k: "R", t: "신장", d: "표면이 늘어난 정도", c: H.RED },
    { k: "G", t: "뼈 방향 압축", d: "뼈를 따라 줄어든 정도", c: H.GREEN },
    { k: "B", t: "가로 압축", d: "뼈와 직각으로 줄어든 정도", c: H.BLUE },
    { k: "A", t: "릴랙스 슬랙", d: "굽혔다 편 뒤 남는 이력", c: H.GOLD },
  ];
  const cw3 = (W - 0.3 * 3) / 4;
  chans.forEach((ch, i) => {
    const x = M + i * (cw3 + 0.3), y = BODY_Y + 0.4;
    card(s, { x, y, w: cw3, h: 1.6, line: ch.c });
    txt(s, ch.k, { x: x + 0.26, y: y + 0.2, w: 0.6, h: 0.5, fontSize: 28, bold: true,
      color: ch.c, valign: "middle" });
    txt(s, ch.t, { x: x + 0.26, y: y + 0.76, w: cw3 - 0.52, h: 0.32, fontSize: 14, bold: true,
      color: WHITE, valign: "middle" });
    txt(s, ch.d, { x: x + 0.26, y: y + 1.1, w: cw3 - 0.52, h: 0.4, fontSize: 11,
      color: MUTED, valign: "top" });
  });

  const y2 = BODY_Y + 2.32;
  card(s, { x: M, y: y2, w: 5.9, h: 2.3, line: H.GOLD });
  txt(s, "부피 보존을 추정값에서 실제 계산으로", { x: M + 0.32, y: y2 + 0.24, w: 5.26, h: 0.32,
    fontSize: 14, bold: true, color: GOLD, valign: "middle" });
  txt(s, [
    { text: "1학기  ", options: { fontSize: 12, color: H.MUTED } },
    { text: "1/λ²", options: { fontSize: 14, bold: true, color: H.MUTED, fontFace: "Consolas" } },
    { text: "  — 한 방향 신장률만 보고 어림잡은 값", options: { fontSize: 12, color: H.MUTED, breakLine: true } },
    { text: "2학기  ", options: { fontSize: 12, color: "FFFFFF" } },
    { text: "1/J", options: { fontSize: 14, bold: true, color: H.GOLD, fontFace: "Consolas" } },
    { text: "  — 변형 텐서 ", options: { fontSize: 12, color: "FFFFFF" } },
    { text: "C = FᵀF", options: { fontSize: 13, bold: true, color: H.GOLD, fontFace: "Consolas" } },
    { text: " 에서 구한 실제 부피비", options: { fontSize: 12, color: "FFFFFF" } },
  ], { x: M + 0.32, y: y2 + 0.68, w: 5.26, h: 0.92, isTextBox: true, margin: 0, valign: "top",
    lineSpacingMultiple: 1.5 });
  txt(s, "세 방향의 변형을 모두 반영하므로, 비틀리는 자세에서 부피가 어긋나지 않는다.",
    { x: M + 0.32, y: y2 + 1.66, w: 5.26, h: 0.46, fontSize: 11.5, color: MUTED,
      valign: "top", lineSpacingMultiple: 1.3 });

  card(s, { x: M + 6.2, y: y2, w: W - 6.2, h: 2.3, line: LINE });
  txt(s, "이력 주름 — 폈다 놓아도 바로 사라지지 않는다", { x: M + 6.52, y: y2 + 0.24,
    w: W - 6.84, h: 0.32, fontSize: 14, bold: true, color: WHITE, valign: "middle" });
  bullets(s, [
    "RelaxState 를 프레임 간 유지해, 굽혔다 편 직후에도 주름이 남는다",
    "감쇠 시간 약 0.9초 — 실제 피부의 거동에 맞춘 값",
    { text: "정지 화면으로는 확인할 수 없다 — 시퀀서 렌더로 검증해야 한다", color: H.GOLD },
  ], { x: M + 6.52, y: y2 + 0.72, w: W - 6.84, h: 1.4, fontSize: 12, gap: 10 });

  s.addNotes("텐션을 하나의 값으로 두지 않고 네 채널로 나눴습니다. 늘어남과 줄어듦, 그리고 뼈 방향인지 가로 방향인지를 구분해야 주름 방향이 제대로 나옵니다.\n부피 보존은 1학기에 한 방향 신장률로 어림잡았는데, 2학기에 변형 텐서에서 실제 부피비를 구하도록 바꿨습니다.\n오른쪽 이력 주름은 발표 때 주의할 점입니다. 0.9초면 사라져서 정지 화면으로는 안 보입니다.");
}

{
  const s = newContent("03 GPU 스키닝", "손등과 손바닥은 반대로 동작한다", SEC.gpu);

  card(s, { x: M, y: BODY_Y, w: W, h: 0.88, fill: CARD, line: null });
  txt(s, "손가락을 굽히면 손등 피부는 당겨지고 손바닥 피부는 접힌다. 같은 관절인데 주름이 생기는 조건이 정반대라, 셰이더에서 이중 게이트로 분기한다.",
    { x: M + 0.34, y: BODY_Y + 0.16, w: W - 0.68, h: 0.56, fontSize: 13.5, color: WHITE,
      valign: "middle", lineSpacingMultiple: 1.35 });

  const two = [
    { t: "손등", d: "굽힐수록 늘어난다", e: "신장(R) 채널이 올라가는 쪽에서 주름을 만든다.\n마디 위로 가로줄이 선다.", c: H.BLUE },
    { t: "손바닥", d: "굽힐수록 접힌다", e: "압축(G·B) 채널이 올라가는 쪽에서 주름을 만든다.\n손바닥 접힘선은 Phase 4 에서 해결했다.", c: H.GOLD },
  ];
  const cw4 = (W - 0.36) / 2;
  two.forEach((t, i) => {
    const x = M + i * (cw4 + 0.36), y = BODY_Y + 1.12;
    card(s, { x, y, w: cw4, h: 1.74, line: t.c });
    txt(s, t.t, { x: x + 0.32, y: y + 0.22, w: cw4 - 0.64, h: 0.36, fontSize: 18, bold: true,
      color: t.c, valign: "middle" });
    txt(s, t.d, { x: x + 0.32, y: y + 0.62, w: cw4 - 0.64, h: 0.3, fontSize: 13.5, bold: true,
      color: WHITE, valign: "middle" });
    txt(s, t.e, { x: x + 0.32, y: y + 0.98, w: cw4 - 0.64, h: 0.64, fontSize: 11.5,
      color: MUTED, valign: "top", lineSpacingMultiple: 1.3 });
  });

  const y3 = BODY_Y + 3.14;
  txt(s, "현재 상태", { x: M, y: y3, w: 4.0, h: 0.3, fontSize: 12, bold: true, color: GOLD,
    charSpacing: 1.5, valign: "middle" });
  const sw4 = (W - 0.3 * 3) / 4;
  [
    { v: "Phase 7", l: "진행 단계\n손바닥선 · 부피 보존 완료", c: H.GREEN, vs: 24 },
    { v: "74,186", l: "고밀도 메시 정점 수\nSKM_MH_Hand_R_Dense", c: "FFFFFF", vs: 26 },
    { v: "3.7~4.6", unit: "ms", l: "전체 GPU 시간 — 아직 한가하다\n패스별 분해는 미측정", c: "FFFFFF", vs: 24 },
    { v: "0.9", unit: "초", l: "이력 주름 감쇠 시간", c: "FFFFFF" },
  ].forEach((d, i) => {
    stat(s, { x: M + i * (sw4 + 0.3), y: y3 + 0.38, w: sw4, h: 1.5, value: d.v, unit: d.unit,
      color: d.c, label: d.l, vs: d.vs, ls: 11, line: d.c === H.GREEN ? H.GREEN : H.LINE });
  });

  s.addNotes("이게 구현에서 가장 까다로웠던 부분입니다.\n같은 관절인데 손등은 늘어나고 손바닥은 접힙니다. 주름이 생기는 조건이 정반대라, 한쪽 기준으로 짜면 반대쪽이 틀립니다. 셰이더에서 이중으로 분기합니다.\n현재 Phase 7까지 왔고, 1차 때 한계로 적었던 손바닥 접힘선은 해결했습니다.\nGPU는 4ms 정도로 아직 여유가 있습니다. 병목은 다른 데 있는데 마지막에 말씀드립니다.");
}

// ═══════════════════ 04 Chaos Flesh ═══════════════════
pres.addSection({ title: SEC.flesh });
divider("04", "Chaos Flesh",
  "주름 같은 미세한 디테일이 아니라, 살이 눌려 옆으로 밀려나는 거시적인 변형을 다룬다.\n손 내부를 사면체로 채우고 뼈에 묶어 물리로 계산한다.",
  "곽경민", SEC.flesh);

{
  const s = newContent("04 Chaos Flesh", "IsoStuffing은 손가락을 만들지 못했다", SEC.flesh);
  lead(s, "손 메시 내부를 사면체로 채우는 단계에서, 엔진 기본 생성기가 MetaHuman 손의 가는 손가락을 처리하지 못했다.");

  const iw = 4.05, iy = BODY_Y + 0.44;
  card(s, { x: M, y: iy, w: iw, h: 3.22, line: H.RED });
  chip(s, M + 0.26, iy + 0.22, "IsoStuffing", H.RED, 1.5);
  s.addImage({ path: CROP + "/tet_iso.png", x: M + 0.26, y: iy + 0.62, w: iw - 0.52, h: 2.1,
    sizing: { type: "contain", w: iw - 0.52, h: 2.1 }, objectName: "tet_iso" });
  txt(s, "손가락이 통째로 날아가고\n손바닥만 덩어리로 남는다", { x: M + 0.26, y: iy + 2.74,
    w: iw - 0.52, h: 0.42, fontSize: 11, color: H.RED, align: "center", valign: "top",
    lineSpacingMultiple: 1.2 });

  card(s, { x: M + iw + 0.3, y: iy, w: iw, h: 3.22, line: H.GREEN });
  chip(s, M + iw + 0.56, iy + 0.22, "TetWild", H.GREEN, 1.5);
  s.addImage({ path: CROP + "/tet_wild.png", x: M + iw + 0.56, y: iy + 0.62, w: iw - 0.52, h: 2.1,
    sizing: { type: "contain", w: iw - 0.52, h: 2.1 }, objectName: "tet_wild" });
  txt(s, "손가락 다섯 개가 모두 살아 있다\n사면체 정점 5,688", { x: M + iw + 0.56, y: iy + 2.74,
    w: iw - 0.52, h: 0.42, fontSize: 11, color: H.GREEN, align: "center", valign: "top",
    lineSpacingMultiple: 1.2 });

  const rx = M + iw * 2 + 0.64;
  bullets(s, [
    { text: "왜 실패했나", bold: true, color: "FFFFFF", bullet: false, fontSize: 13 },
    "IsoStuffing은 격자를 채워 넣는 방식이라, 격자 간격보다 가는 부분은 아예 비어 버린다",
    { text: "TetWild로 전환", bold: true, color: "FFFFFF", bullet: false, fontSize: 13 },
    "표면을 먼저 정리한 뒤 내부를 채우므로 가는 손가락도 살아남는다",
    { text: "Dataflow도 통합", bold: true, color: "FFFFFF", bullet: false, fontSize: 13 },
    "1학기에 그래프 2개로 나뉘어 있던 것을 단일 그래프로 합쳤다",
  ], { x: rx, y: iy + 0.14, w: W - (iw * 2 + 0.64), h: 3.0, fontSize: 11.5, gap: 7 });

  s.addImage({ path: CROP + "/flesh_dataflow.png", x: M, y: iy + 3.46, w: W, h: 0.96,
    sizing: { type: "contain", w: W, h: 0.96 }, objectName: "flesh_dataflow" });

  s.addNotes("사면체를 만드는 단계에서 막혔던 이야기입니다.\n엔진 기본 생성기인 IsoStuffing은 격자를 채우는 방식이라, 격자 간격보다 가는 부분은 비어 버립니다. MetaHuman 손가락이 딱 그 경우였습니다. 왼쪽 사진처럼 손가락이 날아가고 손바닥 덩어리만 남았습니다.\nTetWild로 바꾸니 손가락 다섯 개가 모두 살아났습니다. 사면체 정점은 5,688개입니다.\n아래가 통합한 Dataflow 그래프입니다.");
}

{
  const s = newContent("04 Chaos Flesh", "Flesh 결과를 GPU 스키닝에 섞는다", SEC.flesh);

  card(s, { x: M, y: BODY_Y, w: W, h: 0.94, fill: CARD, line: H.GREEN });
  txt(s, [
    { text: "2차 성과 — ", options: { bold: true, color: H.GREEN, fontSize: 14 } },
    { text: "Flesh가 계산한 표면 위치를 GPU 스키닝 직후에 섞는 어댑터를 구현하고 검증까지 마쳤다.",
      options: { color: "FFFFFF", fontSize: 14, breakLine: true } },
    { text: "컴퓨트 셰이더에서  lerp(스키닝 결과, Flesh 결과, Blend)  로 합성한다.",
      options: { color: H.MUTED, fontSize: 11.5 } },
  ], { x: M + 0.32, y: BODY_Y + 0.14, w: W - 0.64, h: 0.68, valign: "middle", lineSpacingMultiple: 1.4 });

  const vy2 = BODY_Y + 1.2;
  txt(s, "연결 검증 결과", { x: M, y: vy2, w: 4.0, h: 0.3, fontSize: 12, bold: true, color: GOLD,
    charSpacing: 1.5, valign: "middle" });
  const vrows = [
    ["정점 수 일치", "Flesh 반환 74,186 = 렌더 메시 74,186", H.GREEN],
    ["정점 순서 · 좌표계", "휴지 자세 편차 평균 0.27 cm · 최대 0.35 cm → 이음매 매핑 불필요", H.GREEN],
    ["렌더 패스 실행", "301 프레임 중 301회 실행, 실패 0", H.GREEN],
    ["좌표 변환", "불필요 — 변환 전후 편차가 같다", H.GREEN],
    ["성능", "바인딩 1회 생성 + 정점 계산 병렬화로 46 ms → 7 ms", H.GOLD],
  ];
  const tbw = 8.2, rh2 = 0.64;
  vrows.forEach((r, i) => {
    const y = vy2 + 0.4 + i * rh2;
    if (i % 2 === 0) card(s, { x: M, y, w: tbw, h: rh2 - 0.08, fill: CARD, line: null, r: 0.05 });
    s.addShape(pres.ShapeType.ellipse, { x: M + 0.22, y: y + rh2 / 2 - 0.11, w: 0.14, h: 0.14,
      fill: { color: r[2] }, line: { type: "none" }, objectName: oname("dot") });
    txt(s, r[0], { x: M + 0.52, y: y, w: 2.3, h: rh2 - 0.08, fontSize: 12, bold: true,
      color: WHITE, valign: "middle" });
    txt(s, r[1], { x: M + 2.88, y: y, w: tbw - 3.0, h: rh2 - 0.08, fontSize: 11.5, color: MUTED,
      valign: "middle" });
  });

  const hx = M + tbw + 0.34;
  const hw = W - tbw - 0.34;
  s.addImage({ path: CROP + "/flesh_hand.png", x: hx, y: vy2 + 0.4, w: hw, h: 2.9,
    sizing: { type: "cover", w: hw, h: 2.9 }, objectName: "flesh_hand" });
  txt(s, "Flesh + GPU 스키닝 통합 결과 (L_FleshTest)", { x: hx, y: vy2 + 3.38, w: hw, h: 0.26,
    fontSize: 10, color: LINE, align: "center" });
  txt(s, "정지 자세에서 Flesh 쪽 표면이 평균 0.3 cm 더 두껍다", { x: hx, y: vy2 + 3.64, w: hw, h: 0.28,
    fontSize: 10, color: MUTED, align: "center" });

  s.addNotes("1차 발표에서 '어댑터 미구현'이라고 말씀드렸던 부분입니다. 2차에서 구현하고 검증까지 마쳤습니다.\n정점 수가 정확히 일치하고, 좌표계도 같아서 별도 매핑이 필요 없었습니다. 편차가 평균 0.27cm인데 이건 Flesh 표면이 원래 조금 더 두꺼워서 나는 차이입니다.\n처음 구현했을 때 46ms가 걸렸는데, 바인딩을 매 프레임 만들던 것을 한 번만 만들도록 고치고 정점 계산을 병렬화해서 7ms로 줄였습니다.\n오른쪽이 실제로 합쳐진 결과입니다.");
}

{
  const s = newContent("04 Chaos Flesh", "현재 확보한 것과 남은 문제", SEC.flesh);

  const sw5 = (W - 0.3 * 3) / 4;
  [
    { v: "5,688", l: "사면체 정점 수 (TetWild)", c: "FFFFFF", vs: 28 },
    { v: "0", l: "바인딩 에러 (뼈 22개 전부 성공)", c: H.GREEN },
    { v: "74,186", l: "렌더 메시 바인딩 정점\n고아 · 재부모 정점 0", c: H.GREEN, vs: 26 },
    { v: "0", l: "시뮬레이션 발산 · 폭발 프레임", c: H.GREEN },
  ].forEach((d, i) => {
    stat(s, { x: M + i * (sw5 + 0.3), y: BODY_Y, w: sw5, h: 1.5, value: d.v, label: d.l,
      color: d.c, vs: d.vs, ls: 11, line: d.c === H.GREEN ? H.GREEN : H.LINE });
  });

  const ly = BODY_Y + 1.8;
  txt(s, "알려진 한계", { x: M, y: ly, w: 4.0, h: 0.3, fontSize: 12, bold: true, color: H.RED,
    charSpacing: 1.5, valign: "middle" });
  const lims = [
    { t: "손끝 어긋남", d: "타이밍 · 중력 · 바인딩 영역을 바꿔도 동일하고 정지 상태에서도 남는다.\n지연이 아니라 형태 차이로 보고 있다 — 위치를 추출해 수치로 확인 예정." },
    { t: "안쪽 살 지글거림", d: "주먹을 쥘 때 가장 안쪽 살이 떨린다.\n자기충돌(self‑collision)을 설정하지 않은 것이 원인으로 보인다." },
    { t: "부위별 바인딩 미적용", d: "VertexSelection 이 비어 있으면 모든 정점이 뼈에 묶여\n안쪽의 탄성이 반영되지 않는다. 설정 후 변형 차이를 확인해야 한다." },
    { t: "Blend 값별 비교 미실시", d: "0 / 0.5 / 1 로 나눠 살 눌림과 부피 이득을 정량 비교해야\nFlesh를 쓰는 근거를 수치로 댈 수 있다." },
  ];
  const lw3 = (W - 0.34) / 2, lh = 1.32;
  lims.forEach((l, i) => {
    const col = i % 2, row = Math.floor(i / 2);
    const x = M + col * (lw3 + 0.34), y = ly + 0.4 + row * (lh + 0.26);
    card(s, { x, y, w: lw3, h: lh, line: LINE });
    txt(s, l.t, { x: x + 0.3, y: y + 0.18, w: lw3 - 0.6, h: 0.3, fontSize: 13.5, bold: true,
      color: WHITE, valign: "middle" });
    txt(s, l.d, { x: x + 0.3, y: y + 0.54, w: lw3 - 0.6, h: 0.66, fontSize: 11,
      color: MUTED, valign: "top", lineSpacingMultiple: 1.3 });
  });

  s.addNotes("위는 확보한 수치, 아래는 남은 문제입니다.\n손끝 어긋남이 가장 오래 붙잡고 있는 문제인데, 처음에는 시뮬레이션이 늦게 따라오는 지연이라고 봤습니다. 그런데 정지 상태에서도 남아서, 지연이 아니라 형태 자체가 다른 것으로 보고 있습니다.\nBlend 값별 비교는 Flesh를 쓸 이유를 수치로 대는 작업이라 꼭 해야 합니다.");
}

// ═══════════════════ 05 통합 ═══════════════════
pres.addSection({ title: SEC.wrap });
divider("05", "통합과 마무리",
  "모듈을 각자 돌릴 때는 보이지 않다가, 붙여서 데이터를 따라가 보니 드러난 것들.\n2차 발표에서 가장 말씀드리고 싶은 부분이다.",
  "정근녕", SEC.wrap);

{
  const s = newContent("05 통합", "같은 수치를 각 파트가 따로 들고 있었다", SEC.wrap);
  lead(s, "건반 치수는 네 모듈이 모두 참조한다. 그런데 각자 자기 코드에 값을 적어 두고 있었고, 서로 달랐다.");

  const probs = [
    { t: "흑건 앞뒤 위치", b: "+3.0 cm", a: "55.0 mm",
      d: "건반 형상에서 도출될 수 없는 값이었다.\n백건 길이 150 − 흑건 길이 95 로 재정의." },
    { t: "흑건 상면 높이", b: "정의 없음", a: "12.5 mm",
      d: "IK가 반드시 참조해야 하는 값인데\n명세에 항목 자체가 없었다." },
    { t: "백건 폭", b: "23.4 mm", a: "164.0 / 7",
      d: "반올림한 값을 쓰면 88건반 끝에서\n1.5 mm 오차가 누적된다." },
  ];
  const pw2 = (W - 0.32 * 2) / 3;
  probs.forEach((p, i) => {
    const x = M + i * (pw2 + 0.32), y = BODY_Y + 0.44;
    card(s, { x, y, w: pw2, h: 2.46, line: LINE });
    txt(s, p.t, { x: x + 0.3, y: y + 0.22, w: pw2 - 0.6, h: 0.32, fontSize: 14.5, bold: true,
      color: WHITE, valign: "middle" });
    txt(s, p.b, { x: x + 0.3, y: y + 0.68, w: pw2 - 0.6, h: 0.36, fontSize: 15,
      color: H.RED, fontFace: "Consolas", valign: "middle" });
    s.addShape(pres.ShapeType.downArrow, { x: x + 0.42, y: y + 1.08, w: 0.14, h: 0.26,
      fill: { color: H.GOLD }, line: { type: "none" }, objectName: oname("dn") });
    txt(s, p.a, { x: x + 0.3, y: y + 1.38, w: pw2 - 0.6, h: 0.36, fontSize: 15, bold: true,
      color: H.GOLD, fontFace: "Consolas", valign: "middle" });
    txt(s, p.d, { x: x + 0.3, y: y + 1.8, w: pw2 - 0.6, h: 0.56, fontSize: 10.5,
      color: MUTED, valign: "top", lineSpacingMultiple: 1.3 });
  });

  card(s, { x: M, y: BODY_Y + 3.14, w: W, h: 1.5, fill: CARD, line: H.GOLD });
  txt(s, [
    { text: "shared_constants.py", options: { bold: true, color: H.GOLD, fontSize: 15, fontFace: "Consolas" } },
    { text: "  —  단일 출처로 통합", options: { bold: true, color: "FFFFFF", fontSize: 15, breakLine: true } },
    { text: "건반 치수 · 손가락 간 최대 폭 · 손목 ROM · 본 이름 · 프레임 레이트 · 해제 시점 규약을 한 파일에 모았다. 각 파트는 이 파일에서 읽어 쓴다. 값이 바뀌면 한 군데만 고치면 되고, 서로 다른 값을 들고 있을 수가 없다.",
      options: { color: H.MUTED, fontSize: 12 } },
  ], { x: M + 0.34, y: BODY_Y + 3.34, w: W - 0.68, h: 1.14, isTextBox: true, margin: 0,
    valign: "top", lineSpacingMultiple: 1.45 });

  s.addNotes("건반 치수는 네 모듈이 다 쓰는 값인데, 각자 자기 코드에 적어 두고 있었습니다.\n가운데 것이 특히 문제였습니다. 흑건 윗면 높이는 IK가 반드시 알아야 하는 값인데 명세에 항목 자체가 없었습니다. 각자 알아서 가정하고 있었던 겁니다.\n오른쪽은 작아 보이지만, 23.4로 반올림하면 88건반 끝에서 1.5mm가 어긋납니다.\n지금은 shared_constants.py 한 파일에서 읽어 씁니다.");
}

{
  const s = newContent("05 통합 · 핵심", "계산해서 넘겼는데, 받는 쪽에서 쓰지 않고 있었다", SEC.wrap);
  lead(s, "모듈을 각자 돌릴 때는 드러나지 않고, 붙여서 데이터를 끝까지 따라가 봐야 보이는 종류의 문제다.");

  const dgw = 6.85, dgh = 3.07, dgy = BODY_Y + 0.3;
  s.addImage({ path: CROP + "/diag_wrist_roll.png", x: M, y: dgy, w: dgw, h: dgh,
    objectName: "diag_wrist" });

  const rx2 = M + dgw + 0.3;
  card(s, { x: rx2, y: dgy, w: W - dgw - 0.3, h: dgh, fill: CARD, line: H.GOLD });
  txt(s, "무슨 값인가", { x: rx2 + 0.3, y: dgy + 0.22, w: W - dgw - 0.9, h: 0.3,
    fontSize: 12, bold: true, color: GOLD, charSpacing: 1.2, valign: "middle" });
  bullets(s, [
    { text: "엄지가 흑건을 누르면 +12°, 소지가 흑건을 누르면 −12° 가 손 전체에 붙는다 (왼손은 부호 반대)", fontSize: 11.5 },
    { text: "엄지가 흑건을 누르는 1,758음 중 1,507음에 롤 값이 들어 있다", color: "FFFFFF", bold: true, fontSize: 11.5 },
    { text: "IK 가 변환한 드뷔시 '달빛' 한 곡만 보면 154음 중 143음", fontSize: 11.5 },
    { text: "IK 인계 규격서에 \"손목 회전은 IK 쪽 향후 과제\" 로 적혀 있다 — 알려진 공백이고, 아직 닫히지 않았다", color: H.GOLD, fontSize: 11.5 },
  ], { x: rx2 + 0.32, y: dgy + 0.64, w: W - dgw - 0.94, h: 2.5, gap: 9, lsm: 1.3 });

  const cy2 = dgy + dgh + 0.24;
  card(s, { x: M, y: cy2, w: W, h: 1.14, fill: CARD, line: H.GOLD });
  txt(s, [
    { text: "엄지로 흑건을 누르려면 손목을 비틀어야 한다. ", options: { fontSize: 14, color: "FFFFFF" } },
    { text: "엔진은 그 각도를 넘겼지만, IK 는 손목 회전을 다루지 않는다.",
      options: { fontSize: 14, bold: true, color: H.GOLD, breakLine: true } },
    { text: "IK 영상에서 보이는 \"손목이 돌아간\" 자세의 유력한 원인이며, 운지법 쪽 결함이 아니다.",
      options: { fontSize: 12, color: H.MUTED } },
  ], { x: M + 0.34, y: cy2 + 0.16, w: W - 0.68, h: 0.82, isTextBox: true, margin: 0,
    valign: "middle", lineSpacingMultiple: 1.45 });

  txt(s, [
    { text: "여기서 얻은 것 — ", options: { fontSize: 12.5, bold: true, color: GOLD } },
    { text: "인터페이스는 필드를 정의하고 파일을 주고받는 것으로 끝나지 않는다. 받는 쪽이 그 값을 실제로 다루는지까지 확인해야 한다.",
      options: { fontSize: 12.5, color: "FFFFFF" } },
  ], { x: M, y: cy2 + 1.26, w: W, h: 0.32, isTextBox: true, margin: 0, valign: "middle" });

  s.addNotes("2차에서 가장 말씀드리고 싶은 내용입니다.\n왼쪽이 운지법 엔진이 내보낸 손목 롤 값 분포입니다. 21곡 21,912음 중 5,415음에 ±12도가 들어 있습니다. 엄지나 소지가 검은 건반을 누르면 손목을 비틀어야 하기 때문입니다.\n오른쪽이 IK가 기록한 wrist.csv입니다. 전부 0입니다.\nIK는 손목을 위치만 보간하고 회전은 다루지 않습니다. 인계 규격서에도 '손목 회전은 IK 쪽 향후 과제'로 적혀 있습니다. 즉 모르고 있던 게 아니라, 알고 미뤄 둔 공백인데 아직 닫히지 않은 겁니다.\n아까 IK 영상에서 손목이 돌아가 보였던 것의 유력한 원인입니다. 운지법 쪽 결함은 아닙니다.\n인터페이스를 정의하고 파일을 주고받는 것만으로는 부족하고, 받는 쪽이 그 값을 실제로 다루는지까지 확인해야 한다는 걸 배웠습니다.");
}

{
  const s = newContent("05 통합", "병목은 어댑터가 아니었다", SEC.wrap);
  lead(s, "목표는 60 FPS(16.7 ms)인데 현재 약 20 FPS다. 어떤 구성을 끄고 켜며 측정해 원인을 좁혔다.");

  const ty3 = BODY_Y + 0.72, rh3 = 0.72;
  const cols = [["구성", 3.5], ["Frame", 2.0], ["Game (CPU)", 2.3], ["GPU", 1.9], ["FPS", 1.5]];
  let cx0 = M;
  const colXs = cols.map((c) => { const v = cx0; cx0 += c[1]; return v; });
  cols.forEach((c, i) => {
    txt(s, c[0], { x: colXs[i] + (i === 0 ? 0.24 : 0), y: ty3 - 0.36, w: c[1], h: 0.28,
      fontSize: 11, bold: true, color: GOLD, charSpacing: 1.2,
      align: i === 0 ? "left" : "center", valign: "middle" });
  });
  const prows = [
    ["어댑터 끔", "44.5 ms", "44.3 ms", "4.6 ms", "약 22", H.LINE],
    ["어댑터 켬 (최적화 전)", "91 ms", "—", "—", "약 11", H.RED],
    ["어댑터 켬 (최적화 후)", "약 51 ms", "약 51 ms", "약 3.7 ms", "약 20", H.GOLD],
  ];
  prows.forEach((r, i) => {
    const y = ty3 + i * (rh3 + 0.08);
    card(s, { x: M, y, w: W, h: rh3, fill: CARD, line: i === 2 ? H.GOLD : null, lw: 1.0 });
    txt(s, r[0], { x: colXs[0] + 0.24, y, w: cols[0][1] - 0.3, h: rh3, fontSize: 13,
      bold: i === 2, color: WHITE, valign: "middle" });
    for (let k = 1; k <= 4; k++) {
      txt(s, r[k], { x: colXs[k], y, w: cols[k][1], h: rh3, fontSize: 13,
        bold: k === 4, color: k === 4 ? r[5] : (k === 3 ? H.GREEN : MUTED),
        align: "center", valign: "middle" });
    }
  });

  const fy2 = ty3 + 3 * (rh3 + 0.08) + 0.24;
  card(s, { x: M, y: fy2, w: 6.1, h: 1.84, fill: CARD, line: H.GOLD });
  txt(s, "읽어 낸 것", { x: M + 0.32, y: fy2 + 0.2, w: 5.46, h: 0.3, fontSize: 12.5,
    bold: true, color: GOLD, valign: "middle" });
  bullets(s, [
    "어댑터를 아예 꺼도 44.5 ms — 어댑터는 병목이 아니다",
    "GPU는 3.7~4.6 ms로 한가하고, 게임 스레드가 붙잡고 있다",
    "60 FPS로 가려면 기본 비용 44 ms를 약 1/3로 줄여야 한다",
  ], { x: M + 0.34, y: fy2 + 0.58, w: 5.42, h: 1.1, fontSize: 11.5, gap: 8 });

  card(s, { x: M + 6.42, y: fy2, w: W - 6.42, h: 1.84, fill: CARD, line: LINE });
  txt(s, "아직 분리하지 못한 것", { x: M + 6.74, y: fy2 + 0.2, w: W - 7.06, h: 0.3, fontSize: 12.5,
    bold: true, color: WHITE, valign: "middle" });
  bullets(s, [
    "44 ms가 Flesh 시뮬레이션인지, 두 손(342본 × 2)의 애니메이션 평가인지, 에디터 PIE 오버헤드인지",
    "stat game 으로는 컴포넌트 틱 세부가 보이지 않는다 → Flesh 액터 / 디포머 / Standalone 순으로 끄며 측정",
  ], { x: M + 6.76, y: fy2 + 0.58, w: W - 7.1, h: 1.1, fontSize: 11.5, gap: 8 });

  s.addNotes("성능 이야기입니다. 목표는 60 FPS인데 현재 20 FPS입니다.\n표를 보시면 어댑터를 아예 꺼도 44.5ms가 나옵니다. 즉 어댑터가 병목이 아닙니다.\nGPU는 4ms 안쪽으로 한가하고, 게임 스레드가 붙잡고 있습니다.\n그 44ms가 Flesh 시뮬레이션인지, 두 손 684본의 애니메이션 평가인지, 아니면 에디터 PIE 오버헤드인지는 아직 분리하지 못했습니다. 하나씩 꺼 보며 좁힐 예정입니다.");
}

{
  const s = newContent("05 통합", "남은 과제", SEC.wrap);
  lead(s, "우선순위 순이다. 1번과 2번은 앞에서 말씀드린 두 가지 발견에 대한 후속이다.");

  const tasks = [
    ["1", "손목 각도(yaw · roll)를 IK 에 반영", "한승현 · 정근녕", H.GOLD],
    ["2", "통합 프레임 비용 — 게임 스레드 44 ms 원인 분리", "곽경민 · 이수민", H.GOLD],
    ["3", "GPU 스키닝 패스별 성능 측정", "이수민", H.LINE],
    ["4", "Flesh 부위별 바인딩 · Blend 값별 비교", "곽경민", H.LINE],
    ["5", "엔드‑투‑엔드 데모 (MIDI → 최종 렌더)", "전체", H.GREEN],
    ["6", "손 크기 프리셋 · 피아노 트랙 자동 선별", "정근녕", H.LINE],
  ];
  const trh = 0.72;
  tasks.forEach((t, i) => {
    const y = BODY_Y + 0.62 + i * (trh + 0.1);
    card(s, { x: M, y, w: W, h: trh, fill: CARD, line: i < 2 ? H.GOLD : null, lw: 0.9 });
    badge(s, M + 0.24, y + trh / 2 - 0.16, t[0], 0.32, t[3], H.BG);
    txt(s, t[1], { x: M + 0.74, y, w: 8.4, h: trh, fontSize: 13.5,
      bold: i < 2, color: WHITE, valign: "middle" });
    txt(s, t[2], { x: M + 9.2, y, w: W - 9.5, h: trh, fontSize: 11.5, color: MUTED,
      align: "right", valign: "middle" });
  });

  s.addNotes("우선순위 순입니다.\n1번과 2번이 급합니다. 손목 각도는 아까 말씀드린 유실 건이고, 2번은 방금 본 성능 문제입니다.\n5번 엔드투엔드 데모가 학기 최종 목표입니다. MIDI 파일 하나를 넣으면 최종 렌더까지 나오는 것을 보여 드리려고 합니다.");
}

{
  const s = pres.addSlide({ masterName: "COVER", sectionTitle: SEC.wrap });
  txt(s, "마무리", { x: M, y: 1.26, w: 6.4, h: 0.3, fontSize: 12, bold: true, color: GOLD,
    charSpacing: 2, valign: "middle" });
  txt(s, "모듈이 각자 도는 단계에서\n서로 붙는 단계로 넘어왔다", { x: M, y: 1.7, w: 7.6, h: 1.5,
    fontSize: 32, bold: true, color: WHITE, valign: "top", lineSpacingMultiple: 1.25 });

  const pts = [
    ["운지법", "제약을 거는 단위를 시간 기준으로 바꿔 21곡에서 위반 0건"],
    ["IK", "양손 10손가락이 실제 비율 건반을 치고, 달빛 전곡을 애니메이션으로 변환"],
    ["GPU 스키닝", "6‑Pass 정점 파이프라인으로 주름과 부피 보존을 구현"],
    ["Chaos Flesh", "TetWild 사면체 + 렌더 메시 바인딩, GPU 연결 어댑터까지 완료"],
    ["통합", "인터페이스 A · B · C 에 실제 데이터가 흐르고, 공유 상수로 수치를 일원화"],
  ];
  pts.forEach((p, i) => {
    const y = 3.44 + i * 0.56;
    s.addShape(pres.ShapeType.ellipse, { x: M + 0.04, y: y + 0.17, w: 0.1, h: 0.1,
      fill: { color: H.GOLD }, line: { type: "none" }, objectName: oname("cdot") });
    txt(s, p[0], { x: M + 0.34, y, w: 1.7, h: 0.44, fontSize: 12.5, bold: true, color: GOLD,
      valign: "middle" });
    txt(s, p[1], { x: M + 2.1, y, w: 7.6, h: 0.44, fontSize: 12, color: MUTED, valign: "middle" });
  });

  card(s, { x: 10.0, y: 3.44, w: 2.73, h: 2.3, fill: CARD, line: H.GOLD });
  txt(s, "남은 기간의 목표", { x: 10.26, y: 3.66, w: 2.21, h: 0.3, fontSize: 11.5, bold: true,
    color: GOLD, valign: "middle" });
  txt(s, "손목 각도 반영\n프레임 비용 개선\n엔드‑투‑엔드 데모", { x: 10.26, y: 4.06, w: 2.21, h: 1.4,
    fontSize: 14, bold: true, color: WHITE, valign: "top", lineSpacingMultiple: 1.6 });

  txt(s, "감사합니다", { x: M, y: 6.46, w: 6.4, h: 0.4, fontSize: 18, bold: true, color: WHITE,
    valign: "middle" });

  s.addNotes("정리하겠습니다.\n2차의 핵심은 각 모듈이 독립 동작에서 실제 구현 단계에 도달했고, 인터페이스 세 군데에 실제 데이터가 흐르기 시작했다는 점입니다.\n붙여 보니 손목 각도 유실과 성능 병목 같은 문제가 드러났는데, 이건 붙이지 않았으면 끝까지 몰랐을 종류입니다.\n남은 기간에는 그 문제들을 고치고 엔드투엔드 데모까지 가는 것이 목표입니다.\n감사합니다.");
}

// ───────────────────────── 저장 ─────────────────────────
const OUT = process.argv[2] || "2학기_2차_중간발표.pptx";
pres.writeFile({ fileName: OUT }).then(async () => {
  if (process.argv[3]) {
    const { applyTheme } = require(process.argv[3]);
    await applyTheme(OUT, THEME);
  }
  console.log("생성 완료:", OUT);
}).catch((e) => { console.error("실패:", e); process.exit(1); });
