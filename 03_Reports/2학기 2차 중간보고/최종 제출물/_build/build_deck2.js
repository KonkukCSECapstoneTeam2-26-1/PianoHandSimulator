// 2학기 2차 중간발표 PPT — 견본 덱(밝은 세이지)의 디자인 시스템에 맞춰 재작성
const path = require("path");
const pptxgen = require("pptxgenjs");

const REPO = "D:/Git/PianoHandSimulator";
const R2 = REPO + "/03_Reports/2학기 2차 중간보고";
const SKIN = REPO + "/02_Implementation/03_Skinning/Document/images";
const CROP = path.join(__dirname, "img");
const EMBED_VIDEO = process.env.EMBED_VIDEO !== "0";

// ── 견본에서 뽑은 팔레트 ────────────────────────────────
const H = {
  BG:      "F7F3EF",  // 배경 (따뜻한 오프화이트)
  BG2:     "F8F7F5",
  BEIGE:   "E4DFD8",  // 면
  BEIGE2:  "E0DBD2",
  LINE:    "CDC5B9",  // 선 · 약한 글씨
  SAGE:    "6A7E74",  // 세이지 (제목)
  SAGE_D:  "466456",  // 진한 세이지 (강조)
  SAGE_L:  "BACCC3",  // 연한 세이지
  INK:     "222222",
  INK2:    "444444",
  WHITE:   "FFFFFF",
  RUST:    "A8584F",  // 문제 표시 (견본에 없어 보색을 절제해 추가)
};

const THEME = {
  name: "PianoHand Sage",
  headFontFace: "Pretendard",
  bodyFontFace: "Pretendard",
  colors: {
    dk1: H.INK, lt1: H.BG, dk2: H.SAGE_D, lt2: H.BEIGE,
    accent1: H.SAGE, accent2: H.SAGE_D, accent3: H.SAGE_L,
    accent4: H.LINE, accent5: H.INK2, accent6: H.BEIGE2,
    hlink: H.SAGE_D, folHlink: H.LINE,
  },
};

const pres = new pptxgen();
pres.defineLayout({ name: "SAMPLE", width: 20, height: 11.25 });
pres.layout = "SAMPLE";
pres.theme = { headFontFace: "Pretendard", bodyFontFace: "Pretendard" };
pres.author = "정근녕";
pres.company = "졸업프로젝트 3201 2팀";
pres.subject = "IK와 Skinning을 통한 Piano Hand Simulator";
pres.title = "2학기 2차 중간발표";

const F = "Pretendard";
const FM = "Consolas";

const M = 1.04;            // 좌여백
const W = 17.92;           // 본문 폭 (1.04 → 18.96)
const RULE_Y = 2.32;       // 머리글 밑 가로선
const BY = 2.86;           // 본문 시작
const BBOT = 10.32;        // 본문 끝

// ───────────────────────── 레이아웃 ─────────────────────────
pres.defineSlideMaster({ title: "PLAIN", background: { color: H.BG }, objects: [] });

pres.defineSlideMaster({
  title: "BODY",
  background: { color: H.BG },
  objects: [
    { placeholder: { options: { name: "kicker", type: "body", x: M, y: 0.82, w: 10, h: 0.42,
        fontSize: 18, color: H.SAGE_L, align: "left", valign: "middle", margin: 0,
        fontFace: F, charSpacing: 0.6 }, text: "" } },
    { placeholder: { options: { name: "title", type: "title", x: M, y: 1.26, w: 13.6, h: 0.78,
        fontSize: 38, bold: true, color: H.SAGE, align: "left", valign: "middle", margin: 0,
        fontFace: F }, text: "" } },
    { line: { x: M, y: RULE_Y, w: W, h: 0, line: { color: H.LINE, width: 0.75 } } },
    { text: { text: "Piano Hand Simulator",
        options: { x: 13.6, y: 1.58, w: 5.36, h: 0.36, fontSize: 14, color: H.INK2,
          align: "right", valign: "middle", isTextBox: true, margin: 0, fontFace: F } } },
  ],
  slideNumber: { x: 18.3, y: 10.48, w: 0.66, h: 0.34, fontSize: 12, color: H.LINE, align: "right" },
});

// ───────────────────────── 헬퍼 ─────────────────────────
let _n = 0;
const on = (p) => `${p}_${++_n}`;

// 음수·0 폭/높이는 PowerPoint 가 파일을 거부하게 만든다. 조용히 넘기지 말고 바로 터뜨린다.
function guard(o, where) {
  for (const k of ["w", "h", "d"]) {
    if (o[k] !== undefined && !(o[k] > 0))
      throw new Error(`${where}: ${k}=${o[k]} (0 이하) — ${JSON.stringify(o).slice(0, 160)}`);
  }
}

function txt(s, t, o) {
  guard(o, "txt");
  s.addText(t, Object.assign({ isTextBox: true, margin: 0, fontFace: F, objectName: on("t") }, o));
}

function hline(s, y, x, w, color, width) {
  s.addShape(pres.ShapeType.line, { x: x === undefined ? M : x, y, w: w === undefined ? W : w, h: 0,
    line: { color: color || H.LINE, width: width || 0.75 }, objectName: on("hl") });
}

// 세로 막대 모티프 — 견본의 소제목 앞 ▍
function vbar(s, x, y, h, color) {
  s.addShape(pres.ShapeType.rect, { x, y, w: 0.075, h,
    fill: { color: color || H.SAGE }, line: { type: "none" }, objectName: on("vb") });
}

function pill(s, o) {
  s.addShape(pres.ShapeType.roundRect, { x: o.x, y: o.y, w: o.w, h: o.h,
    rectRadius: Math.min(o.h / 2, 0.5),
    fill: { color: o.fill || H.SAGE },
    line: o.line ? { color: o.line, width: o.lw || 1 } : { type: "none" },
    objectName: on("pill") });
  if (o.text !== undefined)
    txt(s, o.text, { x: o.x, y: o.y, w: o.w, h: o.h, fontSize: o.fs || 15,
      bold: o.bold !== false, color: o.color || H.WHITE, align: "center", valign: "middle" });
}

function circle(s, o) {
  s.addShape(pres.ShapeType.ellipse, { x: o.x, y: o.y, w: o.d, h: o.d,
    fill: { color: o.fill || H.SAGE },
    line: o.line ? { color: o.line, width: o.lw || 1 } : { type: "none" },
    objectName: on("c") });
  if (o.text !== undefined)
    txt(s, o.text, { x: o.x, y: o.y, w: o.d, h: o.d, fontSize: o.fs || 17,
      bold: true, color: o.color || H.WHITE, align: "center", valign: "middle",
      lineSpacingMultiple: 1.15 });
}

// 면 없는 수치 — 위에 얇은 선, 아래 큰 숫자와 설명
function figure(s, o) {
  hline(s, o.y, o.x, o.w, o.rule || H.LINE, o.rule ? 1.4 : 0.75);
  txt(s, [
    { text: o.value, options: { fontSize: o.vs || 40, bold: true, color: o.color || H.INK, fontFace: F } },
    { text: o.unit ? " " + o.unit : "", options: { fontSize: 17, bold: true, color: o.color || H.INK2, fontFace: F } },
  ], { x: o.x, y: o.y + 0.22, w: o.w, h: 0.74, align: "left", valign: "middle" });
  txt(s, o.label, { x: o.x, y: o.y + 1.02, w: o.w, h: o.lh || 0.76, fontSize: o.ls || 13.5,
    color: H.INK2, align: "left", valign: "top", lineSpacingMultiple: 1.35 });
}

// 가로선으로 나뉜 목록 행
function rows(s, items, o) {
  const rh = o.rh || 0.92;
  items.forEach((it, i) => {
    const y = o.y + i * rh;
    hline(s, y, o.x, o.w, H.LINE);
    if (it.render) { it.render(y, rh); return; }
    txt(s, it.left, { x: o.x, y: y + 0.08, w: o.lw || 3.2, h: rh - 0.16,
      fontSize: o.lfs || 16, bold: true, color: it.lcolor || H.SAGE_D, valign: "middle" });
    txt(s, it.right, { x: o.x + (o.lw || 3.2) + 0.3, y: y + 0.08, w: o.w - (o.lw || 3.2) - 0.3,
      h: rh - 0.16, fontSize: o.rfs || 15, color: it.rcolor || H.INK, valign: "middle",
      lineSpacingMultiple: 1.3 });
  });
  hline(s, o.y + items.length * rh, o.x, o.w, H.LINE);
}

function bullets(s, items, o) {
  const runs = items.map((it, i) => {
    const b = typeof it === "string" ? { text: it } : it;
    return {
      text: b.text,
      options: Object.assign({
        bullet: b.bullet === false ? false : { code: "2022", indent: 18 },
        color: b.color || H.INK2, bold: !!b.bold,
        fontSize: b.fontSize || o.fontSize || 15,
        paraSpaceAfter: b.gap !== undefined ? b.gap : (o.gap === undefined ? 11 : o.gap),
        breakLine: i !== items.length - 1, fontFace: F,
      }, b.options || {}),
    };
  });
  txt(s, runs, { x: o.x, y: o.y, w: o.w, h: o.h, align: "left", valign: "top",
    lineSpacingMultiple: o.lsm || 1.35 });
}

// 베이지 설명 띠
function band(s, o) {
  s.addShape(pres.ShapeType.roundRect, { x: o.x === undefined ? M : o.x, y: o.y,
    w: o.w === undefined ? W : o.w, h: o.h, rectRadius: 0.12,
    fill: { color: o.fill || H.BEIGE }, line: { type: "none" }, objectName: on("band") });
}

// 사진은 베이지 테두리 안에 둔다
function photo(s, o) {
  s.addShape(pres.ShapeType.rect, { x: o.x - 0.05, y: o.y - 0.05, w: o.w + 0.1, h: o.h + 0.1,
    fill: { color: H.BEIGE }, line: { type: "none" }, objectName: on("fr") });
  s.addImage({ path: o.path, x: o.x, y: o.y, w: o.w, h: o.h,
    sizing: { type: o.fit || "cover", w: o.w, h: o.h }, objectName: on("img") });
  if (o.cap) txt(s, o.cap, { x: o.x, y: o.y + o.h + 0.16, w: o.w, h: 0.34,
    fontSize: 12, color: H.INK2, align: "center", valign: "top", lineSpacingMultiple: 1.25 });
}

function head(kicker, title, section) {
  const s = pres.addSlide({ masterName: "BODY", sectionTitle: section });
  txt(s, kicker, { placeholder: "kicker" });
  txt(s, title, { placeholder: "title" });
  return s;
}

function lead(s, t, y) {
  txt(s, t, { x: M, y: y === undefined ? BY - 0.1 : y, w: W, h: 0.4, fontSize: 16,
    color: H.INK2, valign: "middle" });
}

function sub(s, x, y, t, w, color) {
  vbar(s, x, y + 0.04, 0.38, color || H.SAGE);
  txt(s, t, { x: x + 0.22, y, w: w || 5, h: 0.46, fontSize: 20, bold: true,
    color: H.INK, valign: "middle" });
}

// 장 구분
function divider(num, title, desc, owner, section) {
  const s = pres.addSlide({ masterName: "PLAIN", sectionTitle: section });
  txt(s, `Chapter ${num}.`, { x: M, y: 4.3, w: 8, h: 0.46, fontSize: 20, color: H.SAGE_L,
    charSpacing: 0.6, valign: "middle" });
  vbar(s, M, 4.92, 0.98, H.SAGE_L);
  txt(s, title, { x: M + 0.32, y: 4.88, w: 11, h: 1.06, fontSize: 48, bold: true,
    color: H.SAGE, valign: "middle" });
  hline(s, 6.26, M, 10.4);
  txt(s, desc, { x: M, y: 6.5, w: 11.4, h: 1.3, fontSize: 15.5, color: H.INK2,
    valign: "top", lineSpacingMultiple: 1.5 });
  pill(s, { x: M, y: 8.0, w: 2.0, h: 0.54, text: owner, fill: H.BEIGE, color: H.SAGE_D, fs: 15 });
  txt(s, "PIANO HAND SIMULATOR", { x: 0, y: 9.08, w: 20, h: 1.5, fontSize: 56, bold: true,
    color: H.BEIGE, align: "center", valign: "middle", charSpacing: 3 });
  return s;
}

const SEC = { intro: "도입", fing: "01 운지법", ik: "02 IK",
              gpu: "03 GPU 스키닝", flesh: "04 Chaos Flesh", wrap: "05 통합과 마무리" };

// ═══════════════════ 1. 표지 ═══════════════════
pres.addSection({ title: SEC.intro });
{
  const s = pres.addSlide({ masterName: "PLAIN", sectionTitle: SEC.intro });
  txt(s, "졸업프로젝트[3201] 2팀", { x: 0, y: 1.5, w: 20, h: 0.42, fontSize: 17,
    color: H.SAGE_L, align: "center", valign: "middle", charSpacing: 1 });
  txt(s, "IK와 Skinning을 통한", { x: 0, y: 2.22, w: 20, h: 0.92, fontSize: 36,
    color: H.SAGE, align: "center", valign: "middle", charSpacing: 2 });
  hline(s, 3.22, 6.1, 7.8);
  txt(s, "Piano Hand Simulator", { x: 0, y: 3.34, w: 20, h: 1.26, fontSize: 60, bold: true,
    color: H.SAGE, align: "center", valign: "middle", charSpacing: 1 });
  pill(s, { x: 6.9, y: 4.86, w: 6.2, h: 0.72, fill: H.BEIGE, color: H.INK2, bold: false, fs: 15,
    text: "2차 중간발표  ·  2026. 10. 30  ·  지도교수 김형석" });

  const mem = [["정근녕", "운지법 · 04_Main"], ["한승현", "역운동학 (IK)"],
               ["이수민", "GPU 스키닝"], ["곽경민", "Chaos Flesh"]];
  const mw = 3.3, gap = 0.5;
  const startX = (20 - (mw * 4 + gap * 3)) / 2;
  mem.forEach((m, i) => {
    const x = startX + i * (mw + gap);
    hline(s, 6.0, x, mw);
    txt(s, m[0], { x, y: 6.14, w: mw, h: 0.4, fontSize: 17, bold: true, color: H.SAGE_D,
      align: "center", valign: "middle" });
    txt(s, m[1], { x, y: 6.56, w: mw, h: 0.36, fontSize: 13, color: H.INK2,
      align: "center", valign: "middle" });
  });

  s.addImage({ path: CROP + "/lt_cover_hands.png", x: 0, y: 8.05, w: 20, h: 3.2,
    sizing: { type: "cover", w: 20, h: 3.2 }, objectName: "cover_hands" });
  s.addImage({ path: CROP + "/lt_fade_down.png", x: 0, y: 8.05, w: 20, h: 1.3,
    objectName: "cover_fade" });

  s.addNotes("2팀 발표 시작합니다. 저희 주제는 MIDI 파일을 입력으로 받아 피아노를 치는 손을 시뮬레이션하는 것입니다.\n모듈은 네 개로 나뉘어 있고, 2차 발표의 핵심은 '각 모듈이 실제로 돌아가게 되었고, 서로 붙기 시작했다'는 점입니다.");
}

// ═══════════════════ 2. 목차 ═══════════════════
{
  const s = pres.addSlide({ masterName: "PLAIN", sectionTitle: SEC.intro });
  vbar(s, 2.0, 4.1, 1.0, H.SAGE_L);
  txt(s, "목차", { x: 2.34, y: 4.06, w: 5, h: 1.08, fontSize: 50, color: H.SAGE,
    valign: "middle", charSpacing: 3 });
  txt(s, "CONTENTS", { x: 2.36, y: 5.3, w: 5, h: 0.4, fontSize: 15, color: H.SAGE_L,
    valign: "middle", charSpacing: 2 });

  const items = [
    ["Chapter 1.", "프로젝트 개요와 2학기 변화", "무엇이 어떻게 달라졌는지"],
    ["Chapter 2.", "운지법 결정 엔진", "제약을 거는 단위를 바꾼 이야기 · 정근녕"],
    ["Chapter 3.", "역운동학 (IK)", "Weighted DLS와 건반 모델 연동 · 한승현"],
    ["Chapter 4.", "GPU 스키닝", "6‑Pass 정점 파이프라인 · 이수민"],
    ["Chapter 5.", "Chaos Flesh", "사면체 물리와 부피 보존 · 곽경민"],
    ["Chapter 6.", "모듈 통합과 남은 과제", "붙여 보니 드러난 것들"],
  ];
  const lx = 9.0, lw = 9.96, rh = 1.08, ly = 2.36;
  items.forEach((it, i) => {
    const y = ly + i * rh;
    hline(s, y, lx, lw);
    txt(s, it[0], { x: lx, y: y + 0.16, w: 1.9, h: rh - 0.3, fontSize: 13.5,
      color: H.SAGE_L, valign: "middle" });
    txt(s, it[1], { x: lx + 2.0, y: y + 0.12, w: lw - 2.0, h: 0.46, fontSize: 21, bold: true,
      color: H.INK, valign: "middle" });
    txt(s, it[2], { x: lx + 2.0, y: y + 0.58, w: lw - 2.0, h: 0.36, fontSize: 13,
      color: H.INK2, valign: "middle" });
  });
  hline(s, ly + items.length * rh, lx, lw);

  s.addNotes("순서는 개요 먼저, 그다음 모듈 네 개, 마지막에 통합과 남은 과제입니다.\n모듈별 발표자는 해당 파트 담당자가 이어서 말씀드립니다.");
}

// ═══════════════════ 3. 1학기 대비 2학기 ═══════════════════
{
  const s = head("Chapter 1.", "1학기와 2학기, 무엇이 달라졌는가", SEC.intro);
  lead(s, "1학기는 \"이 방법이 되는가\"를 확인하는 단계였고, 2학기는 \"실제로 돌아가게 만들고 서로 붙이는\" 단계다.");

  const ty = BY + 0.92, rh = 1.26;
  const cx = [M, M + 3.4, M + 10.2];
  const cw = [3.4, 6.5, W - 10.2];
  txt(s, "1학기", { x: cx[1], y: ty - 0.44, w: cw[1], h: 0.36, fontSize: 14,
    color: H.LINE, charSpacing: 1, valign: "middle" });
  txt(s, "2학기", { x: cx[2], y: ty - 0.44, w: cw[2], h: 0.36, fontSize: 14, bold: true,
    color: H.SAGE_D, charSpacing: 1, valign: "middle" });

  [
    ["각 모듈", "알고리즘이 성립하는지 검증", "실제 데이터로 동작하는 구현"],
    ["모듈 간", "문서상의 인터페이스 약속", "코드 수준 공유 상수 · 실파일 연동"],
    ["스키닝", "포스트프로세스 사전 검증", "정점 처리 단계 6‑Pass 파이프라인"],
    ["물리", "Chaos Flesh 적용 가능성 확인", "TetWild 사면체 + 렌더 메시 바인딩"],
    ["검증", "눈으로 보고 판단", "지표 자동 측정 + 회귀 테스트 5종"],
  ].forEach((r, i) => {
    const y = ty + i * rh;
    hline(s, y, M, W);
    txt(s, r[0], { x: cx[0], y: y + 0.1, w: cw[0] - 0.3, h: rh - 0.2, fontSize: 18, bold: true,
      color: H.SAGE_D, valign: "middle" });
    txt(s, r[1], { x: cx[1], y: y + 0.1, w: cw[1] - 0.8, h: rh - 0.2, fontSize: 15.5,
      color: H.LINE, valign: "middle" });
    s.addShape(pres.ShapeType.rightArrow, { x: cx[1] + cw[1] - 0.62, y: y + rh / 2 - 0.1,
      w: 0.34, h: 0.2, fill: { color: H.SAGE_L }, line: { type: "none" }, objectName: on("ar") });
    txt(s, r[2], { x: cx[2], y: y + 0.1, w: cw[2], h: rh - 0.2, fontSize: 15.5,
      color: H.INK, valign: "middle" });
  });
  hline(s, ty + 5 * rh, M, W);

  s.addNotes("왼쪽이 1학기, 오른쪽이 2학기입니다.\n핵심은 '검증' 줄입니다. 1학기에는 눈으로 보고 괜찮다고 판단했는데, 그 방식으로는 놓치는 결함이 많았습니다. 뒤에서 그 이야기를 하겠습니다.");
}

// ═══════════════════ 4. 전체 파이프라인 ═══════════════════
{
  const s = head("Chapter 1.", "전체 파이프라인과 모듈 간 인터페이스", SEC.intro);

  const boxes = [
    { label: "MIDI 파일", sub: "실곡 13곡 + 기준 8곡", fill: H.BEIGE, color: H.INK2, owner: "" },
    { label: "01 운지법", sub: "화음 DP + 시간 제약", fill: H.SAGE, color: H.WHITE, owner: "정근녕" },
    { label: "02 IK", sub: "Weighted DLS", fill: H.SAGE_D, color: H.WHITE, owner: "한승현" },
    { label: "03 스키닝", sub: "GPU 6‑Pass · Chaos Flesh", fill: H.SAGE, color: H.WHITE, owner: "이수민 · 곽경민" },
    { label: "UE5 렌더", sub: "최종 영상", fill: H.BEIGE, color: H.INK2, owner: "" },
  ];
  const d = 2.74, gap = 1.02, by = 5.0;
  const sx = (20 - (d * 5 + gap * 4)) / 2;
  boxes.forEach((b, i) => {
    const x = sx + i * (d + gap);
    circle(s, { x, y: by, d, fill: b.fill, text: "", });
    txt(s, b.label, { x: x + 0.1, y: by + d / 2 - 0.52, w: d - 0.2, h: 0.46, fontSize: 18,
      bold: true, color: b.color, align: "center", valign: "middle" });
    txt(s, b.sub, { x: x + 0.14, y: by + d / 2 - 0.04, w: d - 0.28, h: 0.62, fontSize: 11.5,
      color: b.color === H.WHITE ? H.WHITE : H.INK2, align: "center", valign: "top",
      lineSpacingMultiple: 1.25 });
    if (b.owner) txt(s, b.owner, { x, y: by + d + 0.2, w: d, h: 0.34, fontSize: 13,
      bold: true, color: H.SAGE_D, align: "center", valign: "middle" });
    if (i < 4) hline(s, by + d / 2, x + d + 0.16, gap - 0.32, H.LINE, 1.2);
  });

  const ifs = [
    { i: 1, name: "A", desc: "*_polyphonic_result.json\n*_fingering.csv" },
    { i: 2, name: "B", desc: "joints.csv + wrist.csv\n30 FPS → AnimSequence" },
    { i: 3, name: "C", desc: "정점 버퍼\nlerp(스키닝, Flesh, Blend)" },
  ];
  ifs.forEach((f) => {
    const cx2 = sx + f.i * (d + gap) - gap / 2;
    s.addShape(pres.ShapeType.line, { x: cx2, y: by - 0.62, w: 0, h: 0.62 + d / 2,
      line: { color: H.LINE, width: 0.75, dashType: "sysDot" }, objectName: on("ifl") });
    circle(s, { x: cx2 - 0.26, y: by - 1.14, d: 0.52, fill: H.SAGE_D, text: f.name, fs: 15 });
    txt(s, f.desc, { x: cx2 - 2.0, y: by - 2.08, w: 4.0, h: 0.84, fontSize: 12,
      color: H.INK2, align: "center", valign: "bottom", fontFace: FM, lineSpacingMultiple: 1.3 });
  });

  band(s, { y: 9.04, h: 1.22 });
  txt(s, [
    { text: "2차에서 달라진 점 — ", options: { bold: true, color: H.SAGE_D, fontSize: 16, fontFace: F } },
    { text: "A·B·C 모두 실제 파일이 오가는 상태가 되었다. 1차에서는 전부 문서상의 약속이었다.",
      options: { color: H.INK, fontSize: 16, breakLine: true, fontFace: F } },
    { text: "좌표 단위는 mm로 통일하고, UE5(cm)는 소비하는 쪽에서 ÷10 한다.",
      options: { color: H.INK2, fontSize: 13.5, fontFace: F } },
  ], { x: M + 0.44, y: 9.24, w: W - 0.88, h: 0.84, valign: "middle", lineSpacingMultiple: 1.45 });

  s.addNotes("왼쪽부터 MIDI가 들어와서 운지법이 손가락을 정하고, IK가 관절 각도를 만들고, 스키닝이 살을 그립니다.\n원 사이 A·B·C가 모듈 간 인터페이스입니다. 2차에서는 이 세 군데 모두 실제 파일이 흐릅니다.\n단위는 mm로 통일했습니다. 이게 왜 중요한지는 뒤에서 말씀드립니다.");
}

// ═══════════════════ 01 운지법 ═══════════════════
pres.addSection({ title: SEC.fing });
divider("2", "운지법 결정 엔진",
  "MIDI의 음표 하나하나에 어느 손 몇 번 손가락을 쓸지 정한다.\n사람이 실제로 칠 수 있는 손 모양이어야 하므로, 물리 제약을 만족하는 배정만 허용한다.",
  "정근녕", SEC.fing);

{
  const s = head("Chapter 2.", "모듈의 역할과 처리 흐름", SEC.fing);
  lead(s, "여섯 단계로 돌아간다. 1학기에는 3단계까지였고, 4·5단계가 2학기에 새로 들어왔다.");

  const steps = [
    ["MIDI 파싱", "전 트랙 템포맵을 모아\ntick → ms 로 변환", false],
    ["손 분리 · 화음 그룹화", "양손에 음을 나누고\n동시 타건을 묶는다", false],
    ["화음 단위 DP", "빔 폭 120으로 가지치기한\n동적 계획법", false],
    ["시간 제약 해소", "순간 단위로 손가락 충돌과\n손 범위를 다시 검사", true],
    ["점유 구간 산출", "페달을 걷어내고\nkey_hold_ms 를 계산", true],
    ["출력", "JSON / UE5 DataTable CSV\n+ 평가 지표", false],
  ];
  const d = 1.42, cw = (W - 0.5 * 5) / 6, cy = BY + 0.9;
  steps.forEach((st, i) => {
    const x = M + i * (cw + 0.5);
    circle(s, { x: x + cw / 2 - d / 2, y: cy, d, text: String(i + 1), fs: 22,
      fill: st[2] ? H.SAGE_D : H.BEIGE, color: st[2] ? H.WHITE : H.SAGE_D });
    if (i < 5) hline(s, cy + d / 2, x + cw / 2 + d / 2 + 0.12, 0.5 + cw - d - 0.24, H.LINE, 1.2);
    if (st[2]) txt(s, "2학기 신규", { x, y: cy - 0.46, w: cw, h: 0.34, fontSize: 11.5,
      bold: true, color: H.SAGE_D, align: "center", valign: "middle" });
    txt(s, st[0], { x, y: cy + d + 0.26, w: cw, h: 0.72, fontSize: 15.5, bold: true,
      color: H.INK, align: "center", valign: "top", lineSpacingMultiple: 1.2 });
    txt(s, st[1], { x, y: cy + d + 1.02, w: cw, h: 1.0, fontSize: 12.5, color: H.INK2,
      align: "center", valign: "top", lineSpacingMultiple: 1.35 });
  });

  s.addNotes("운지법 엔진은 여섯 단계로 돌아갑니다.\n1학기에는 3번 DP까지였고, 2학기에 4번과 5번이 새로 들어왔습니다. 진하게 표시한 두 단계가 오늘 말씀드릴 핵심입니다.");
}

{
  const s = head("Chapter 2.", "제약을 화음 단위로 걸고 있었다", SEC.fing);
  lead(s, "손이 닿는 범위, 한 손가락은 한 건반, 손가락 순서 — 이 제약들은 모두 \"시간상의 한 순간\"에 성립해야 한다.");

  s.addImage({ path: CROP + "/lt_constraint_unit.png", x: M + 0.5, y: BY + 0.42, w: 16.92, h: 5.53,
    objectName: "diag_constraint" });

  const fw = (W - 0.9 * 2) / 3;
  [
    { v: "3", u: "건", l: "화음 단위로 셌을 때의 실제 데이터 위반", c: H.INK, r: H.LINE },
    { v: "2,552", u: "건", l: "순간 단위로 셌을 때의 같은 데이터 위반", c: H.RUST, r: H.RUST },
    { v: "0", u: "건", l: "재정의 후 현재 (21곡 전체)", c: H.SAGE_D, r: H.SAGE_D },
  ].forEach((d2, i) => {
    figure(s, { x: M + i * (fw + 0.9), y: 8.86, w: fw, value: d2.v, unit: d2.u,
      color: d2.c, label: d2.l, rule: d2.r, vs: 38, lh: 0.6 });
  });

  s.addNotes("여기가 2학기 운지법 작업의 중심입니다.\n손이 닿는 범위나 손가락 충돌 같은 제약은 '어느 순간'에 성립해야 하는 조건인데, 엔진은 화음이라는 묶음 단위로 검사하고 있었습니다.\n화음은 시간을 나누지 않습니다. 앞 화음의 지속음이 다음 화음까지 걸쳐 있으면 그 겹침이 보이지 않습니다.\n검사 단위를 바꾸자 3건이던 위반이 2,552건으로 드러났습니다. 없던 문제가 생긴 게 아니라, 원래 있었는데 못 보던 것입니다. 지금은 0건입니다.");
}

{
  const s = head("Chapter 2.", "소리의 지속과 손가락의 점유는 다르다", SEC.fing);

  band(s, { y: BY - 0.14, h: 1.42 });
  txt(s, [
    { text: "MIDI의 note_off 는 페달 때문에 늘어난 ", options: { fontSize: 17, color: H.INK, fontFace: F } },
    { text: "소리", options: { fontSize: 17, bold: true, color: H.SAGE_D, fontFace: F } },
    { text: "의 끝이지, 손가락이 건반에서 떨어진 시점이 아니다.",
      options: { fontSize: 17, color: H.INK, breakLine: true, fontFace: F } },
    { text: "그래서 점유 시간을 뜻하는 key_hold_ms 를 따로 두고, 제약 검사와 IK 입력은 이 값을 쓰도록 했다.",
      options: { fontSize: 14, color: H.INK2, fontFace: F } },
  ], { x: M + 0.44, y: BY + 0.1, w: W - 0.88, h: 0.96, valign: "middle", lineSpacingMultiple: 1.5 });

  txt(s, "드뷔시 '달빛'에서 측정한 결과", { x: M, y: BY + 1.78, w: 8, h: 0.4, fontSize: 15,
    bold: true, color: H.SAGE_D, valign: "middle" });
  const fw2 = (W - 0.76 * 3) / 4;
  [
    { v: "76.7", u: "%", l: "곡 전체에서 페달이\n눌려 있던 시간 비율", c: H.INK, r: H.LINE },
    { v: "87", u: "%", l: "손가락 충돌 111건 중\n페달 구간에서 발생 (97건)", c: H.RUST, r: H.RUST },
    { v: "3,000", u: "ms", l: "같은 손가락이 두 건반을\n동시에 잡던 최대 중첩", c: H.RUST, r: H.RUST, vs: 36 },
    { v: "0", u: "ms", l: "key_hold_ms 적용 후\n최대 중첩", c: H.SAGE_D, r: H.SAGE_D },
  ].forEach((d2, i) => {
    figure(s, { x: M + i * (fw2 + 0.76), y: BY + 2.32, w: fw2, value: d2.v, unit: d2.u,
      color: d2.c, label: d2.l, rule: d2.r, vs: d2.vs });
  });

  band(s, { y: 9.0, h: 1.3, fill: H.SAGE_L });
  txt(s, [
    { text: "IK 파트에 드리는 당부 — ", options: { bold: true, color: H.SAGE_D, fontSize: 16.5, fontFace: F } },
    { text: "건반에서 손가락을 떼는 시점은 반드시 ", options: { color: H.INK, fontSize: 16.5, fontFace: F } },
    { text: "start_ms + key_hold_ms", options: { color: H.SAGE_D, fontSize: 16.5, fontFace: FM, bold: true } },
    { text: " 를 쓸 것.", options: { color: H.INK, fontSize: 16.5, breakLine: true, fontFace: F } },
    { text: "duration_ms 로 떼면 한 손가락이 서로 다른 건반을 동시에 누르는 자세가 만들어진다.",
      options: { color: H.INK2, fontSize: 13.5, fontFace: F } },
  ], { x: M + 0.44, y: 9.22, w: W - 0.88, h: 0.9, valign: "middle", lineSpacingMultiple: 1.45 });

  s.addNotes("두 번째 발견입니다.\n피아노는 페달을 밟으면 손가락을 떼도 소리가 계속 납니다. MIDI의 note_off는 그 소리가 끝난 시점이지 손가락이 떨어진 시점이 아닙니다.\n달빛은 곡의 76.7% 동안 페달이 밟혀 있었고, 손가락 충돌 111건 중 97건이 페달 구간이었습니다. 즉 대부분이 이 착각 때문이었습니다.\n마지막 줄이 IK 파트에 중요합니다. duration_ms로 건반을 떼면 한 손가락이 두 건반을 동시에 누르는 자세가 나옵니다.");
}

{
  const s = head("Chapter 2.", "21곡에서 물리 제약 위반 0건", SEC.fing);

  const fw3 = (W - 0.66 * 4) / 5;
  [
    { v: "21", u: "곡", l: "실곡 13곡 + 기준 8곡", c: H.INK, r: H.LINE },
    { v: "0", u: "건", l: "물리 제약 위반", c: H.SAGE_D, r: H.SAGE_D },
    { v: "0.000", u: "ms", l: "템포 변화 구간\n타이밍 오차", c: H.SAGE_D, r: H.SAGE_D, vs: 34 },
    { v: "85.2", u: "%", l: "음표 보존율", c: H.INK, r: H.LINE },
    { v: "17.8", u: "초", l: "21곡 전체 처리 시간", c: H.INK, r: H.LINE },
  ].forEach((d2, i) => {
    figure(s, { x: M + i * (fw3 + 0.66), y: BY, w: fw3, value: d2.v, unit: d2.u,
      color: d2.c, label: d2.l, rule: d2.r, vs: d2.vs || 36, lh: 0.66 });
  });

  // 네이티브 차트 — 견본 팔레트
  const cy2 = BY + 2.12, chh = 4.1;
  txt(s, "손가락별 사용 분포", { x: M, y: cy2, w: 8.4, h: 0.4, fontSize: 15, bold: true,
    color: H.SAGE_D, valign: "middle" });
  s.addChart(pres.ChartType.bar, [
    { name: "드뷔시 Clair de Lune", labels: ["1번 엄지", "2번 검지", "3번 중지", "4번 약지", "5번 소지"],
      values: [19.2, 26.8, 22.1, 17.8, 14.0] },
    { name: "Super Mario 64 Medley", labels: ["1번 엄지", "2번 검지", "3번 중지", "4번 약지", "5번 소지"],
      values: [20.0, 25.7, 12.8, 23.1, 18.3] },
  ], {
    x: M, y: cy2 + 0.46, w: 8.4, h: chh,
    barDir: "col", barGapWidthPct: 45,
    chartColors: [H.SAGE, H.LINE],
    showValue: true, dataLabelPosition: "outEnd", dataLabelColor: H.INK2,
    dataLabelFontSize: 10, dataLabelFontFace: "+mn-lt", dataLabelFormatCode: '0.0"%"',
    showLegend: true, legendPos: "b", legendColor: H.INK2, legendFontSize: 11,
    legendFontFace: "+mn-lt",
    catAxisLabelColor: H.INK2, catAxisLabelFontSize: 11, catAxisLabelFontFace: "+mn-lt",
    valAxisLabelColor: H.INK2, valAxisLabelFontSize: 10, valAxisLabelFontFace: "+mn-lt",
    valAxisMaxVal: 30, valAxisMajorUnit: 10,
    valGridLine: { color: H.BEIGE, size: 1 }, catGridLine: { style: "none" },
    chartArea: { fill: { color: H.BG } }, plotArea: { fill: { color: H.BG } },
    border: { pt: 0, color: H.BG },
  });
  txt(s, "엄지와 검지에 쏠리지 않고 고르게 퍼져 있다", { x: M, y: cy2 + 0.46 + chh + 0.08,
    w: 8.4, h: 0.34, fontSize: 12, color: H.INK2, align: "center" });

  const rx = M + 9.2;
  txt(s, "성부 역할 분포 — 드뷔시 '달빛'", { x: rx, y: cy2, w: W - 9.2, h: 0.4, fontSize: 15,
    bold: true, color: H.SAGE_D, valign: "middle" });
  s.addChart(pres.ChartType.doughnut, [
    { name: "성부", labels: ["BASS", "INNER", "MELODY"], values: [41.2, 30.9, 28.0] },
  ], {
    x: rx, y: cy2 + 0.46, w: W - 9.2, h: chh,
    holeSize: 58, chartColors: [H.SAGE_D, H.SAGE_L, H.BEIGE2],
    showValue: true, dataLabelColor: H.INK, dataLabelFontSize: 12,
    dataLabelFontFace: "+mn-lt", dataLabelFormatCode: '0.0"%"',
    showLegend: true, legendPos: "b", legendColor: H.INK2, legendFontSize: 11,
    legendFontFace: "+mn-lt",
    chartArea: { fill: { color: H.BG } }, plotArea: { fill: { color: H.BG } },
    border: { pt: 0, color: H.BG },
  });
  txt(s, "멜로디·베이스·내성을 구분해 손을 나눈다", { x: rx, y: cy2 + 0.46 + chh + 0.08,
    w: W - 9.2, h: 0.34, fontSize: 12, color: H.INK2, align: "center" });

  s.addNotes("현재 결과입니다. 21곡에서 물리 제약 위반 0건입니다.\n타이밍 오차 0.000ms는 템포가 바뀌는 곡에서도 시간 계산이 정확하다는 뜻입니다. 전에는 템포 변화를 첫 번째 값으로만 처리해서 58.7% 오차가 났습니다.\n음표 보존율 85.2%는 나머지 15%를 버렸다는 뜻인데, 밴드 편곡 곡처럼 애초에 두 손으로 못 치는 구간에 몰려 있습니다.");
}

{
  const s = head("Chapter 2.", "위반이 엔진 탓인지 입력 탓인지 구분할 수 없었다", SEC.fing);

  const cw2 = (W - 1.0) / 2;
  sub(s, M, BY, "문제 — 게임 음악 MIDI는 애초에 두 손으로 칠 수 없다", cw2, H.RUST);
  bullets(s, [
    "밴드 편곡을 그대로 받으면 동시에 10음이 넘는다",
    "위반이 나와도 엔진 결함인지 입력 탓인지 알 수 없다",
    "1학기 내내 deb_clai 와 Super Mario 두 곡으로만 검증했다",
    { text: "그런데 이 둘은 유독 깨끗한 샘플이었다", color: H.RUST, bold: true },
  ], { x: M + 0.24, y: BY + 0.74, w: cw2 - 0.24, h: 2.3, fontSize: 15, gap: 9 });

  const rx2 = M + cw2 + 1.0;
  sub(s, rx2, BY, "대응 — 연주 가능함이 보장된 8곡을 직접 만들었다", cw2, H.SAGE);
  bullets(s, [
    "5지 포지션 · 블록 코드 · 알베르티 · 페달 아르페지오",
    "지속 베이스 · 포지션 이동 · 내성 · 음계",
    { text: "여기서 나는 위반은 전부 엔진 결함이다", color: H.SAGE_D, bold: true },
    "판정의 모호함이 사라진다",
  ], { x: rx2 + 0.24, y: BY + 0.74, w: cw2 - 0.24, h: 2.3, fontSize: 15, gap: 9 });

  const fw4 = (W - 0.9 * 2) / 3;
  [
    { v: "81.6", u: "%", l: "실곡 위반 시점 중, 애초에 어떤 운지법으로도\n연주가 불가능한 구간이 차지하는 비율", c: H.INK, r: H.LINE },
    { v: "8", u: "곡", l: "기준 코퍼스 ref_01 ~ ref_08\n엔진 검증은 이쪽으로만 판단한다", c: H.SAGE_D, r: H.SAGE_D },
    { v: "5", u: "종", l: "회귀 테스트 — 타이밍 · 건반 좌표\n지표 · 점유 산출 · 기준 코퍼스", c: H.INK, r: H.LINE },
  ].forEach((d2, i) => {
    figure(s, { x: M + i * (fw4 + 0.9), y: BY + 3.5, w: fw4, value: d2.v, unit: d2.u,
      color: d2.c, label: d2.l, rule: d2.r });
  });

  band(s, { y: 9.14, h: 1.0 });
  txt(s, "실곡에서 나오는 위반 수는 엔진의 정확도가 아니라 입력 MIDI의 연주 가능성을 나타내는 지표다. 두 가지를 섞어서 보면 안 된다.",
    { x: M + 0.44, y: 9.34, w: W - 0.88, h: 0.6, fontSize: 15, color: H.SAGE_D, valign: "middle" });

  s.addNotes("이 부분이 2학기에 일하는 방식을 바꾼 지점입니다.\n게임 음악 MIDI는 밴드 편곡이라 동시에 10음이 넘는 구간이 흔합니다. 위반이 나와도 엔진이 틀린 건지 입력이 못 칠 곡인 건지 알 수가 없었습니다.\n그래서 사람이 확실히 칠 수 있는 8곡을 직접 만들었습니다. 여기서 나는 위반은 전부 엔진 결함입니다.\n1학기에는 두 곡으로만 검증했는데, 공교롭게도 둘 다 깨끗한 샘플이어서 결함이 가려져 있었습니다.");
}

// ═══════════════════ 02 IK ═══════════════════
pres.addSection({ title: SEC.ik });
divider("3", "역운동학 (IK)",
  "운지법이 정한 \"어느 손가락이 어느 건반을\"을 받아, 그 손가락 끝이 건반에 닿는 관절 각도를 구한다.\n실시간이 아니라 오프라인 사전 계산이므로 수렴 속도보다 정확도를 우선한다.",
  "한승현", SEC.ik);

{
  const s = head("Chapter 3.", "Weighted Damped Least Squares", SEC.ik);

  band(s, { y: BY, h: 1.92, fill: H.BEIGE });
  txt(s, "Δθ  =  W⁻¹Jᵀ ( J W⁻¹Jᵀ + λ²I )⁻¹ Δe",
    { x: M, y: BY + 0.3, w: W, h: 0.82, fontSize: 32, bold: true, color: H.SAGE_D,
      align: "center", valign: "middle" });
  txt(s, "J 는 자코비안, W 는 관절별 가중치, λ 는 감쇠 계수, Δe 는 목표까지의 오차",
    { x: M, y: BY + 1.16, w: W, h: 0.42, fontSize: 14, color: H.INK2, align: "center", valign: "middle" });

  rows(s, [
    { left: "감쇠항  λ²I", right: "특이점 근처에서 역행렬이 발산하는 것을 막는다. 해가 조금 부정확해지는 대신 안정적으로 수렴한다." },
    { left: "가중치  W", right: "관절 한계에 가까워질수록 가중치를 낮춰 그 관절을 덜 움직인다. 급정지 대신 부드럽게 감속한다." },
    { left: "수렴 조건", right: "반복 상한 40회, 허용 오차 0.01 — cm 가 아니라 IK 내부 단위이며 약 0.05 cm 다." },
    { left: "손목 궤적", right: "지수 감쇠 보간으로 접근하면서, 남은 이동 거리에 비례해 손목을 들어 올린다.   arcMultiplier 0.2 · wristReachMargin 0.8 (≈ 4.1 cm)" },
  ], { x: M, y: BY + 2.5, w: W, rh: 1.26, lw: 3.6, lfs: 18, rfs: 15.5 });

  s.addNotes("IK는 Weighted DLS를 씁니다.\n일반 자코비안 역행렬은 특이점에서 발산하는데, 감쇠항을 넣어 막습니다.\n가중치는 관절 한계에 가까워지면 낮아져서, 한계에 부딪혀 급정지하는 대신 부드럽게 감속합니다.\n오프라인 계산이라 반복 40회까지 여유 있게 돌립니다.");
}

{
  const s = head("Chapter 3.", "실제 비율 건반에 양손 10손가락 타건", SEC.ik);
  const vw = 10.4, vh = 5.85, vy = BY + 0.3;
  s.addShape(pres.ShapeType.rect, { x: M - 0.06, y: vy - 0.06, w: vw + 0.12, h: vh + 0.12,
    fill: { color: H.BEIGE }, line: { type: "none" }, objectName: "vidfr" });
  if (EMBED_VIDEO) {
    s.addMedia({ type: "video", path: R2 + "/KakaoTalk_20261028_173251429.mp4",
      x: M, y: vy, w: vw, h: vh });
  } else {
    s.addImage({ path: CROP + "/ik_vulkan.png", x: M, y: vy, w: vw, h: vh,
      sizing: { type: "contain", w: vw, h: vh }, objectName: "ik_vulkan" });
  }
  txt(s, "IK 솔버 출력 — 슬라이드에서 바로 재생한다", { x: M, y: vy + vh + 0.2, w: vw, h: 0.34,
    fontSize: 12.5, color: H.INK2, align: "center" });

  const rx3 = M + vw + 0.9;
  const rw = W - vw - 0.9;
  bullets(s, [
    { text: "실제 비율 건반 위에서 양손 10손가락이 움직인다", bold: true, color: H.INK, fontSize: 16 },
    "흑건은 건반 안쪽, 백건은 앞쪽 — 타건 지점을 구분한다",
    "엄지 뿌리를 CMC 위치로 옮기고 타건 지점 조정",
    { text: "출력: joints.csv + wrist.csv (30 FPS)", bold: true, color: H.INK, fontSize: 16 },
    "frame, time_ms, bone, flex_deg, abd_deg, twist_deg",
    "오른손 15행 / 프레임",
    "달빛 전곡 248초 · 7,447프레임 → 4초 만에 내보냄",
    { text: "검증기 RESULT: OK", bold: true, color: H.SAGE_D },
    { text: "A_IK_DebClai 애니메이션 생성 완료", bold: true, color: H.SAGE_D },
  ], { x: rx3, y: vy + 0.08, w: rw, h: 5.9, fontSize: 14.5, gap: 12 });

  s.addNotes("실제 비율 건반 위에서 양손이 움직입니다. 왼쪽이 IK 솔버가 직접 그린 화면입니다.\n흑건과 백건은 타건 지점이 다릅니다. 흑건은 건반 안쪽을, 백건은 앞쪽을 누릅니다.\n출력은 관절 각도 CSV이고, 달빛 전곡 7,447프레임을 4초 만에 내보냅니다. 검증기를 통과했고 UE5 애니메이션까지 만들었습니다.\n영상을 보시면 손목이 부자연스럽게 돌아가는 구간이 있는데, 마지막 통합 파트에서 원인을 말씀드립니다.");
}

{
  const s = head("Chapter 3.", "결과와 알려진 한계", SEC.ik);

  const cw3 = (W - 1.0) / 2;
  sub(s, M, BY, "확보한 것", cw3, H.SAGE);
  bullets(s, [
    "양손 10손가락이 실제 비율 건반을 친다",
    "관절 각도를 CSV로 내보내고 검증기로 확인한다",
    "UE5 AnimSequence 임포트까지 연결됐다",
    "달빛 전곡 248초 · 7,447프레임 변환 완료",
  ], { x: M + 0.24, y: BY + 0.74, w: cw3 - 0.24, h: 2.4, fontSize: 15, gap: 11 });

  const rx4 = M + cw3 + 1.0;
  sub(s, rx4, BY, "알려진 한계", cw3, H.RUST);
  bullets(s, [
    "마디 길이를 MetaHuman 실측값으로 바꾼 뒤 소지(5번) 오차가 35% → 57% 로 늘었다",
    "한 프레임에 관절 각도가 40~120° 점프하는 구간이 있다 (middle_02_r 123°)",
    "프레임 0에서 중간 마디가 84~97° 굽은 채 시작 — 기본 굽힘 포함 여부 확인 필요",
  ], { x: rx4 + 0.24, y: BY + 0.74, w: cw3 - 0.24, h: 2.4, fontSize: 15, gap: 11 });

  const by4 = BY + 3.4;
  band(s, { x: M, y: by4, w: 10.6, h: 2.5 });
  txt(s, "측정 결과  —  일반 3곡 · 오른손 (타건 150 ms 이후)", { x: M + 0.44, y: by4 + 0.26, w: 9.7, h: 0.4,
    fontSize: 16, bold: true, color: H.SAGE_D, valign: "middle" });
  bullets(s, [
    { text: "손끝–건반 오차: 평균 0.45 cm, 최대 10.66 cm, 1 cm 이상 5.1%", color: H.INK },
    { text: "40회 안에 수렴하지 못한 프레임 60.7% — 남은 오차 중앙값 1.4 cm", color: H.RUST, bold: true },
    "관절 제한은 거의 항상 DIP 최대 굴곡·MCP 최대 신전에서 걸린다",
    "떨림 최대 39.1° — 매 프레임 관절을 0°로 초기화하고 다시 풀기 때문",
  ], { x: M + 0.46, y: by4 + 0.78, w: 9.66, h: 1.6, fontSize: 13.5, gap: 8 });

  photo(s, { path: CROP + "/lt_ik_ue5.png", x: M + 11.1, y: by4, w: W - 11.1, h: 2.5,
    cap: "A_IK_DebClai — UE5 AnimSequence (7,447프레임)" });

  s.addNotes("왼쪽이 된 것, 오른쪽이 아직 남은 것입니다.\n아래가 어제 측정한 값입니다. 손끝과 건반 사이 오차는 평균 0.45cm인데 최대값이 10.66cm입니다. 손이 닿지 않는 구간이 있다는 뜻입니다.\n수렴 실패 60.7%는 설명이 필요합니다. 허용 오차 0.01은 IK 내부 단위라 0.05cm 정도인데, 수렴하지 못한 풀이의 남은 오차 중앙값이 1.4cm입니다. 거의 다 왔다는 뜻이 아닙니다.\n관절 제한은 거의 항상 같은 두 곳, DIP 최대 굴곡과 MCP 최대 신전에서 걸립니다. 목표점이 손가락 도달 범위 끝에 놓인다는 신호입니다.\n떨림은 원인을 알고 있습니다. 매 프레임 관절을 0도로 초기화하고 다시 풀기 때문입니다.");
}

// ═══════════════════ 03 GPU 스키닝 ═══════════════════
pres.addSection({ title: SEC.gpu });
divider("4", "GPU 스키닝",
  "뼈를 따라 정점을 옮기는 것만으로는 피부가 늘어나고 접히는 모습이 나오지 않는다.\n표면이 얼마나 늘어났는지를 직접 계산해서 주름과 핏줄 같은 미세한 디테일을 만든다.",
  "이수민", SEC.gpu);

{
  const s = head("Chapter 4.", "왜 엔진 기본 스키닝으로는 안 되는가", SEC.gpu);

  const cw4 = (W - 1.0) / 2;
  sub(s, M, BY, "엔진 기본 — 정점을 옮기기만 한다", cw4, H.RUST);
  txt(s, "뼈 변환을 가중 평균해 정점 위치를 구한다. 표면이 얼마나 늘어났는지는 계산하지 않으므로, 주름이 생길 자리를 알 수 없다.",
    { x: M + 0.24, y: BY + 0.72, w: cw4 - 0.24, h: 1.0, fontSize: 15, color: H.INK2,
      valign: "top", lineSpacingMultiple: 1.45 });

  const rx5 = M + cw4 + 1.0;
  sub(s, rx5, BY, "커스텀 — 신장률을 직접 계산한다", cw4, H.SAGE);
  txt(s, "UMeshDeformer 를 상속해 정점 처리 단계에 끼어든다. 변의 길이 변화로 텐션을 구하고, 그 값으로 주름을 만든다.",
    { x: rx5 + 0.24, y: BY + 0.72, w: cw4 - 0.24, h: 1.0, fontSize: 15, color: H.INK2,
      valign: "top", lineSpacingMultiple: 1.45 });

  photo(s, { path: CROP + "/lt_wrinkle.png", x: 3.6, y: BY + 2.2, w: 12.8, h: 4.3, fit: "contain",
    cap: "왼쪽: 손을 편 상태  ·  오른쪽: 손가락을 굽힌 상태 — 마디마다 가로 주름이 생긴다" });

  s.addNotes("언리얼 기본 GPU 스키닝은 뼈 변환을 가중 평균해서 정점을 옮기기만 합니다. 표면이 얼마나 늘어났는지는 계산하지 않습니다.\n주름은 피부가 접히면서 생기는 것이라, 늘어남과 줄어듦을 알아야 만들 수 있습니다.\n그래서 UMeshDeformer를 상속해서 정점 처리 단계에 직접 끼어들었습니다.\n아래 사진이 결과입니다. 손가락을 굽히면 마디마다 가로 주름이 생깁니다.");
}

{
  const s = head("Chapter 4.", "6‑Pass 컴퓨트 셰이더 파이프라인", SEC.gpu);
  lead(s, "UMeshDeformer 를 상속해 정점 처리 단계에서 실행된다. 패스 하나가 컴퓨트 셰이더 하나다.");

  const passes = [
    ["1", "Deform", "DQS/LBS 혼합으로\n정점을 변형", H.BEIGE, H.SAGE_D],
    ["2", "Tension\nAccumulate", "변의 신장률을\natomic int 로 누적", H.SAGE_L, H.SAGE_D],
    ["3", "Tension\nResolve", "누적값을 정점 수로\n나눠 텐션 확정", H.SAGE_L, H.SAGE_D],
    ["4", "Detail\nDisplace", "텐션으로 주름·핏줄\n변위를 적용", H.SAGE_D, H.WHITE],
    ["5", "Normal\nAccumulate", "변위 후 면 노멀을\n정점에 누적", H.SAGE, H.WHITE],
    ["6", "Normal\nResolve", "정규화해 최종\n노멀을 기록", H.SAGE, H.WHITE],
  ];
  const d2 = 1.5, cw5 = (W - 0.46 * 5) / 6, py = BY + 0.9;
  passes.forEach((p, i) => {
    const x = M + i * (cw5 + 0.46);
    circle(s, { x: x + cw5 / 2 - d2 / 2, y: py, d: d2, text: p[0], fs: 22,
      fill: p[3], color: p[4] });
    if (i < 5) hline(s, py + d2 / 2, x + cw5 / 2 + d2 / 2 + 0.12, 0.46 + cw5 - d2 - 0.24, H.LINE, 1.2);
    txt(s, p[1], { x, y: py + d2 + 0.24, w: cw5, h: 0.84, fontSize: 14.5, bold: true,
      color: H.INK, align: "center", valign: "top", lineSpacingMultiple: 1.2 });
    txt(s, p[2], { x, y: py + d2 + 1.12, w: cw5, h: 0.92, fontSize: 12, color: H.INK2,
      align: "center", valign: "top", lineSpacingMultiple: 1.35 });
  });

  band(s, { y: 8.5, h: 1.76 });
  txt(s, "왜 누적과 확정을 나누는가", { x: M + 0.44, y: 8.72, w: 8, h: 0.4, fontSize: 16,
    bold: true, color: H.SAGE_D, valign: "middle" });
  txt(s, "한 정점은 여러 삼각형에 속한다. 각 삼각형이 계산한 값을 한 정점에 모으려면 먼저 전부 더해 두고(Accumulate), 모든 삼각형이 끝난 뒤에 나눠야(Resolve) 한다. GPU는 순서를 보장하지 않으므로 atomic 연산으로 더하고 패스를 분리한다. 텐션과 노멀이 같은 이유로 각각 두 패스씩 쓴다.",
    { x: M + 0.44, y: 9.18, w: W - 0.88, h: 0.92, fontSize: 14, color: H.INK2,
      valign: "top", lineSpacingMultiple: 1.45 });

  s.addNotes("컴퓨트 셰이더 여섯 개가 순서대로 돕니다.\n1번이 정점을 옮기고, 2·3번이 텐션을 구하고, 4번이 그 텐션으로 주름을 만들고, 5·6번이 노멀을 다시 계산합니다.\n누적과 확정을 나눈 이유는 아래에 적어 뒀습니다. 한 정점이 여러 삼각형에 속해 있어서, 전부 더한 뒤에 나눠야 하기 때문입니다. GPU는 실행 순서를 보장하지 않아서 atomic으로 더합니다.");
}

{
  const s = head("Chapter 4.", "텐션을 네 채널로 나눠 쓴다", SEC.gpu);
  lead(s, "정점 컬러 네 채널에 서로 다른 변형 성분을 담아, 주름의 방향과 세기를 따로 제어한다.");

  const chans = [
    ["R", "신장", "표면이 늘어난 정도", H.SAGE_D],
    ["G", "뼈 방향 압축", "뼈를 따라 줄어든 정도", H.SAGE],
    ["B", "가로 압축", "뼈와 직각으로 줄어든 정도", H.SAGE_L],
    ["A", "릴랙스 슬랙", "굽혔다 편 뒤 남는 이력", H.BEIGE2],
  ];
  const cw6 = (W - 0.6 * 3) / 4;
  chans.forEach((c, i) => {
    const x = M + i * (cw6 + 0.6), y = BY + 0.72;
    hline(s, y, x, cw6, c[3], 2.4);
    txt(s, c[0], { x, y: y + 0.22, w: cw6, h: 0.86, fontSize: 46, bold: true,
      color: c[3] === H.BEIGE2 ? H.LINE : c[3], valign: "middle" });
    txt(s, c[1], { x, y: y + 1.14, w: cw6, h: 0.42, fontSize: 17, bold: true,
      color: H.INK, valign: "middle" });
    txt(s, c[2], { x, y: y + 1.6, w: cw6, h: 0.5, fontSize: 13, color: H.INK2, valign: "top" });
  });

  const y2 = BY + 3.3;
  const cw7 = (W - 1.0) / 2;
  sub(s, M, y2, "부피 보존을 추정값에서 실제 계산으로", cw7, H.SAGE);
  txt(s, [
    { text: "1학기   ", options: { fontSize: 14, color: H.LINE, fontFace: F } },
    { text: "1/λ²", options: { fontSize: 17, bold: true, color: H.LINE, fontFace: FM } },
    { text: "   한 방향 신장률만 보고 어림잡은 값", options: { fontSize: 14, color: H.LINE, breakLine: true, fontFace: F } },
    { text: "2학기   ", options: { fontSize: 14, color: H.INK, fontFace: F } },
    { text: "1/J", options: { fontSize: 17, bold: true, color: H.SAGE_D, fontFace: FM } },
    { text: "   변형 텐서 ", options: { fontSize: 14, color: H.INK, fontFace: F } },
    { text: "C = FᵀF", options: { fontSize: 16, bold: true, color: H.SAGE_D, fontFace: FM } },
    { text: " 에서 구한 실제 부피비", options: { fontSize: 14, color: H.INK, fontFace: F } },
  ], { x: M + 0.24, y: y2 + 0.74, w: cw7 - 0.24, h: 1.3, isTextBox: true, margin: 0,
    valign: "top", lineSpacingMultiple: 1.6 });
  txt(s, "세 방향의 변형을 모두 반영하므로, 비틀리는 자세에서 부피가 어긋나지 않는다.",
    { x: M + 0.24, y: y2 + 2.0, w: cw7 - 0.24, h: 0.7, fontSize: 14, color: H.INK2,
      valign: "top", lineSpacingMultiple: 1.4 });

  const rx6 = M + cw7 + 1.0;
  sub(s, rx6, y2, "이력 주름 — 폈다 놓아도 바로 사라지지 않는다", cw7, H.SAGE);
  bullets(s, [
    "RelaxState 를 프레임 간 유지해, 굽혔다 편 직후에도 주름이 남는다",
    "감쇠 시간 약 0.9초 — 실제 피부의 거동에 맞춘 값",
    { text: "정지 화면으로는 확인할 수 없다 — 시퀀서 렌더로 검증해야 한다", color: H.SAGE_D, bold: true },
  ], { x: rx6 + 0.24, y: y2 + 0.74, w: cw7 - 0.24, h: 2.0, fontSize: 14.5, gap: 11 });

  s.addNotes("텐션을 하나의 값으로 두지 않고 네 채널로 나눴습니다. 늘어남과 줄어듦, 그리고 뼈 방향인지 가로 방향인지를 구분해야 주름 방향이 제대로 나옵니다.\n부피 보존은 1학기에 한 방향 신장률로 어림잡았는데, 2학기에 변형 텐서에서 실제 부피비를 구하도록 바꿨습니다.\n오른쪽 이력 주름은 발표 때 주의할 점입니다. 0.9초면 사라져서 정지 화면으로는 안 보입니다.");
}

{
  const s = head("Chapter 4.", "손등과 손바닥은 반대로 동작한다", SEC.gpu);

  band(s, { y: BY - 0.1, h: 1.14 });
  txt(s, "손가락을 굽히면 손등 피부는 당겨지고 손바닥 피부는 접힌다. 같은 관절인데 주름이 생기는 조건이 정반대라, 셰이더에서 이중 게이트로 분기한다.",
    { x: M + 0.44, y: BY + 0.12, w: W - 0.88, h: 0.7, fontSize: 16.5, color: H.INK,
      valign: "middle", lineSpacingMultiple: 1.4 });

  const cw8 = (W - 1.0) / 2;
  const y3 = BY + 1.5;
  [["손등", "굽힐수록 늘어난다", "신장(R) 채널이 올라가는 쪽에서 주름을 만든다. 마디 위로 가로줄이 선다.", H.SAGE],
   ["손바닥", "굽힐수록 접힌다", "압축(G·B) 채널이 올라가는 쪽에서 주름을 만든다. 손바닥 접힘선은 Phase 4 에서 해결했다.", H.SAGE_D],
  ].forEach((t, i) => {
    const x = M + i * (cw8 + 1.0);
    hline(s, y3, x, cw8, t[3], 2.4);
    txt(s, t[0], { x, y: y3 + 0.22, w: cw8, h: 0.6, fontSize: 28, bold: true, color: t[3], valign: "middle" });
    txt(s, t[1], { x, y: y3 + 0.88, w: cw8, h: 0.42, fontSize: 17, bold: true, color: H.INK, valign: "middle" });
    txt(s, t[2], { x, y: y3 + 1.36, w: cw8, h: 0.9, fontSize: 14, color: H.INK2,
      valign: "top", lineSpacingMultiple: 1.4 });
  });

  const fw5 = (W - 0.66 * 3) / 4;
  [
    { v: "Phase 7", l: "진행 단계\n손바닥선 · 부피 보존 완료", c: H.SAGE_D, r: H.SAGE_D, vs: 30 },
    { v: "74,186", l: "고밀도 메시 정점 수\nSKM_MH_Hand_R_Dense", c: H.INK, r: H.LINE, vs: 32 },
    { v: "3.7~4.6", u: "ms", l: "전체 GPU 시간 — 아직 한가하다\n패스별 분해는 미측정", c: H.INK, r: H.LINE, vs: 30 },
    { v: "0.9", u: "초", l: "이력 주름 감쇠 시간", c: H.INK, r: H.LINE },
  ].forEach((d3, i) => {
    figure(s, { x: M + i * (fw5 + 0.66), y: y3 + 3.0, w: fw5, value: d3.v, unit: d3.u,
      color: d3.c, label: d3.l, rule: d3.r, vs: d3.vs || 36 });
  });

  s.addNotes("이게 구현에서 가장 까다로웠던 부분입니다.\n같은 관절인데 손등은 늘어나고 손바닥은 접힙니다. 주름이 생기는 조건이 정반대라, 한쪽 기준으로 짜면 반대쪽이 틀립니다. 셰이더에서 이중으로 분기합니다.\n현재 Phase 7까지 왔고, 1차 때 한계로 적었던 손바닥 접힘선은 해결했습니다.\nGPU는 4ms 정도로 아직 여유가 있습니다. 병목은 다른 데 있는데 마지막에 말씀드립니다.");
}

// ═══════════════════ 04 Chaos Flesh ═══════════════════
pres.addSection({ title: SEC.flesh });
divider("5", "Chaos Flesh",
  "주름 같은 미세한 디테일이 아니라, 살이 눌려 옆으로 밀려나는 거시적인 변형을 다룬다.\n손 내부를 사면체로 채우고 뼈에 묶어 물리로 계산한다.",
  "곽경민", SEC.flesh);

{
  const s = head("Chapter 5.", "IsoStuffing은 손가락을 만들지 못했다", SEC.flesh);
  lead(s, "손 메시 내부를 사면체로 채우는 단계에서, 엔진 기본 생성기가 MetaHuman 손의 가는 손가락을 처리하지 못했다.");

  const iw = 5.1, iy = BY + 0.6, ih = 3.5;
  photo(s, { path: CROP + "/tet_iso.png", x: M, y: iy, w: iw, h: ih, fit: "contain",
    cap: "IsoStuffing — 손가락이 통째로 날아가고 손바닥만 덩어리로 남는다" });
  photo(s, { path: CROP + "/tet_wild.png", x: M + iw + 0.6, y: iy, w: iw, h: ih, fit: "contain",
    cap: "TetWild — 손가락 다섯 개가 모두 살아 있다 · 사면체 정점 5,688" });

  const rx7 = M + (iw + 0.6) * 2;
  const rw2 = W - (iw + 0.6) * 2;
  [
    ["왜 실패했나", "격자를 채워 넣는 방식이라, 격자 간격보다 가는 부분은 아예 비어 버린다"],
    ["TetWild 로 전환", "표면을 먼저 정리한 뒤 내부를 채우므로 가는 손가락도 살아남는다"],
    ["Dataflow 도 통합", "1학기에 그래프 2개로 나뉘어 있던 것을 단일 그래프로 합쳤다"],
  ].forEach((r, i) => {
    const y = iy + i * 1.3;
    hline(s, y, rx7, rw2, H.SAGE_L, 2.0);
    txt(s, r[0], { x: rx7, y: y + 0.18, w: rw2, h: 0.42, fontSize: 16.5, bold: true,
      color: H.SAGE_D, valign: "middle" });
    txt(s, r[1], { x: rx7, y: y + 0.64, w: rw2, h: 0.58, fontSize: 13.5, color: H.INK2,
      valign: "top", lineSpacingMultiple: 1.4 });
  });

  s.addNotes("사면체를 만드는 단계에서 막혔던 이야기입니다.\n엔진 기본 생성기인 IsoStuffing은 격자를 채우는 방식이라, 격자 간격보다 가는 부분은 비어 버립니다. MetaHuman 손가락이 딱 그 경우였습니다. 왼쪽 사진처럼 손가락이 날아가고 손바닥 덩어리만 남았습니다.\nTetWild로 바꾸니 손가락 다섯 개가 모두 살아났습니다. 사면체 정점은 5,688개입니다.\n아래가 통합한 Dataflow 그래프입니다.");

  photo(s, { path: CROP + "/flesh_dataflow.png", x: M, y: 8.3, w: W, h: 1.34, fit: "contain" });
}

{
  const s = head("Chapter 5.", "Flesh 결과를 GPU 스키닝에 섞는다", SEC.flesh);

  band(s, { y: BY - 0.1, h: 1.26, fill: H.SAGE_L });
  txt(s, [
    { text: "2차 성과 — ", options: { bold: true, color: H.SAGE_D, fontSize: 16.5, fontFace: F } },
    { text: "Flesh가 계산한 표면 위치를 GPU 스키닝 직후에 섞는 어댑터를 구현하고 검증까지 마쳤다.",
      options: { color: H.INK, fontSize: 16.5, breakLine: true, fontFace: F } },
    { text: "컴퓨트 셰이더에서  lerp(스키닝 결과, Flesh 결과, Blend)  로 합성한다.",
      options: { color: H.INK2, fontSize: 13.5, fontFace: F } },
  ], { x: M + 0.44, y: BY + 0.1, w: W - 0.88, h: 0.86, valign: "middle", lineSpacingMultiple: 1.45 });

  const ly2 = BY + 1.96, lw2 = 12.3;
  txt(s, "연결 검증 결과", { x: M, y: ly2 - 0.5, w: 6, h: 0.4, fontSize: 15, bold: true,
    color: H.SAGE_D, valign: "middle" });
  [
    ["정점 수 일치", "Flesh 반환 74,186 = 렌더 메시 74,186", H.SAGE_D],
    ["정점 순서 · 좌표계", "휴지 자세 편차 평균 0.27 cm · 최대 0.35 cm → 이음매 매핑 불필요", H.SAGE_D],
    ["렌더 패스 실행", "301 프레임 중 301회 실행, 실패 0", H.SAGE_D],
    ["좌표 변환", "불필요 — 변환 전후 편차가 같다", H.SAGE_D],
    ["성능", "바인딩 1회 생성 + 정점 계산 병렬화로 46 ms → 7 ms", H.SAGE],
  ].forEach((r, i) => {
    const y = ly2 + i * 0.94;
    hline(s, y, M, lw2);
    circle(s, { x: M + 0.1, y: y + 0.36, d: 0.2, fill: r[2] });
    txt(s, r[0], { x: M + 0.5, y: y + 0.1, w: 3.3, h: 0.74, fontSize: 15.5, bold: true,
      color: H.INK, valign: "middle" });
    txt(s, r[1], { x: M + 4.0, y: y + 0.1, w: lw2 - 4.0, h: 0.74, fontSize: 14.5,
      color: H.INK2, valign: "middle" });
  });
  hline(s, ly2 + 5 * 0.94, M, lw2);

  photo(s, { path: CROP + "/lt_flesh_hand.png", x: M + lw2 + 0.7, y: ly2 - 0.1,
    w: W - lw2 - 0.7, h: 4.2, cap: "Flesh + GPU 스키닝 통합 결과 (L_FleshTest)\n정지 자세에서 Flesh 쪽 표면이 평균 0.3 cm 더 두껍다" });

  s.addNotes("1차 발표에서 '어댑터 미구현'이라고 말씀드렸던 부분입니다. 2차에서 구현하고 검증까지 마쳤습니다.\n정점 수가 정확히 일치하고, 좌표계도 같아서 별도 매핑이 필요 없었습니다. 편차가 평균 0.27cm인데 이건 Flesh 표면이 원래 조금 더 두꺼워서 나는 차이입니다.\n처음 구현했을 때 46ms가 걸렸는데, 바인딩을 매 프레임 만들던 것을 한 번만 만들도록 고치고 정점 계산을 병렬화해서 7ms로 줄였습니다.\n오른쪽이 실제로 합쳐진 결과입니다.");
}

{
  const s = head("Chapter 5.", "현재 확보한 것과 남은 문제", SEC.flesh);

  const fw6 = (W - 0.66 * 3) / 4;
  [
    { v: "5,688", l: "사면체 정점 수 (TetWild)", c: H.INK, r: H.LINE, vs: 34 },
    { v: "0", l: "바인딩 에러 (뼈 22개 전부 성공)", c: H.SAGE_D, r: H.SAGE_D },
    { v: "74,186", l: "렌더 메시 바인딩 정점\n고아 · 재부모 정점 0", c: H.SAGE_D, r: H.SAGE_D, vs: 32 },
    { v: "0", l: "시뮬레이션 발산 · 폭발 프레임", c: H.SAGE_D, r: H.SAGE_D },
  ].forEach((d3, i) => {
    figure(s, { x: M + i * (fw6 + 0.66), y: BY, w: fw6, value: d3.v,
      color: d3.c, label: d3.l, rule: d3.r, vs: d3.vs || 36 });
  });

  txt(s, "알려진 한계", { x: M, y: BY + 2.6, w: 6, h: 0.4, fontSize: 15, bold: true,
    color: H.RUST, valign: "middle" });
  rows(s, [
    { left: "손끝 어긋남", right: "두 가지가 섞여 있었다. 정지에 가까울 때는 0.2~0.7 cm 로 두께 차(0.3 cm)와 같은 크기 — 형태 차이다. 손끝이 10 cm/s 이상이면 1.3~4.6 cm 이고 거의 전부 이동 반대 방향 — 약 한 프레임 지연이다." },
    { left: "안쪽 살 지글거림", right: "주먹을 쥘 때 가장 안쪽 살이 떨린다. 자기충돌(self‑collision)을 설정하지 않은 것이 원인으로 보인다." },
    { left: "부위별 바인딩", right: "손가락을 묶으면 정지 어긋남은 30~40% 줄지만(약지 0.6 → 0.4 cm) 움직일 때 지연은 그대로다. 손가락 사면체가 손바닥을 따라 끌려가는 것으로 보인다." },
    { left: "Blend 값별 비교 미실시", right: "0 / 0.5 / 1 로 나눠 살 눌림과 부피 이득을 정량 비교해야 Flesh를 쓰는 근거를 수치로 댈 수 있다." },
  ], { x: M, y: BY + 3.14, w: W, rh: 1.22, lw: 4.4, lfs: 16.5, rfs: 14 });

  s.addNotes("위는 확보한 수치, 아래는 남은 문제입니다.\n손끝 어긋남이 가장 오래 붙잡고 있던 문제입니다. 처음에는 지연이라고 봤다가, 정지 상태에서도 남아서 형태 차이로 추정했습니다. 어제 로그로 재 보니 둘 다였습니다.\n거의 멈춰 있을 때는 0.2에서 0.7센티인데, 이건 Flesh 표면이 원래 0.3센티 더 두꺼운 것과 같은 크기라 형태 차이입니다. 손끝이 초당 10센티 넘게 움직이면 1.3에서 4.6센티로 커지고, 어긋나는 방향이 거의 전부 이동 반대쪽입니다. 즉 Flesh가 한 프레임쯤 뒤처집니다.\n손가락을 바인딩에서 풀어도 지연은 그대로였습니다. 손가락 안 사면체가 단단해서 손바닥을 따라 끌려가는 것으로 보고 있습니다.\nBlend 값별 비교는 Flesh를 쓸 이유를 수치로 대는 작업이라 꼭 해야 합니다.");
}

// ═══════════════════ 05 통합 ═══════════════════
pres.addSection({ title: SEC.wrap });
divider("6", "통합과 마무리",
  "모듈을 각자 돌릴 때는 보이지 않다가, 붙여서 데이터를 따라가 보니 드러난 것들.\n2차 발표에서 가장 말씀드리고 싶은 부분이다.",
  "정근녕", SEC.wrap);

{
  const s = head("Chapter 6.", "같은 수치를 각 파트가 따로 들고 있었다", SEC.wrap);
  lead(s, "건반 치수는 네 모듈이 모두 참조한다. 그런데 각자 자기 코드에 값을 적어 두고 있었고, 서로 달랐다.");

  const probs = [
    ["흑건 앞뒤 위치", "+3.0 cm", "55.0 mm", "건반 형상에서 도출될 수 없는 값이었다.\n백건 길이 150 − 흑건 길이 95 로 재정의."],
    ["흑건 상면 높이", "정의 없음", "12.5 mm", "IK가 반드시 참조해야 하는 값인데\n명세에 항목 자체가 없었다."],
    ["백건 폭", "23.4 mm", "164.0 / 7", "반올림한 값을 쓰면 88건반 끝에서\n1.5 mm 오차가 누적된다."],
  ];
  const pw = (W - 0.9 * 2) / 3, py2 = BY + 0.82;
  probs.forEach((p, i) => {
    const x = M + i * (pw + 0.9);
    hline(s, py2, x, pw, H.SAGE_L, 2.4);
    txt(s, p[0], { x, y: py2 + 0.2, w: pw, h: 0.46, fontSize: 18, bold: true,
      color: H.SAGE_D, valign: "middle" });
    txt(s, p[1], { x, y: py2 + 0.84, w: pw, h: 0.5, fontSize: 19, color: H.LINE,
      fontFace: FM, valign: "middle" });
    s.addShape(pres.ShapeType.downArrow, { x: x + 0.18, y: py2 + 1.42, w: 0.18, h: 0.36,
      fill: { color: H.SAGE }, line: { type: "none" }, objectName: on("dn") });
    txt(s, p[2], { x, y: py2 + 1.86, w: pw, h: 0.52, fontSize: 20, bold: true,
      color: H.SAGE_D, fontFace: FM, valign: "middle" });
    txt(s, p[3], { x, y: py2 + 2.46, w: pw, h: 0.92, fontSize: 13, color: H.INK2,
      valign: "top", lineSpacingMultiple: 1.4 });
  });

  band(s, { y: 8.6, h: 1.66 });
  txt(s, [
    { text: "shared_constants.py", options: { bold: true, color: H.SAGE_D, fontSize: 18, fontFace: FM } },
    { text: "   단일 출처로 통합", options: { bold: true, color: H.INK, fontSize: 18, breakLine: true, fontFace: F } },
    { text: "건반 치수 · 손가락 간 최대 폭 · 손목 ROM · 본 이름 · 프레임 레이트 · 해제 시점 규약을 한 파일에 모았다. 각 파트는 이 파일에서 읽어 쓴다. 값이 바뀌면 한 군데만 고치면 되고, 서로 다른 값을 들고 있을 수가 없다.",
      options: { color: H.INK2, fontSize: 14, fontFace: F } },
  ], { x: M + 0.44, y: 8.84, w: W - 0.88, h: 1.2, isTextBox: true, margin: 0,
    valign: "top", lineSpacingMultiple: 1.5 });

  s.addNotes("건반 치수는 네 모듈이 다 쓰는 값인데, 각자 자기 코드에 적어 두고 있었습니다.\n가운데 것이 특히 문제였습니다. 흑건 윗면 높이는 IK가 반드시 알아야 하는 값인데 명세에 항목 자체가 없었습니다. 각자 알아서 가정하고 있었던 겁니다.\n오른쪽은 작아 보이지만, 23.4로 반올림하면 88건반 끝에서 1.5mm가 어긋납니다.\n지금은 shared_constants.py 한 파일에서 읽어 씁니다.");
}

{
  const s = head("Chapter 6.", "계산해서 넘겼는데, 받는 쪽에서 쓰지 않고 있었다", SEC.wrap);
  lead(s, "모듈을 각자 돌릴 때는 드러나지 않고, 붙여서 데이터를 끝까지 따라가 봐야 보이는 종류의 문제다.");

  const dgw = 11.1, dgh = 4.97, dgy = BY + 0.5;
  s.addImage({ path: CROP + "/lt_wrist_roll.png", x: M, y: dgy, w: dgw, h: dgh,
    objectName: "diag_wrist" });

  const rx8 = M + dgw + 0.7;
  const rw3 = W - dgw - 0.7;
  sub(s, rx8, dgy + 0.1, "무슨 값인가", rw3, H.SAGE);
  bullets(s, [
    "엄지가 흑건을 누르면 +12°, 소지가 흑건을 누르면 −12° 가 손 전체에 붙는다 (왼손은 부호 반대)",
    { text: "엄지가 흑건을 누르는 1,758음 중 1,507음에 롤 값이 들어 있다", color: H.INK, bold: true },
    "IK 는 운지 CSV 를 13번째 열부터 읽어 두 열을 건너뛴다. 손목은 FK 로만 움직인다",
    { text: "반영 실험: 요+롤 적용 시 엄지–흑건 오차 1.54 → 1.10 cm", color: H.SAGE_D, bold: true },
    { text: "롤 단독은 효과 없음 — 손목 위치·엄지 도달 범위와 함께 조정해야 한다", color: H.RUST },
  ], { x: rx8 + 0.24, y: dgy + 0.86, w: rw3 - 0.24, h: 4.1, fontSize: 13.5, gap: 11 });

  const cy3 = dgy + dgh + 0.36;
  band(s, { y: cy3, h: 1.3, fill: H.SAGE_L });
  txt(s, [
    { text: "엄지로 흑건을 누르려면 손목을 비틀어야 한다. ", options: { fontSize: 16.5, color: H.INK, fontFace: F } },
    { text: "엔진은 그 각도를 넘겼지만, IK 는 손목 회전을 다루지 않는다.",
      options: { fontSize: 16.5, bold: true, color: H.SAGE_D, breakLine: true, fontFace: F } },
    { text: "IK 영상에서 보이는 \"손목이 돌아간\" 자세의 유력한 원인이며, 운지법 쪽 결함이 아니다.",
      options: { fontSize: 13.5, color: H.INK2, fontFace: F } },
  ], { x: M + 0.44, y: cy3 + 0.2, w: W - 0.88, h: 0.9, isTextBox: true, margin: 0,
    valign: "middle", lineSpacingMultiple: 1.45 });

  s.addNotes("2차에서 가장 말씀드리고 싶은 내용입니다.\n왼쪽이 운지법 엔진이 내보낸 손목 롤 값 분포입니다. 21곡 21,912음 중 5,415음에 ±12도가 들어 있습니다. 엄지나 소지가 검은 건반을 누르면 손목을 비틀어야 하기 때문입니다.\n오른쪽이 IK가 기록한 wrist.csv입니다. 전부 0입니다.\nIK는 손목을 위치만 보간하고 회전은 다루지 않습니다. 인계 규격서에도 '손목 회전은 IK 쪽 향후 과제'로 적혀 있습니다. 즉 모르고 있던 게 아니라, 알고 미뤄 둔 공백인데 아직 닫히지 않은 겁니다.\n아까 IK 영상에서 손목이 돌아가 보였던 것의 유력한 원인입니다. 운지법 쪽 결함은 아닙니다.\n다만 한 가지는 조심해서 말씀드려야 합니다. 어제 IK 쪽에서 반영 실험을 해 봤는데, 롤만 돌려서는 나아지지 않았습니다. 요까지 같이 넣어야 엄지-흑건 오차가 1.54에서 1.10센티로 줄었습니다. 그래서 롤만 반영하면 해결된다고 말씀드릴 수는 없고, 손목 위치와 엄지 도달 범위를 함께 봐야 합니다.\n인터페이스를 정의하고 파일을 주고받는 것만으로는 부족하고, 받는 쪽이 그 값을 실제로 다루는지까지 확인해야 한다는 걸 배웠습니다.");
}

{
  const s = head("Chapter 6.", "병목은 어댑터가 아니었다", SEC.wrap);
  lead(s, "목표는 60 FPS(16.7 ms)인데 현재 약 20 FPS다. 어떤 구성을 끄고 켜며 측정해 원인을 좁혔다.");

  const ty2 = BY + 0.96, rh2 = 1.06;
  const cols = [["구성", 5.2], ["Frame", 3.1], ["Game (CPU)", 3.4], ["GPU", 3.1], ["FPS", 3.12]];
  let cx0 = M;
  const colXs = cols.map((c) => { const v = cx0; cx0 += c[1]; return v; });
  cols.forEach((c, i) => {
    txt(s, c[0], { x: colXs[i], y: ty2 - 0.46, w: c[1], h: 0.38, fontSize: 14, bold: true,
      color: H.SAGE_D, charSpacing: 0.8, align: i === 0 ? "left" : "center", valign: "middle" });
  });
  [
    ["어댑터 끔", "44.5 ms", "44.3 ms", "4.6 ms", "약 22", H.INK2, false],
    ["어댑터 켬 (최적화 전)", "91 ms", "—", "—", "약 11", H.RUST, false],
    ["어댑터 켬 (최적화 후)", "약 51 ms", "약 51 ms", "약 3.7 ms", "약 20", H.SAGE_D, true],
  ].forEach((r, i) => {
    const y = ty2 + i * rh2;
    hline(s, y, M, W, r[6] ? H.SAGE : H.LINE, r[6] ? 1.6 : 0.75);
    txt(s, r[0], { x: colXs[0], y: y + 0.1, w: cols[0][1] - 0.3, h: rh2 - 0.2, fontSize: 16,
      bold: r[6], color: H.INK, valign: "middle" });
    for (let k = 1; k <= 4; k++) {
      txt(s, r[k], { x: colXs[k], y: y + 0.1, w: cols[k][1], h: rh2 - 0.2, fontSize: 16,
        bold: k === 4, color: k === 4 ? r[5] : (k === 3 ? H.SAGE_D : H.INK2),
        align: "center", valign: "middle" });
    }
  });
  hline(s, ty2 + 3 * rh2, M, W);

  const fy = ty2 + 3 * rh2 + 0.5;
  const cw9 = (W - 1.0) / 2;
  sub(s, M, fy, "읽어 낸 것", cw9, H.SAGE);
  bullets(s, [
    "어댑터를 아예 꺼도 44.5 ms — 어댑터는 병목이 아니다",
    "GPU는 3.7~4.6 ms로 한가하고, 게임 스레드가 붙잡고 있다",
    "60 FPS로 가려면 기본 비용 44 ms를 약 1/3로 줄여야 한다",
  ], { x: M + 0.24, y: fy + 0.72, w: cw9 - 0.24, h: 1.9, fontSize: 14.5, gap: 10 });

  const rx9 = M + cw9 + 1.0;
  sub(s, rx9, fy, "아직 분리하지 못한 것", cw9, H.LINE);
  bullets(s, [
    "44 ms가 Flesh 시뮬레이션인지, 두 손(342본 × 2)의 애니메이션 평가인지, 에디터 PIE 오버헤드인지",
    "stat game 으로는 컴포넌트 틱 세부가 보이지 않는다 → Flesh 액터 / 디포머 / Standalone 순으로 끄며 측정",
  ], { x: rx9 + 0.24, y: fy + 0.72, w: cw9 - 0.24, h: 1.9, fontSize: 14.5, gap: 10 });

  s.addNotes("성능 이야기입니다. 목표는 60 FPS인데 현재 20 FPS입니다.\n표를 보시면 어댑터를 아예 꺼도 44.5ms가 나옵니다. 즉 어댑터가 병목이 아닙니다.\nGPU는 4ms 안쪽으로 한가하고, 게임 스레드가 붙잡고 있습니다.\n그 44ms가 Flesh 시뮬레이션인지, 두 손 684본의 애니메이션 평가인지, 아니면 에디터 PIE 오버헤드인지는 아직 분리하지 못했습니다. 하나씩 꺼 보며 좁힐 예정입니다.");
}

{
  const s = head("Chapter 6.", "남은 과제", SEC.wrap);
  lead(s, "우선순위 순이다. 1번과 2번은 앞에서 말씀드린 두 가지 발견에 대한 후속이다.");

  const tasks = [
    ["1", "손목 각도(yaw · roll)를 IK 에 반영", "한승현 · 정근녕", true],
    ["2", "통합 프레임 비용 — 게임 스레드 44 ms 원인 분리", "곽경민 · 이수민", true],
    ["3", "GPU 스키닝 패스별 성능 측정", "이수민", false],
    ["4", "Flesh 부위별 바인딩 · Blend 값별 비교", "곽경민", false],
    ["5", "엔드‑투‑엔드 데모 (MIDI → 최종 렌더)", "전체", false],
    ["6", "손 크기 프리셋 · 피아노 트랙 자동 선별 · 04_Main", "정근녕", false],
  ];
  const trh = 1.06, ty3 = BY + 0.9;
  tasks.forEach((t, i) => {
    const y = ty3 + i * trh;
    hline(s, y, M, W, t[3] ? H.SAGE : H.LINE, t[3] ? 1.6 : 0.75);
    circle(s, { x: M + 0.06, y: y + trh / 2 - 0.27, d: 0.54, text: t[0], fs: 16,
      fill: t[3] ? H.SAGE_D : H.BEIGE, color: t[3] ? H.WHITE : H.SAGE_D });
    txt(s, t[1], { x: M + 0.92, y: y + 0.1, w: 12.6, h: trh - 0.2, fontSize: 17,
      bold: t[3], color: H.INK, valign: "middle" });
    txt(s, t[2], { x: M + 13.8, y: y + 0.1, w: W - 13.8, h: trh - 0.2, fontSize: 14,
      color: H.INK2, align: "right", valign: "middle" });
  });
  hline(s, ty3 + tasks.length * trh, M, W);

  s.addNotes("우선순위 순입니다.\n1번과 2번이 급합니다. 손목 각도는 아까 말씀드린 유실 건이고, 2번은 방금 본 성능 문제입니다.\n5번 엔드투엔드 데모가 학기 최종 목표입니다. MIDI 파일 하나를 넣으면 최종 렌더까지 나오는 것을 보여 드리려고 합니다.");
}

{
  const s = pres.addSlide({ masterName: "PLAIN", sectionTitle: SEC.wrap });
  txt(s, "마무리", { x: M, y: 1.6, w: 8, h: 0.44, fontSize: 18, color: H.SAGE_L,
    charSpacing: 1, valign: "middle" });
  vbar(s, M, 2.16, 1.6, H.SAGE_L);
  txt(s, "모듈이 각자 도는 단계에서\n서로 붙는 단계로 넘어왔다", { x: M + 0.34, y: 2.12, w: 13, h: 1.7,
    fontSize: 42, bold: true, color: H.SAGE, valign: "middle", lineSpacingMultiple: 1.3 });

  const pts = [
    ["운지법", "제약을 거는 단위를 시간 기준으로 바꿔 21곡에서 위반 0건"],
    ["IK", "양손 10손가락이 실제 비율 건반을 치고, 달빛 전곡을 애니메이션으로 변환"],
    ["GPU 스키닝", "6‑Pass 정점 파이프라인으로 주름과 부피 보존을 구현"],
    ["Chaos Flesh", "TetWild 사면체 + 렌더 메시 바인딩, GPU 연결 어댑터까지 완료"],
    ["통합", "인터페이스 A · B · C 에 실제 데이터가 흐르고, 공유 상수로 수치를 일원화"],
  ];
  const lw3 = 13.0;
  pts.forEach((p, i) => {
    const y = 4.4 + i * 0.94;
    hline(s, y, M, lw3);
    txt(s, p[0], { x: M, y: y + 0.1, w: 2.8, h: 0.74, fontSize: 15.5, bold: true,
      color: H.SAGE_D, valign: "middle" });
    txt(s, p[1], { x: M + 3.0, y: y + 0.1, w: lw3 - 3.0, h: 0.74, fontSize: 14.5,
      color: H.INK2, valign: "middle" });
  });
  hline(s, 4.4 + pts.length * 0.94, M, lw3);

  band(s, { x: M + lw3 + 0.8, y: 4.4, w: W - lw3 - 0.8, h: 3.3 });
  txt(s, "남은 기간의 목표", { x: M + lw3 + 1.14, y: 4.72, w: W - lw3 - 1.48, h: 0.4,
    fontSize: 14, bold: true, color: H.SAGE_D, valign: "middle" });
  txt(s, "손목 각도 반영\n프레임 비용 개선\n엔드‑투‑엔드 데모", { x: M + lw3 + 1.14, y: 5.3, w: W - lw3 - 1.48,
    h: 2.0, fontSize: 18, bold: true, color: H.INK, valign: "top", lineSpacingMultiple: 1.75 });

  txt(s, "감사합니다", { x: M, y: 9.02, w: 8, h: 0.56, fontSize: 24, bold: true,
    color: H.SAGE, valign: "middle" });
  txt(s, "PIANO HAND SIMULATOR", { x: 0, y: 9.72, w: 20, h: 1.3, fontSize: 52, bold: true,
    color: H.BEIGE, align: "center", valign: "middle", charSpacing: 3 });

  s.addNotes("정리하겠습니다.\n2차의 핵심은 각 모듈이 독립 동작에서 실제 구현 단계에 도달했고, 인터페이스 세 군데에 실제 데이터가 흐르기 시작했다는 점입니다.\n붙여 보니 손목 각도 유실과 성능 병목 같은 문제가 드러났는데, 이건 붙이지 않았으면 끝까지 몰랐을 종류입니다.\n남은 기간에는 그 문제들을 고치고 엔드투엔드 데모까지 가는 것이 목표입니다.\n감사합니다.");
}

// ───────────────────────── 저장 ─────────────────────────
const OUT = process.argv[2] || "deck2.pptx";
pres.writeFile({ fileName: OUT }).then(async () => {
  if (process.argv[3]) {
    const { applyTheme } = require(process.argv[3]);
    await applyTheme(OUT, THEME);
  }
  console.log("생성 완료:", OUT);
}).catch((e) => { console.error("실패:", e); process.exit(1); });
