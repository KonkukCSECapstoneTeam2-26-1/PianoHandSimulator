"""Assemble the Phase 3 report page, inlining every figure as a data: URI."""
import base64, os

IMG = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'img')


def d(name):
    with open(os.path.join(IMG, name + '.jpg'), 'rb') as f:
        return 'data:image/jpeg;base64,' + base64.b64encode(f.read()).decode()


def fig(n, src, cap, alt, wide=True):
    return f'''<figure class="fig{' fig--wide' if wide else ''}">
  <img src="{src}" alt="{alt}">
  <figcaption><span class="fignum">Fig.{n}</span>{cap}</figcaption>
</figure>'''


def duo(n, a, b, la, lb, cap, alt):
    return f'''<figure class="fig fig--wide">
  <div class="duo">
    <div class="duo__cell"><img src="{a}" alt="{alt} — {la}"><span class="duo__tag">{la}</span></div>
    <div class="duo__cell"><img src="{b}" alt="{alt} — {lb}"><span class="duo__tag">{lb}</span></div>
  </div>
  <figcaption><span class="fignum">Fig.{n}</span>{cap}</figcaption>
</figure>'''


def trio(n, imgs, labels, cap, alt):
    cells = ''.join(
        f'<div class="duo__cell"><img src="{s}" alt="{alt} — {l}"><span class="duo__tag">{l}</span></div>'
        for s, l in zip(imgs, labels))
    return f'''<figure class="fig fig--wide">
  <div class="trio">{cells}</div>
  <figcaption><span class="fignum">Fig.{n}</span>{cap}</figcaption>
</figure>'''


HEAD = '''<title>PianoHand 피부 셰이딩 리포트</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans+KR:wght@300;400;500;600;700&display=swap">
<style>
:root{
  --bg:#e9ebee; --surface:#fbfcfd; --surface-2:#f1f3f5;
  --ink:#14181c; --ink-2:#39424b; --muted:#6b757e;
  --line:#ced4da; --line-soft:#dee2e6;
  --stretch:#c8402a; --compress:#2a5fbe; --rest:#8d949b;
  --accent:var(--stretch);
  --shadow:0 1px 2px rgba(15,22,30,.05), 0 8px 24px -16px rgba(15,22,30,.22);
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --bg:#121518; --surface:#191d22; --surface-2:#20252b;
    --ink:#e7ebee; --ink-2:#b6bec6; --muted:#8a949d;
    --line:#2d343b; --line-soft:#242a30;
    --stretch:#f0715a; --compress:#6d9bf0; --rest:#7f888f;
    --shadow:0 1px 2px rgba(0,0,0,.4), 0 10px 30px -18px rgba(0,0,0,.8);
  }
}
:root[data-theme="dark"]{
  --bg:#121518; --surface:#191d22; --surface-2:#20252b;
  --ink:#e7ebee; --ink-2:#b6bec6; --muted:#8a949d;
  --line:#2d343b; --line-soft:#242a30;
  --stretch:#f0715a; --compress:#6d9bf0; --rest:#7f888f;
  --shadow:0 1px 2px rgba(0,0,0,.4), 0 10px 30px -18px rgba(0,0,0,.8);
}

*{box-sizing:border-box}
body{
  margin:0; background:var(--bg); color:var(--ink);
  font-family:"IBM Plex Sans KR","Malgun Gothic",system-ui,-apple-system,sans-serif;
  font-weight:400; font-size:16px; line-height:1.75;
  -webkit-font-smoothing:antialiased;
}
.wrap{max-width:1180px; margin:0 auto; padding-inline:20px; padding-block:0 96px}
.col{max-width:720px; margin-inline:auto}

/* ---------- masthead ---------- */
.mast{padding-block:64px 40px; border-bottom:1px solid var(--line)}
.kicker{
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:11.5px; font-weight:500;
  letter-spacing:.16em; text-transform:uppercase; color:var(--muted); margin:0 0 18px
}
h1{
  font-size:clamp(30px,5.2vw,48px); line-height:1.16; font-weight:600; letter-spacing:-.022em;
  margin:0 0 16px; text-wrap:balance;
}
.dek{font-size:17.5px; line-height:1.7; color:var(--ink-2); margin:0; max-width:56ch; font-weight:300}
.meta{
  display:flex; flex-wrap:wrap; gap:8px 28px; margin-top:28px;
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:12px; color:var(--muted);
}
.meta b{color:var(--ink-2); font-weight:500}

/* ---------- sections ---------- */
section{padding-block:56px 0}
h2{
  font-size:13px; font-family:"IBM Plex Mono",ui-monospace,monospace; font-weight:600;
  letter-spacing:.14em; text-transform:uppercase; color:var(--accent);
  margin:0 0 6px; display:flex; align-items:baseline; gap:12px;
}
h2::after{content:""; flex:1; height:1px; background:var(--line-soft)}
h3{font-size:24px; font-weight:600; letter-spacing:-.016em; margin:0 0 18px; text-wrap:balance}
p{margin:0 0 18px; color:var(--ink-2)}
p strong{color:var(--ink); font-weight:600}
code{
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:.87em;
  background:var(--surface-2); border:1px solid var(--line-soft);
  border-radius:4px; padding:.1em .38em; color:var(--ink);
}

/* ---------- figures ---------- */
.fig{margin:36px 0 44px}
.fig--wide{max-width:1140px; margin-inline:auto}
.fig img{
  display:block; width:100%; max-width:100%; border-radius:3px;
  background:var(--surface-2);
}
.fig > img{box-shadow:var(--shadow)}
figcaption{
  margin-top:14px; font-size:13.5px; line-height:1.65; color:var(--muted);
  max-width:74ch;
}
.fignum{
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:11.5px; font-weight:600;
  letter-spacing:.08em; color:var(--ink-2); margin-right:10px;
}
.duo{display:grid; grid-template-columns:1fr 1fr; gap:10px}
.trio{display:grid; grid-template-columns:repeat(3,1fr); gap:10px}
.duo__cell{position:relative; box-shadow:var(--shadow); border-radius:3px; overflow:hidden}
.duo__tag{
  position:absolute; left:10px; top:10px;
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:11px; font-weight:500;
  letter-spacing:.04em; color:#fff; background:rgba(12,16,20,.72);
  padding:3px 8px; border-radius:3px; backdrop-filter:blur(3px);
}

/* ---------- legend ---------- */
.legend{
  display:flex; flex-wrap:wrap; gap:8px 22px; margin:0 0 18px;
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:12.5px; color:var(--ink-2);
}
.legend span{display:inline-flex; align-items:center; gap:8px}
.sw{width:22px; height:10px; border-radius:2px; border:1px solid rgba(0,0,0,.12)}

/* ---------- pipeline ---------- */
.pipe{list-style:none; margin:0 0 8px; padding:0; display:grid; gap:1px; background:var(--line-soft);
  border:1px solid var(--line-soft); border-radius:4px; overflow:hidden}
.pipe li{
  background:var(--surface); display:grid; grid-template-columns:auto 1fr auto;
  gap:16px; align-items:baseline; padding:13px 16px;
}
.pipe .n{
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:11.5px; font-weight:600;
  color:var(--accent); letter-spacing:.05em;
}
.pipe .what{font-size:14.5px; color:var(--ink)}
.pipe .what em{font-style:normal; color:var(--muted); font-size:13px}
.pipe .where{
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:11.5px; color:var(--muted);
  white-space:nowrap;
}

/* ---------- table ---------- */
.tablewrap{overflow-x:auto; border:1px solid var(--line-soft); border-radius:4px; background:var(--surface)}
table{border-collapse:collapse; width:100%; font-size:13.5px; min-width:520px}
th,td{text-align:left; padding:10px 16px; border-bottom:1px solid var(--line-soft)}
tbody tr:last-child td{border-bottom:0}
th{
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:11px; font-weight:600;
  letter-spacing:.1em; text-transform:uppercase; color:var(--muted); background:var(--surface-2);
}
td:first-child{font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:12.5px; color:var(--ink)}
td.num{font-family:"IBM Plex Mono",ui-monospace,monospace; font-variant-numeric:tabular-nums; color:var(--ink)}
td:last-child{color:var(--ink-2)}

/* ---------- callout ---------- */
.note{
  border-left:2px solid var(--accent); background:var(--surface);
  padding:16px 20px; margin:26px 0; border-radius:0 4px 4px 0; box-shadow:var(--shadow);
}
.note p:last-child{margin-bottom:0}
.note .lbl{
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:11px; font-weight:600;
  letter-spacing:.12em; text-transform:uppercase; color:var(--accent); display:block; margin-bottom:6px;
}

/* ---------- traps ---------- */
.traps{list-style:none; margin:0; padding:0; display:grid; gap:14px}
.traps li{
  display:grid; grid-template-columns:auto 1fr; gap:14px; align-items:start;
  padding-bottom:14px; border-bottom:1px solid var(--line-soft);
}
.traps li:last-child{border-bottom:0; padding-bottom:0}
.traps .n{
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:12px; font-weight:600;
  color:var(--muted); padding-top:2px;
}
.traps b{display:block; color:var(--ink); font-weight:600; margin-bottom:2px}
.traps span{color:var(--ink-2); font-size:14.5px; line-height:1.65}

footer{
  margin-top:72px; padding-top:22px; border-top:1px solid var(--line);
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:11.5px; color:var(--muted);
  display:flex; flex-wrap:wrap; gap:6px 24px;
}

@media (max-width:640px){
  body{font-size:15.5px}
  .mast{padding-block:44px 30px}
  section{padding-block:40px 0}
  .duo,.trio{grid-template-columns:1fr}
  .pipe li{grid-template-columns:auto 1fr; gap:12px}
  .pipe .where{grid-column:2; white-space:normal}
}
@media (prefers-reduced-motion:reduce){*{animation:none!important; transition:none!important}}
</style>'''


def body():
    F = {k: d(k) for k in [
        'skin_idle', 'skin_curl', 'skin_grasp', 'skin_close',
        'tension_idle', 'tension_grasp', 'tension_close',
        'clay_base', 'clay_dense', 'creaseonly', 'maskdebug',
        'map_wrinkle', 'map_detail', 'map_vein']}

    return f'''<div class="wrap">

<header class="mast col">
  <p class="kicker">PianoHandSimulator · Phase 3 결과 보고</p>
  <h1>텐션 구동 피부 셰이딩</h1>
  <p class="dek">MIDI 구동 피아노 손 시뮬레이터의 커스텀 GPU 스키닝 파이프라인에, 스킨 웨이트에서
  직접 뽑아낸 변형장으로 구동되는 주름·핏줄·부피 보존을 얹었다. 마스크도, 상용 에셋도 쓰지 않았다.</p>
  <div class="meta">
    <span><b>엔진</b> UE 5.6.1</span>
    <span><b>메시</b> SKM_MannyXR_right_Dense · 93,725 verts</span>
    <span><b>픽셀 셰이더</b> ~600 instr · 샘플러 4</span>
    <span><b>날짜</b> 2026-09-20</span>
  </div>
</header>

<section class="col">
  <h2>요약</h2>
  <h3>무엇이 되었나</h3>
  <p>엔진 스킨 캐시를 대체하는 컴퓨트 스키닝 위에, 정점별 <strong>엣지 신장률(strain)</strong>을 매 프레임
  계산해 그 값으로 지오메트리 변위와 셰이딩 디테일을 함께 구동한다. 손가락을 구부리면 압축이 생긴
  마디에 주름이 깊어지고, 펴면 얕아지되 <strong>사라지지는 않는다</strong> — 실제 손도 편 상태에서
  마디 주름이 남아 있기 때문이다.</p>
  <p>주름이 생기는 <strong>위치와 방향</strong>은 손으로 칠한 맵이 아니라 리그에서 구웠다. 가장 큰 두 스킨
  웨이트로 만든 <code>4·w₀·w₁</code> 은 강체부에서 0, 관절의 50/50 블렌드 선에서 1이 되므로, 관절이
  어디인지를 메시 스스로 알려준다.</p>
</section>

{fig(1, F['skin_close'], '최종 결과. 마디를 가로지르는 주름과 그 사이의 미세 피부 요철. 주름 방향은 본 축에서 유도되므로 손가락마다 자동으로 맞는다.', '쥔 손의 손등 클로즈업')}

<section class="col">
  <h2>파이프라인</h2>
  <h3>한 프레임에 일어나는 일</h3>
  <p>모두 같은 RDG 그래프 안에서 순서대로 디스패치되고, 결과는 엔진 GPU 스킨 passthrough 정점
  팩토리 버퍼에 직접 쓴다. 머티리얼은 그 위에 얹힌다.</p>
  <ol class="pipe">
    <li><span class="n">01</span><span class="what">선형 블렌드 스키닝 <em>— 정점당 본 4개</em></span><span class="where">Deformer.usf</span></li>
    <li><span class="n">02</span><span class="what">삼각형당 엣지 strain 누적 <em>— 고정소수점 atomic</em></span><span class="where">Tension.usf</span></li>
    <li><span class="n">03</span><span class="what">정점별 평균 → Vertex Color + strain 버퍼</span><span class="where">Tension.usf</span></li>
    <li><span class="n">04</span><span class="what">부피 보존 · 관절 크리즈 · 리플 변위</span><span class="where">Detail.usf</span></li>
    <li><span class="n">05</span><span class="what">변위 후 노멀 재계산 + 탄젠트 재직교화</span><span class="where">Detail.usf</span></li>
    <li><span class="n">06</span><span class="what">피부 표면 셰이딩 <em>— 3층 노멀 블렌드</em></span><span class="where">PianoHandSkin.ush</span></li>
  </ol>
  <p>05번이 빠지면 주름이 <em>보이지 않는다</em>. 정점을 밀어도 노멀이 그대로면 라이팅이 평면 그대로라서,
  실루엣만 살짝 울퉁불퉁해지고 만다.</p>
</section>

{trio(2, [F['skin_idle'], F['skin_curl'], F['skin_grasp']], ['Idle', 'IndexCurl', 'Grasp'],
      '같은 파라미터, 포즈만 교체. 편 손(왼쪽)에도 마디 주름이 남아 있고, 구부릴수록(오른쪽) 압축부에서 깊고 조밀해진다.',
      '세 가지 포즈의 피부 셰이딩')}

<section class="col">
  <h2>텐션 필드</h2>
  <h3>무엇이 주름을 움직이는가</h3>
  <p>모든 디테일의 입력은 정점별 strain 하나다. <code>|pᵢ−pⱼ| / |rᵢ−rⱼ| − 1</code> — 스키닝된 엣지 길이를
  레스트 길이와 비교한 값이고, 0이면 원래 길이, 양수면 늘어남, 음수면 눌림이다. CPU 인접 정보는
  필요 없다. 삼각형당 스레드 하나가 세 엣지를 돌면서 양 끝점에 atomic 으로 더하면 끝이다.</p>
  <div class="legend">
    <span><i class="sw" style="background:var(--stretch)"></i> R — 신장 (stretch)</span>
    <span><i class="sw" style="background:var(--compress)"></i> G — 압축 (compression)</span>
    <span><i class="sw" style="background:var(--rest)"></i> 회색 — 레스트</span>
  </div>
</section>

{duo(3, F['tension_idle'], F['tension_grasp'], 'Idle', 'Grasp',
     '텐션 디버그 머티리얼(M_PianoHandTension). 레스트 포즈는 거의 균일한 회색 — strain 이 0 이라는 뜻이고, 이게 기준선이 맞다는 증거다. 쥐면 접히는 마디 안쪽이 파랗게(압축), 바깥쪽 피부가 붉게(신장) 갈린다.',
     '텐션 디버그 뷰')}

{fig(4, F['tension_close'], '같은 뷰 클로즈업. 붉은 띠가 마디 바깥, 푸른 점이 접히는 안쪽에 정확히 맺힌다. 주름·핏줄·부피 항이 모두 이 그림 하나에서 갈라져 나온다.', '텐션 디버그 클로즈업')}

<section class="col">
  <h2>지오메트리 밀도</h2>
  <h3>Nanite 테셀레이션은 쓸 수 없다</h3>
  <p>설계서는 Nanite 테셀레이션을 전제했지만 이 파이프라인과는 <strong>구조적으로 호환되지 않는다</strong>.
  커스텀 스키닝은 GPU 스킨 passthrough 정점 팩토리 버퍼에 결과를 쓰는데, Nanite 메시는 그 팩토리를
  거쳐 그려지지 않는다. Nanite 를 켜는 순간 스키닝 전체가 우회된다.</p>
  <p>그래서 밀도는 에셋 단계에서 올렸다. GeometryScripting 의 PN 테셀레이션(level 3)은 실루엣을
  부드럽게 유지하면서 스킨 웨이트를 포함한 정점 속성을 보간하므로, 스켈레탈 메시에 그대로 쓸 수 있다.</p>
  <div class="tablewrap">
    <table>
      <thead><tr><th>메시</th><th>삼각형</th><th>정점 (렌더)</th><th>비고</th></tr></thead>
      <tbody>
        <tr><td>SKM_MannyXR_right</td><td class="num">11,462</td><td class="num">3,239</td><td>원본 (UE VR 템플릿)</td></tr>
        <tr><td>…_Dense</td><td class="num">183,392</td><td class="num">93,725</td><td>PN tess level 3, 스켈레톤·머티리얼 슬롯 동일</td></tr>
      </tbody>
    </table>
  </div>
</section>

{duo(5, F['clay_base'], F['clay_dense'], '3,239 verts', '93,725 verts',
     '무광 clay 셰이딩 — 기하 변위만 보이도록 했다. 원본(왼쪽)은 마디 주름이 정점 몇 개 폭에 뭉개져 사라지고, 테셀레이션 후(오른쪽)에는 컴퓨트 패스의 크리즈가 실제 굴곡으로 남는다.',
     '테셀레이션 전후 clay 비교')}

<section class="col">
  <h2>주름 맵</h2>
  <h3>리그에서 구운 집중도와 방향</h3>
  <p>정점 92k 에서도 주름 한 줄은 정점 몇 개 폭이다. 실제 피부 요철은 그보다 한 자릿수 미세하므로
  셰이딩 노멀로 간다. 문제는 <em>어디에</em>, <em>어느 방향으로</em> 그리느냐다.</p>
  <p>세 장을 구웠다. 둘은 타일링 텍스처(피부 미세 요철, 핏줄)이고, 한 장은 메시 UV 공간의
  집중도 맵이다. 집중도 맵의 R 채널은 관절 밴드에 마디별 가중치
  (PIP 1.15 / MCP 1.00 / DIP 0.90 / 중수골 0.50 / 손바닥·손목 0.35)를 곱한 값이고,
  G 채널은 관절 피벗에서 본 축을 따라 잰 <strong>부호 있는 거리</strong>(±3cm)다.</p>
</section>

{fig(6, F['map_wrinkle'], 'T_PH_WrinkleMask — 2048², 손이 차지하는 텍셀은 190,807개. 손가락 스트립마다 마디 위치에 밴드가 맺혀 있고, 그 안에서 채널이 램프를 이룬다. 이 램프가 주름 간격을 만든다.', '구워진 주름 집중도 맵')}

{duo(7, F['map_detail'], F['map_vein'], 'T_PH_SkinDetail_N', 'T_PH_Vein_N',
     '타일링 노멀 두 장. 노이즈 해시를 주기(period)로 mod 해서 이음매가 없다. 흔히 쓰는 sin·frac 해시는 wrap 하지 않아 경계가 그대로 보인다.',
     '타일링 노멀 텍스처')}

<section class="col">
  <div class="note">
    <span class="lbl">설계 판단</span>
    <p>처음에는 주름 <strong>각도</strong>를 이중각으로 굽고 셰이더에서 UV 를 그만큼 회전시켰다. 완전히 깨졌다.
    전역 좌표를 픽셀마다 다른 각도로 회전하면 각도 변화량에 UV 원점까지의 거리가 곱해져서, 각도가
    조금만 움직여도 선 필드가 노이즈로 부서진다.</p>
    <p>대신 <strong>본 축 좌표</strong>를 구우면 셰이더는 <code>sin(s · frequency)</code> 만 하면 된다. s 의 등고선이
    애초에 본에 수직이므로 주름이 손가락을 가로지르는 것은 구조적으로 보장되고, s 는 매끄러우니
    깨질 것이 없다. 부호 있는 값이라 관절을 지나도 연속이고, 주름이 관절을 중심으로 대칭으로 맺힌다.</p>
  </div>
</section>

{fig(8, F['maskdebug'], '집중도 맵을 메시 위에 그대로 출력한 디버그 뷰. 초록 밴드가 각 마디에 얹혀 있다 — 여기가 주름이 몰리는 곳이고, 손으로 칠한 것이 아니라 스킨 웨이트에서 나온 것이다.', '메시 위에 표시한 주름 집중도 맵')}

{duo(9, F['creaseonly'], F['skin_close'], '크리즈 층만', '+ 디테일·핏줄',
     '레이어 분리. 왼쪽은 맵이 구동하는 크리즈 층만, 오른쪽은 타일링 디테일 노멀과 핏줄까지 합친 최종본. 크리즈가 구조를 잡고 디테일이 표면을 채운다.',
     '레이어 분리 비교')}

<section class="col">
  <h2>셰이더 구성</h2>
  <h3>HLSL 소스로 분리</h3>
  <p>UE 머티리얼 셰이더는 HLSL 로 작성해 플랫폼별로 크로스컴파일된다 — GLSL 경로는 없다. 다만 코드를
  Custom 노드 안에 박아둘 이유도 없어서, 표면 모델 전체를
  <code>Shaders/Private/PianoHandSkin.ush</code> 로 빼고 Custom 노드는 <code>IncludeFilePaths</code> 로
  인클루드만 한다. 노드 본문은 <code>return PH_SkinNormal(…);</code> 한 줄이고, 그래프는 배선만 담당한다.</p>
  <div class="tablewrap">
    <table>
      <thead><tr><th>파라미터</th><th>기본값</th><th>역할</th></tr></thead>
      <tbody>
        <tr><td>CreaseFrequency</td><td class="num">1.5</td><td>cm 당 주름 수 (맵이 cm 단위라 그대로 물리 단위)</td></tr>
        <tr><td>CreaseRange</td><td class="num">3.0</td><td>맵 G 채널의 ± 범위(cm). 베이커의 <code>S_RANGE</code> 와 반드시 일치</td></tr>
        <tr><td>CreaseDepth</td><td class="num">0.055</td><td>크리즈 노멀 기울기</td></tr>
        <tr><td>WrinkleBase</td><td class="num">0.35</td><td>레스트에서 남는 주름량 — 편 손가락의 마디 주름</td></tr>
        <tr><td>CompressGain</td><td class="num">2.2</td><td>압축이 주름을 깊게 하는 속도</td></tr>
        <tr><td>MaskGain / MaskSharpness</td><td class="num">1.6 / 3.0</td><td>관절 밴드의 폭과 조임</td></tr>
        <tr><td>DetailTiling / Strength</td><td class="num">4.0 / 1.0</td><td>타일링 피부 요철</td></tr>
        <tr><td>VeinTiling / Strength</td><td class="num">4.0 / 1.0</td><td>핏줄 — 신장(R)으로 구동, 관절 밴드에서는 억제</td></tr>
      </tbody>
    </table>
  </div>
</section>

<section class="col">
  <h2>디버깅 기록</h2>
  <h3>이번에 밟은 지뢰</h3>
  <ol class="traps">
    <li><span class="n">01</span><span><b>BC5 노멀맵의 Z 는 복원해야 한다</b>
      <span><code>TC_Normalmap</code> 은 2채널만 저장하고 <code>(x, y, 0, 1)</code> 로 샘플된다. 파란 채널에서
      z 를 읽으면 −1 이 되어 노멀이 탄젠트 평면으로 무너지고, 모든 텍셀이 최대 경사가 되어 피부가
      군복 위장무늬처럼 보인다. <code>z = √(1 − x² − y²)</code>.</span></span></li>
    <li><span class="n">02</span><span><b><code>Tex.Sample</code> 은 쓸 수 없다</b>
      <span>암시적 미분 샘플링은 비균일 분기 안에서 정의되지 않고, 레이트레이싱 hit 셰이더에서는
      아예 불법이다 — 모든 UE 머티리얼이 그쪽으로도 컴파일된다.
      <code>Common.ush</code> 의 <code>Texture2DSample</code> 매크로가 해당 스테이지에서
      <code>SampleLevel</code> 로 대체해 준다.</span></span></li>
    <li><span class="n">03</span><span><b>베이크할 때 V 를 뒤집지 말 것</b>
      <span>UE 는 텍스처 좌상단이 UV 원점이고 V 가 아래로 자란다 — 이미 이미지 행 순서와 같다.
      뒤집으면 아틀라스 반대쪽에 구워지고, 머티리얼은 빈 텍셀을 읽어 맵이 균일한 단색으로 보인다.</span></span></li>
    <li><span class="n">04</span><span><b>LOD 스트리밍 가드</b>
      <span>아직 스트리밍 중인 LOD 로 디스패치하면 엔진 내부 정점 팩토리 배열(크기 0)을 인덱싱하며
      죽는다. <code>LodIndex ≥ max(CurrentFirstLODIdx, GetPendingFirstLODIdx(0))</code> 와
      <code>HaveValidDynamicData()</code> 검사로 막았다.</span></span></li>
  </ol>
</section>

<section class="col">
  <h2>남은 과제</h2>
  <h3>다음</h3>
  <p><strong>손바닥 접힘선.</strong> 생명선 같은 큰 손금은 관절 밴드에서 나오지 않는다. 별도 채널이나
  수작업 맵이 필요하다.</p>
  <p><strong>적응적 밀도.</strong> 테셀레이션도 베이크도 오프라인 1회성이다. 카메라 거리에 따라 밀도를
  조절하는 경로는 아직 없다.</p>
  <p><strong>UV 왜곡 보정.</strong> 머티리얼 디테일이 UV 공간이라 UV 가 늘어난 영역에서 요철 밀도가
  달라진다. 트라이플래너나 UV 면적 보정이 필요하다.</p>
  <p><strong>Phase 4.</strong> Chaos Flesh 시뮬레이션 결과(변형 표면·스트레인)를 레스트 대신 입력으로
  받는 어댑터.</p>
</section>

<footer class="col">
  <span>PianoHandSimulator · Phase 3</span>
  <span>Docs/CustomSkinning_Pipeline.md §1-F ~ §1-H</span>
  <span>2026-09-20</span>
</footer>

</div>'''


if __name__ == '__main__':
    here = os.path.dirname(os.path.abspath(__file__))
    content = HEAD + '\n' + body()
    # artifact form: no document skeleton, the publisher wraps it
    open(os.path.join(here, 'report_artifact.html'), 'w', encoding='utf-8').write(content)
    # standalone form for the repo
    standalone = ('<!doctype html>\n<html lang="ko">\n<head>\n<meta charset="utf-8">\n'
                  '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
                  + HEAD + '\n</head>\n<body>\n' + body() + '\n</body>\n</html>\n')
    open(os.path.join(here, 'PianoHand_Phase3_Report.html'), 'w', encoding='utf-8').write(standalone)
    for f in ('report_artifact.html', 'PianoHand_Phase3_Report.html'):
        print(f, os.path.getsize(os.path.join(here, f)) // 1024, 'KB')
