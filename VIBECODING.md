# PGU 해외법인 교육비 인보이스 포털 — 바이브코딩 인수인계

다른 모델/에이전트가 이 저장소에서 바로 이어서 작업할 수 있도록, 제품 맥락·하드 제약·아키텍처·최근 변경·함정을 한 파일에 모았습니다.

- **프로젝트 경로:** `C:\Users\junge\OneDrive\Desktop\새 폴더\인보이스_ver.2`
- **앱 이름:** POSCO Group University 해외법인 교육비 인보이스 포털
- **스택:** Flask 3 + SQLAlchemy 2 + Jinja2 + reportlab (PDF) + python-pptx/pypdfium2 (PPT)
- **로컬 DB:** SQLite `instance/pgu_invoices.db` (로컬은 `DATABASE_URL`이 있어도 SQLite. Render에서만 Postgres)
- **문서 작성일:** 2026-11-16 (대화 세션 기준 마지막 인수인계)

---

## 1. 이 파일로 무엇을 하는가

사용자는 Cursor에서 한국어로 화면을 가리키며 기능을 고칩니다. 에이전트는 코드를 직접 수정하고, Flask를 재시작하며, 가능하면 브라우저로 확인합니다.

다음 채팅을 열면:

1. 이 파일과 `config.py`, `app.py`, `models.py`를 먼저 읽는다.
2. **§3 하드 제약**을 어기지 않는다.
3. `use_reloader=False` 이므로 **코드 변경 후 Flask 프로세스를 직접 재시작**한다.
4. 커밋/푸시/Render 배포는 사용자가 말하기 전에는 하지 않는다.

---

## 2. 로컬 실행 / 접속 링크

### 서버 기동

```powershell
cd "C:\Users\junge\OneDrive\Desktop\새 폴더\인보이스_ver.2"
py -3 app.py
```

엔트리: `app.py` 하단

```python
app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
```

- 포트 **5000**, 모든 인터페이스 바인딩.
- **리로더 없음.** 템플릿은 대체로 바로 반영되지만 `app.py` / `i18n.py` / PDF 생성 코드는 재시작해야 한다.
- 예전 Flask가 떠 있으면 새 라우트가 안 잡힌다. `app.py`를 쓰는 python 프로세스를 전부 종료한 뒤 **하나만** 띄운다.
- Windows에서 프로세스 종료 코드 `4294967295`는 `taskkill`/`Stop-Process`로 개발 서버를 죽인 것으로, 앱 버그가 아니다.

### 접속 URL

| 구분 | URL |
|------|-----|
| 이 PC | http://127.0.0.1:5000 |
| 같은 네트워크 (오프라인/사내) | http://192.168.0.103:5000 (이 PC IPv4, 바뀔 수 있음) |

랜 IP는 네트워크에 따라 바뀐다. 예전 값은 `http://192.168.225.29:5000` 이었다.

Render 주소 `https://invoice2-icp0.onrender.com` 은 `config.py`의 `PORTAL_URL` 기본값이다. **배포는 사용자 요청 없이는 하지 않는다.** 로컬 작업의 정본은 이 폴더의 Flask다.

### 접속이 안 될 때 (2026-11-16 재발)

두 가지가 겹쳤다.

1. **Flask가 꺼져 있음.** `use_reloader=False`라 예전 프로세스를 죽이면 서버가 남지 않는다. `127.0.0.1:5000` 연결 거부.
2. **Windows 사용자 환경에 `DATABASE_URL`이 Render Postgres로 남아 있으면**, 예전 `config.py`는 로컬도 그 DB에 붙었다. Render DB SSL이 끊기면 `create_app()`에서 바로 죽음:

   `connection to server at "...singapore-postgres.render.com" ... SSL connection has been closed unexpectedly`

현재 `config.py`의 `resolve_database_uri()`는 **`RENDER` 환경변수가 없을 때 무조건 로컬 SQLite** (`instance/pgu_invoices.db`)를 쓴다. Render 배포에서만 `DATABASE_URL`을 쓴다. SQLite↔Postgres 데이터 마이그레이션은 하지 않는다.

조치:

1. `app.py`를 실행 중인 python이 있는지 확인.
2. 없으면 `py -3 app.py`로 기동. 기동 직후 콘솔에 `Running on http://127.0.0.1:5000`가 나와야 한다.
3. Postgres traceback이 나오면 `RENDER`가 로컬에 켜져 있는지 확인하고, 로컬에서는 꺼 둔다.
4. 포트 충돌이면 기존 프로세스만 종료 후 다시 기동.

### 로그인 (코드에 있는 기본값, `.env`가 우선)

- 관리자: `config.py`의 `ADMIN_USERNAME` / `ADMIN_PASSWORD`
- 법인 초기 비밀번호: `INITIAL_SUBSIDIARY_PASSWORD`
- **비밀번호·SMTP 앱 비밀번호·`.env` 내용을 채팅에 붙여 넣거나 커밋하지 말 것.**

---

## 3. 하드 제약 (사용자/세션에서 반복된 규칙)

이 규칙을 어기면 실데이터·운영 메일이 망가진다.

| 하지 말 것 | 이유 |
|------------|------|
| 사용자가 말하기 전 `git commit` / `push` / Render 배포 | 명시적으로만 |
| SQLite → Postgres 자동 마이그레이션 | 금지 |
| DB 스키마 변경 (새 컬럼/테이블) 무단 | 승인 후에만. 기존 `create_all` + 가벼운 ALTER는 `app.py`에 이미 있음 |
| 인보이스/이력 데이터 삭제·초기화 | 금지 |
| 빈 칸을 추측해서 채우기 | 금지 |
| `.env` 비밀값 노출 | 금지 |
| 실제 법인에 테스트 메일 발송 | 진단/수정 시에만, 테스트는 `MAIL_FROM` 쪽 |
| `02IN04` / Delhi / Pune을 한 법인으로 합치기 | **별개 엔티티로 유지** |
| 직인 파일 `instance/pgu_stamp.png` 삭제 | 실물 직인. 없으면 PDF에 공란 |
| 신규 반기 생성 UI 부활 | 사용자가 삭제함 (2026-10-22) |

허용되는 가벼운 ALTER는 `app.py` `create_app()` 안의 기존 컬럼 추가 루프다. **새 스키마를 추가하지 말고** 가능하면 기존 컬럼/JSON/텍스트 필드를 쓴다.

---

## 4. 제품이 하는 일

포스코그룹대(인재창조원, PGU)가 **해외법인 교육비**를 반기 단위로 청구한다.

1. 관리자가 **교육과정**을 반기에 등록하고 학습자 명단(법인코드, 이름, 선택 이메일)을 넣는다.
2. **인보이스 일괄생성:** 법인코드별로 초안 인보이스를 만든다. 같은 연도·반기·법인은 하나의 인보이스로 묶인다.
3. 달러 금액 = **원화 ÷ 환율**. VAT는 비과세지만 **화면/PDF에서 VAT 칸은 빼 둔 상태**.
4. 발행 → 법인 담당자 메일(PDF, 옵션 PPT) → 법인 포털에서 확인(acknowledge) → 입금 처리.
5. 관리자는 반기 전체를 **하나의 PDF 또는 PPT로 일괄 다운로드**, 또는 HQ 담당자에게 통합본 발송.

역할:

- `admin` — 전체 메뉴 (교육, 인보이스, 해외법인, 본사 정보, 로그)
- `subsidiary` — 자기 법인 인보이스 수신/확인, 법인 정보 일부 수정

반기:

- H1 = 1–6월, H2 = 7–12월
- 기간은 쿼리스트링이 아니라 URL: `/trainings/<year>/h<half>`, `/invoices/<year>/h<half>`
- 교육과정·학습자·인보이스는 그 반기 안에서만 관리

환율:

- 수동 입력. 서울외국환중개 조회 링크만 제공 (스크래핑 금지, SMBS 정책)
- 링크: http://www.smbs.biz/ExRate/TodayExRate.jsp

메일:

- Gmail SMTP (`smtp.gmail.com` 587 STARTTLS, 실패 시 465 SSL)
- HQ 사본 수신: `instance/hq_settings.json`의 `HQ_COPY_EMAIL` (현재 `mileg0410@poscohrd.com` 등, 파일 값을 따름)
- 큰 PPT는 Gmail ~25MB / 타임아웃. **10건 초과 또는 PDF가 크면 메일에서 PPT를 건너뛰고 PDF만** 보내도록 되어 있음. 전체 반기 PPT는 **일괄 다운로드**가 정석.

---

## 5. 디렉터리 / 핵심 파일

```
인보이스_ver.2/
  app.py                 # Flask 앱, 거의 모든 라우트
  config.py              # 경로, DB URI, 메일/은행 기본값
  models.py              # User, Subsidiary, Training, Invoice, InvoiceItem, AuditLog
  i18n.py                # ko/en 문자열
  pdf_invoice.py         # reportlab A4 인보이스
  ppt_invoice.py         # PDF 페이지 → PPTX
  mailer.py              # 본문 HTML, 수신자 To/Cc
  smtp_mail.py           # 실제 SMTP 전송
  corporation_master.py  # 법인 매칭, JSON 임포트, 이메일 파싱
  entity_types.py        # 해외법인 유형
  regions.py             # 권역
  periods.py             # instance/periods.json (선언된 반기, UI 생성은 삭제됨)
  hq_settings.py         # instance/hq_settings.json → Config 오버라이드
  seed.py                # 빈 DB일 때만 시드. 가짜 빨간 직인 그리지 않음
  portal_corporations.json
  templates/             # Jinja
  static/css/style.css
  instance/              # gitignore. DB, 직인, HQ 설정, periods.json
  generated_pdfs/        # gitignore
  .env                   # gitignore. SMTP 비밀
```

중요 템플릿:

| 화면 | 파일 |
|------|------|
| 반기 허브 | `templates/periods/hub.html` |
| 교육 목록/일괄생성 | `templates/trainings/list.html` |
| 교육 등록 | `templates/trainings/form.html` |
| 인보이스 목록 | `templates/invoices/list.html` |
| 인보이스 상세 | `templates/invoices/detail.html` |
| 인보이스 작성 | `templates/invoices/form.html` |
| 메일 작성 | `templates/invoices/compose.html` |
| 해외법인 | `templates/subsidiaries/list.html`, `form.html` |
| 본사 정보 | `templates/settings.html` |

---

## 6. 데이터 모델 요약

**Subsidiary (해외법인)**  
`code` (예: `02VN01`), `name_ko`(정식명), `name_en`(인보이스 공식명), `country`/`country_en`, `emails`(담당자), `hr_emails`(인사주재원).  
`code`는 unique constraint를 풀어 중복 코드를 허용하고 `needs_review`로 표시할 수 있음. **Delhi/Pune/02IN04는 합치지 말 것.**

**Training**  
반기는 `start_date`로 추론. `learners`는 텍스트, 한 줄에 `법인코드, 이름, 이메일`. `learner_count`는 총원. `session_no`는 회차(등록 폼에는 남김, **목록 회차 필터는 삭제됨**).

**Invoice**  
`year` + `half` + `seq` → 번호 `PGU-YYYY-0H-NNN`. 상태: `draft` → `issued` → `acknowledged` → `paid`.  
`billed_name` / `billed_address` / `billed_code`는 발행 시점 스냅샷.  
외화: `amount_fx = amount_krw / exchange_rate`. `vat_rate` 컬럼은 남아 있으나 UI/PDF VAT 표시는 제거.

**InvoiceItem**  
과정별 행. `learner_roster`는 JSON `[{"name","email"}, ...]`. 상세 명단은 여기서 재구성.

**AuditLog**  
관리자 메일 발송 포함 (`log_invoice_mail` 등).

기간 격리는 URL의 year/half. 교육 시작일이 그 반기 밖이면 저장 거부 (`training_wrong_half`).

---

## 7. 최근 세션에서 한 일 (2026-10-22 ~ 10-26, 이 채팅)

시간순. 코드는 이미 반영된 상태로 가정한다.

### PDF / 출력

- `TOTAL AMOUNT DUE (NET)` 글자와 USD 금액이 겹치지 않게 금액 열 너비 확보 (`pdf_invoice.py`).
- 환율 옆 **VAT / Exempt 0%** 메타 칸 삭제. 헤더는 CURRENCY · FX RATE · RATE DATE 3칸 (`meta_w = content_w / 3`).
- 총액 위 **VAT (Exempt) USD 0.00** 줄 삭제. TOTAL만 남김.
- 하단 법률 문구에 “VAT 0%, exempt” 문장은 아직 있음. 사용자가 지우라고 하기 전엔 유지.
- 송금계좌(`show_bank=False`)를 빼도 **직인 위치는 아래쪽 그대로** (`bank_block_h` 예약).
- 직인 파일이 없으면 **빨간 원 플레이스홀더 금지**, 공란. `seed.ensure_stamp`도 가짜 인을 그리지 않음.

### 다운로드 / 메일

- 관리자만 인보이스 **PDF + PPT** 다운로드.
- 반기 전체 일괄: `GET /invoices/<year>/h<half>/bundle?fmt=pdf|ppt&bank=`
- 송금계좌 포함 여부: 상세/목록/담당자 일괄 발송/HQ 일괄.
- HQ 담당자 일괄 발송은 **현재 반기만**. `year`/`half` hidden + URL. `status=draft` 제외. 여러 반기를 한 번에 보내면 `hq_bulk_need_period`.
- PPT를 메일에 붙일 때 인보이스가 많으면 SMTP 타임아웃 → 10건 초과 또는 PDF 큼 → PPT 스킵, PDF만 재시도.
- 관리자가 법인에 보낸 메일도 감사 로그에 남김.

### 교육과정

- 학습자 명단 옆 **해외법인 코드표 엑셀** `GET /trainings/entity-codes` → `overseas_entity_codes.xlsx`  
  열: 국가, 해외법인 정식명(`name_ko`), 해외법인 코드. 관리자 전용.
- 교육 목록 **인보이스 일괄생성** 아래에 **환율 조회** 버튼 → SMBS 오늘의 환율 (새 탭).
- **신규 반기 생성** 카드/POST `/periods` **삭제**. `save_declared_period`는 `periods.py`에만 남음. 반기 카드는 교육/인보이스 연도로 자동 나열.
- 교육 목록 **회차 필터** 삭제. 발행여부(usage) 필터는 유지. 등록 폼의 회차 입력은 유지.

### 인보이스 상세 학습자 명단 (`#learner-roster`)

표시 열: **# / 과정명 / 법인(정식명+코드) / 이름**.  
이메일 열 삭제(데이터는 item JSON에 남을 수 있음).  
과정명은 가능하면 `Training.title`(한국어), 법인은 `name_ko` 우선.

### 인보이스 상세 부가세

상세 카드 `dl.kv`의 **부가세 / Exempt** 행 삭제 (`templates/invoices/detail.html`).  
작성 폼 `form.html`과 대시보드 `vat_note`는 아직 있을 수 있음. 사용자가 상세만 지우라고 함.

### 개인정보

- 주재원(`hr_emails`) 입력란은 유지, 저장된 값은 이전에 비움.
- 2026-10-26: **담당자 이메일 `Subsidiary.emails` 전량 공란** (당시 76법인 중 35건). `portal_corporations.json`의 `contact_emails`도 `[]`. 입력란은 유지. 메일 발송 시 To가 비면 스킵/수동 입력.

---

## 8. 주요 라우트 (관리자)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/trainings`, `/invoices` | 반기 허브 |
| GET/POST | `/trainings/<y>/h<h>/new` | 교육 등록 |
| GET | `/trainings/entity-codes` | 법인 코드표 xlsx |
| POST | `/trainings/bulk-invoices` | 교육 → 법인별 초안 |
| GET | `/invoices/<y>/h<h>` | 반기 인보이스 목록 |
| GET | `/invoices/<y>/h<h>/bundle` | 일괄 PDF/PPT |
| GET | `/invoices/<id>` | 상세 + 명단 |
| GET | `/invoices/<id>/pdf`, `/ppt` | 단건 다운로드, `?bank=0\|1` |
| POST | `/invoices/hq-copy` | 담당자(HQ) 일괄 메일 |
| GET/POST | `/settings` | 본사 정보·직인·메일 템플릿 |

법인 사용자: 인보이스 수신, 확인, 프로필(주소/이메일 등).

---

## 9. 비즈니스 로직 포인트 (`app.py`)

- `money_fx(krw, rate)` — Decimal, 반올림 HALF_UP, 소수 2자리.
- `parse_person` / `parse_training_learners` — 줄에서 법인코드·이름·이메일 추출. 코드 정규식 대문자.
- `rebuild_pdf` — 다운로드/발송 시 PDF 재생성. `use_reloader=False`여도 생성 함수는 프로세스 메모리의 코드.
- `invoice_roster` — 상세 명단. 프로그램명, entity, entity_code, name, email(표시는 안 함).
- `parse_show_bank` / `parse_attach_formats` — 폼 플래그.
- HQ 일괄: 기간이 없거나 여러 반기면 거절. 초안 제외.

i18n: `i18n.py`의 `TRANSLATIONS["ko"|"en"]`. 키 추가 시 양쪽 다.

PDF: `pdf_invoice.py` `generate_invoice_pdf(invoice, path, show_bank=True)`.

---

## 10. UI에서 일부러 뺀 것 (되살리지 말 것, 사용자가 다시 시키기 전)

- PDF VAT 칸/줄
- 인보이스 상세 부가세 행
- 학습자 명단 이메일 열
- 신규 반기 생성 폼
- 교육 목록 회차 필터
- 직인 없을 때 빨간 원
- 담당자 이메일에 들어 있던 실주소 (필드는 빈 칸으로 유지)

---

## 11. 에이전트 작업 습관

1. 화면 DOM/스크린샷이 오면 해당 템플릿부터 고친다.
2. `app.py`는 한 파일에 라우트가 몰려 있다. 검색 후 최소 수정.
3. Flask를 재시작한 뒤 실제로 GET/클릭으로 확인. 예전 프로세스가 5000을 물고 있으면 새 코드가 안 나간다.
4. 메일 수정 시 실법인 주소로 보내지 않는다.
5. 엑셀/PDF 바이너리는 `generated_pdfs/`에 임시 생성 후 가능하면 지운다.
6. 커밋은 사용자 요청 시에만. 메시지 스타일은 히스토리가 `update` 남발이므로, 요청 시에는 **왜**를 한두 문장으로.
7. 브라우저 검증: 로그인 세션이 법인 계정으로 바뀌지 않았는지 메뉴를 보고 확인 (`인보이스 수신/확인`이면 법인 역할).

---

## 12. 알려진 이슈 / 미완

- **로컬 접속 불가:** Flask 미기동. §2.
- 담당자 이메일을 비워서 **법인 일괄 메일 To가 비어 있을 수 있음.** 발송 전 주소를 다시 넣거나 작성 화면에서 수동 To.
- `periods.py`의 `save_declared_period`는 호출부가 없음. 죽은 코드. 굳이 지우지 않아도 됨.
- 인보이스 **작성 폼**과 대시보드에 VAT 안내 문구가 남아 있을 수 있음.
- PDF 하단 영어 법적 고지에 VAT 0% 문구 잔존.
- Render 배포본은 로컬 최신과 다를 수 있음. 로컬이 정본.
- OneDrive 경로라 `git status`/`Get-NetTCPConnection`이 가끔 오래 걸린다.

---

## 13. 사용자 말투·기대

- 한국어, 짧은 확인. “제외해줘/삭제해줘/넣어줘”.
- 화면을 DOM Path로 지정하는 경우가 많음.
- 개인정보(이메일)는 필드만 남기고 값은 비우라는 식이 반복됨.
- 교육 등록 UX(코드표, 환율 링크)와 출력물 레이아웃에 민감.

다음에 비슷한 요청이 오면: **필드(입력란)를 지울지, 저장된 값만 지울지**를 기존 패턴에 맞춘다. 이메일·주재원은 “란은 남기고 값만 삭제”가 기본이었다.

---

## 14. 빠른 체크리스트 (새 에이전트 첫 턴)

- [ ] `py -3 app.py`가 5000에서 떠 있는가
- [ ] http://127.0.0.1:5000/login 이 열리는가
- [ ] 수정할 화면이 관리자인지 법인인지
- [ ] 스키마/메일/배포/커밋이 이번 요청에 포함되는가 (기본 아니오)
- [ ] VAT·반기생성·회차필터·명단 이메일을 되살리는 요청인가 (기본 아니오)

이 파일이 세션 요약과 충돌하면 **코드와 이 파일의 “뺀 것” 목록을 우선**하고, 사용자 최신 메시지를 그 다음으로 따른다.
