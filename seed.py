"""Master list of 62 POSCO overseas entities and demo seed data."""

from datetime import date

from werkzeug.security import generate_password_hash

from config import Config
from models import Subsidiary, Training, User

# code, region_ko, region_en, country_ko, country_en, name_ko, name_en, address_en
SUBSIDIARIES = [
    ("01US01", "아메리카", "Americas", "미국", "USA", "포스코아메리카", "POSCO America Corporation", "Two Gateway Center, 283-299 Market St, Newark, NJ 07102, USA"),
    ("01US02", "아메리카", "Americas", "미국", "USA", "포스코 AAPC", "POSCO AAPC LLC", "600 Grant Street, Suite 3100, Pittsburgh, PA 15219, USA"),
    ("01MX01", "아메리카", "Americas", "멕시코", "Mexico", "포스코멕시코", "POSCO Mexico S.A. de C.V.", "Av. de la Industria 500, Altamira, Tamaulipas 89600, Mexico"),
    ("01MX02", "아메리카", "Americas", "멕시코", "Mexico", "포스코 MPPC", "POSCO MPPC S.A. de C.V.", "Carretera Tampico-Mante Km 12.5, Altamira, Tamaulipas, Mexico"),
    ("01BR01", "아메리카", "Americas", "브라질", "Brazil", "포스코브라질", "POSCO Brasil Ltda.", "Av. Brigadeiro Faria Lima 3729, 8F, Sao Paulo, SP 04538-905, Brazil"),
    ("01AR01", "아메리카", "Americas", "아르헨티나", "Argentina", "포스코아르헨티나", "POSCO Argentina S.A.", "Av. del Libertador 498, Piso 15, C1001ABR Buenos Aires, Argentina"),
    ("01CA01", "아메리카", "Americas", "캐나다", "Canada", "포스코캐나다", "POSCO Canada Ltd.", "100 King Street West, Suite 5600, Toronto, ON M5X 1C9, Canada"),
    ("01PE01", "아메리카", "Americas", "페루", "Peru", "포스코페루", "POSCO Peru S.A.C.", "Av. Javier Prado Este 4200, San Borja, Lima 41, Peru"),
    ("01CL01", "아메리카", "Americas", "칠레", "Chile", "포스코칠레", "POSCO Chile Ltda.", "Av. Apoquindo 3721, Piso 14, Las Condes, Santiago, Chile"),
    ("02VN01", "동남아시아", "Southeast Asia", "베트남", "Vietnam", "포스코베트남", "POSCO Vietnam Co., Ltd.", "4th Floor, Vincom Center, 72 Le Thanh Ton, Dist. 1, Ho Chi Minh City, Vietnam"),
    ("02VN02", "동남아시아", "Southeast Asia", "베트남", "Vietnam", "포스코 SS-VINA", "POSCO SS-VINA Co., Ltd.", "Phu My 2 Industrial Park, Tan Thanh, Ba Ria-Vung Tau, Vietnam"),
    ("02VN03", "동남아시아", "Southeast Asia", "베트남", "Vietnam", "포스코 VST", "POSCO VST Co., Ltd.", "Pho Noi A Industrial Park, Hung Yen Province, Vietnam"),
    ("02ID01", "동남아시아", "Southeast Asia", "인도네시아", "Indonesia", "크라카타우포스코", "PT Krakatau POSCO", "Kawasan Industri Krakatau, Cilegon 42443, Banten, Indonesia"),
    ("02ID02", "동남아시아", "Southeast Asia", "인도네시아", "Indonesia", "포스코인도네시아 자카르타", "PT POSCO Indonesia Jakarta", "World Trade Center 3, Jl. Jend. Sudirman Kav. 29-31, Jakarta 12920, Indonesia"),
    ("02TH01", "동남아시아", "Southeast Asia", "태국", "Thailand", "포스코태국", "POSCO-Thailand Co., Ltd.", "Sathorn Square, 98 North Sathorn Rd, Silom, Bangrak, Bangkok 10500, Thailand"),
    ("02MY01", "동남아시아", "Southeast Asia", "말레이시아", "Malaysia", "포스코말레이시아", "POSCO-Malaysia Sdn. Bhd.", "Level 21, Menara IMC, 8 Jalan Sultan Ismail, 50250 Kuala Lumpur, Malaysia"),
    ("02MM01", "동남아시아", "Southeast Asia", "미얀마", "Myanmar", "포스코미얀마", "POSCO Myanmar Co., Ltd.", "Junction City Tower, 42nd St, Pabedan Township, Yangon, Myanmar"),
    ("02PH01", "동남아시아", "Southeast Asia", "필리핀", "Philippines", "포스코필리핀", "POSCO Philippines Corp.", "22F, GT Tower International, Ayala Avenue, Makati City 1226, Philippines"),
    ("02SG01", "동남아시아", "Southeast Asia", "싱가포르", "Singapore", "포스코싱가포르", "POSCO Singapore Pte. Ltd.", "8 Marina Boulevard, #11-02, Marina Bay Financial Centre, Singapore 018981"),
    ("02KH01", "동남아시아", "Southeast Asia", "캄보디아", "Cambodia", "포스코캄보디아", "POSCO Cambodia Co., Ltd.", "Exchange Square, Street 106, Sangkat Wat Phnom, Phnom Penh, Cambodia"),
    ("03CN01", "동북아시아", "Northeast Asia", "중국", "China", "포스코차이나홀딩스", "POSCO China Holding Co., Ltd.", "28F, China World Tower 3, 1 Jianguomenwai Ave, Beijing 100004, China"),
    ("03CN02", "동북아시아", "Northeast Asia", "중국", "China", "장가항포항불수강", "Zhangjiagang Pohang Stainless Steel Co., Ltd.", "Yangtze River International Metallurgical Park, Zhangjiagang, Jiangsu, China"),
    ("03CN03", "동북아시아", "Northeast Asia", "중국", "China", "청도포항불수강", "Qingdao Pohang Stainless Steel Co., Ltd.", "Qingdao Economic & Technological Development Zone, Shandong, China"),
    ("03CN04", "동북아시아", "Northeast Asia", "중국", "China", "광동포스코냉연", "Guangdong POSCO Cold-Rolled Steel Co., Ltd.", "Shunde District, Foshan, Guangdong 528300, China"),
    ("03CN05", "동북아시아", "Northeast Asia", "중국", "China", "대련포스코가공", "Dalian POSCO Steel Processing Co., Ltd.", "Dalian Development Area, Liaoning 116600, China"),
    ("03CN06", "동북아시아", "Northeast Asia", "중국", "China", "충칭포스코", "Chongqing POSCO Steel Co., Ltd.", "Jianqiao Industrial Park, Dadukou, Chongqing 400084, China"),
    ("03CN07", "동북아시아", "Northeast Asia", "중국", "China", "포스코상하이", "POSCO China Shanghai Office", "Shanghai World Financial Center, 100 Century Ave, Pudong, Shanghai 200120, China"),
    ("03CN08", "동북아시아", "Northeast Asia", "중국", "China", "포스코천진", "POSCO China Tianjin Office", "Tianjin World Financial Center, 2 Dagu North Rd, Heping, Tianjin, China"),
    ("03CN09", "동북아시아", "Northeast Asia", "중국", "China", "포스코무한", "POSCO China Wuhan Office", "Wuhan International Plaza, 188 Jiefang Ave, Jianghan, Wuhan, China"),
    ("03CN10", "동북아시아", "Northeast Asia", "중국", "China", "포스코광저우", "POSCO China Guangzhou Office", "Teemtower, 208 Tianhe Rd, Tianhe, Guangzhou 510620, China"),
    ("03CN11", "동북아시아", "Northeast Asia", "중국", "China", "포스코청두", "POSCO China Chengdu Office", "Shangri-La Centre, 9 Binjiang East Rd, Chengdu, Sichuan, China"),
    ("03CN12", "동북아시아", "Northeast Asia", "중국", "China", "포스코선양", "POSCO China Shenyang Office", "Forum 66, 1 Qingnian St, Shenhe, Shenyang, Liaoning, China"),
    ("03CN13", "동북아시아", "Northeast Asia", "중국", "China", "포스코쑤저우", "POSCO China Suzhou Processing Center", "Suzhou Industrial Park, 200 Xinglong St, Suzhou, Jiangsu, China"),
    ("03CN14", "동북아시아", "Northeast Asia", "중국", "China", "포스코닝보", "POSCO China Ningbo Office", "Ningbo International Shipping Service Center, Yinzhou, Ningbo, China"),
    ("03CN15", "동북아시아", "Northeast Asia", "중국", "China", "포스코-CSPC", "POSCO-CSPC Co., Ltd.", "Nansha Economic Zone, Guangzhou, Guangdong, China"),
    ("04IN01", "서남아시아", "Southwest Asia", "인도", "India", "포스코인도 푸네", "POSCO India Pune Processing Center Pvt. Ltd.", "Plot A-1, Chakan MIDC Phase II, Pune, Maharashtra 410501, India"),
    ("04IN02", "서남아시아", "Southwest Asia", "인도", "India", "포스코마하라슈트라", "POSCO Maharashtra Steel Pvt. Ltd.", "Vile Bhagad MIDC, Dist. Raigad, Maharashtra 402208, India"),
    ("04IN03", "서남아시아", "Southwest Asia", "인도", "India", "포스코인도 델리", "POSCO India Delhi Office", "DLF Cyber City, Building 8C, Gurugram, Haryana 122002, India"),
    ("04IN04", "서남아시아", "Southwest Asia", "인도", "India", "포스코인도 첸나이", "POSCO India Chennai Office", "Prestige Polygon, 471 Anna Salai, Teynampet, Chennai 600018, India"),
    ("04IN05", "서남아시아", "Southwest Asia", "인도", "India", "포스코인도 뭄바이", "POSCO India Mumbai Office", "One BKC, Bandra Kurla Complex, Mumbai 400051, India"),
    ("05PL01", "유럽", "Europe", "폴란드", "Poland", "포스코폴란드", "POSCO-Poland Sp. z o.o.", "ul. Prosta 32, 00-838 Warsaw, Poland"),
    ("05TR01", "유럽", "Europe", "튀르키예", "Turkiye", "포스코아산 TST", "POSCO Assan TST Metal Industry and Trade A.S.", "Dilovasi OSB, Kocaeli 41455, Turkiye"),
    ("05DE01", "유럽", "Europe", "독일", "Germany", "포스코독일", "POSCO Germany GmbH", "Koenigsallee 92A, 40212 Duesseldorf, Germany"),
    ("05GB01", "유럽", "Europe", "영국", "United Kingdom", "포스코영국", "POSCO UK Ltd.", "30 St Mary Axe, London EC3A 8BF, United Kingdom"),
    ("05IT01", "유럽", "Europe", "이탈리아", "Italy", "포스코이탈리아", "POSCO Italy S.r.l.", "Via della Moscova 13, 20121 Milan, Italy"),
    ("05ES01", "유럽", "Europe", "스페인", "Spain", "포스코스페인", "POSCO Spain S.L.", "Paseo de la Castellana 35, 28046 Madrid, Spain"),
    ("05FR01", "유럽", "Europe", "프랑스", "France", "포스코프랑스", "POSCO France SAS", "21 Boulevard Haussmann, 75009 Paris, France"),
    ("05NL01", "유럽", "Europe", "네덜란드", "Netherlands", "포스코네덜란드", "POSCO Netherlands B.V.", "Weena 505, 3013 AL Rotterdam, Netherlands"),
    ("05CZ01", "유럽", "Europe", "체코", "Czechia", "포스코체코", "POSCO Czech s.r.o.", "Na Prikope 23, 110 00 Prague 1, Czechia"),
    ("05HU01", "유럽", "Europe", "헝가리", "Hungary", "포스코헝가리", "POSCO Hungary Kft.", "Madach Imre ut 13-14, 1075 Budapest, Hungary"),
    ("06AE01", "서남아시아", "Southwest Asia", "UAE", "UAE", "포스코중동", "POSCO Middle East FZE", "JAFZA View 18, Sheikh Zayed Road, Dubai, United Arab Emirates"),
    ("06SA01", "서남아시아", "Southwest Asia", "사우디", "Saudi Arabia", "포스코사우디", "POSCO Saudi Arabia", "Kingdom Centre, King Fahd Rd, Riyadh 12214, Saudi Arabia"),
    ("06EG01", "서남아시아", "Southwest Asia", "이집트", "Egypt", "포스코이집트", "POSCO Egypt", "Nile City Towers, Corniche El Nil, Cairo, Egypt"),
    ("06ZA01", "서남아시아", "Southwest Asia", "남아공", "South Africa", "포스코남아프리카", "POSCO Southern Africa (Pty) Ltd.", "Sandton City Office Tower, Johannesburg 2196, South Africa"),
    ("06MA01", "서남아시아", "Southwest Asia", "모로코", "Morocco", "포스코모로코", "POSCO Morocco SARL", "Twin Center, Boulevard Zerktouni, Casablanca 20100, Morocco"),
    ("06KW01", "서남아시아", "Southwest Asia", "쿠웨이트", "Kuwait", "포스코쿠웨이트", "POSCO Kuwait", "Al Hamra Tower, Al Shuhada St, Kuwait City, Kuwait"),
    ("07JP01", "동북아시아", "Northeast Asia", "일본", "Japan", "포스코재팬 도쿄", "POSCO Japan Co., Ltd.", "Marunouchi Building, 2-4-1 Marunouchi, Chiyoda-ku, Tokyo 100-6308, Japan"),
    ("07JP02", "동북아시아", "Northeast Asia", "일본", "Japan", "포스코재팬 오사카", "POSCO Japan Osaka Office", "HERBIS OSAKA, 2-2-22 Umeda, Kita-ku, Osaka 530-0001, Japan"),
    ("07AU01", "오세아니아", "Oceania", "호주", "Australia", "포스코호주 시드니", "POSCO Australia Pty Ltd", "Level 27, 1 O'Connell Street, Sydney NSW 2000, Australia"),
    ("07AU02", "오세아니아", "Oceania", "호주", "Australia", "포스코호주 퍼스", "POSCO Australia Perth Office", "Exchange Tower, 2 The Esplanade, Perth WA 6000, Australia"),
    ("07TW01", "동북아시아", "Northeast Asia", "대만", "Taiwan", "포스코대만", "POSCO Taiwan Ltd.", "Taipei 101, 7 Xinyi Rd, Sec. 5, Taipei 110, Taiwan"),
    ("07HK01", "동북아시아", "Northeast Asia", "홍콩", "Hong Kong", "포스코홍콩", "POSCO Hong Kong Ltd.", "International Finance Centre Two, 8 Finance St, Central, Hong Kong"),
]


def seed_if_empty(db_session):
    if db_session.query(User).filter_by(username=Config.ADMIN_USERNAME).first():
        return False

    admin = User(
        username=Config.ADMIN_USERNAME,
        password_hash=generate_password_hash(Config.ADMIN_PASSWORD),
        role="admin",
        must_change_password=False,
        is_active=True,
    )
    db_session.add(admin)

    for row in SUBSIDIARIES:
        code, region, region_en, country, country_en, name_ko, name_en, address = row
        sub = Subsidiary(
            code=code,
            region=region,
            region_en=region_en,
            country=country,
            country_en=country_en,
            name_ko=name_ko,
            name_en=name_en,
            address_en=address,
            emails=f"finance.{code.lower()}@posco-overseas.example.com; training.{code.lower()}@posco-overseas.example.com",
            phone="+82-32-200-0114",
            status="active",
        )
        db_session.add(sub)
        db_session.flush()
        db_session.add(
            User(
                username=code,
                password_hash=generate_password_hash(Config.INITIAL_SUBSIDIARY_PASSWORD),
                role="subsidiary",
                subsidiary_id=sub.id,
                must_change_password=True,
                is_active=True,
            )
        )

    db_session.add_all(
        [
            Training(
                title="포스코그룹 리더십 프로그램",
                title_en="POSCO Group Leadership Program",
                start_date=date(2026, 3, 2),
                end_date=date(2026, 3, 6),
                instructor="Kim Minjun",
                unit_price_krw=1_500_000,
            ),
            Training(
                title="글로벌 재무·컴플라이언스 워크숍",
                title_en="Global Finance & Compliance Workshop",
                start_date=date(2026, 9, 14),
                end_date=date(2026, 9, 16),
                instructor="Lee Sujin",
                unit_price_krw=800_000,
            ),
            Training(
                title="해외사업장 안전 리더십",
                title_en="Safety Leadership for Overseas Sites",
                start_date=date(2026, 11, 9),
                end_date=date(2026, 11, 11),
                instructor="Park Jiwon",
                unit_price_krw=950_000,
            ),
        ]
    )
    db_session.commit()
    return True


def ensure_stamp(path):
    from PIL import Image, ImageDraw, ImageFont

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    size = 520
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    navy = (0, 32, 96, 255)
    red = (196, 30, 58, 255)
    draw.ellipse((18, 18, size - 18, size - 18), outline=navy, width=14)
    draw.ellipse((42, 42, size - 42, size - 42), outline=red, width=6)
    draw.ellipse((70, 70, size - 70, size - 70), outline=navy, width=3)
    try:
        font_lg = ImageFont.truetype("arial.ttf", 42)
        font_sm = ImageFont.truetype("arial.ttf", 22)
        font_md = ImageFont.truetype("arial.ttf", 28)
    except OSError:
        font_lg = ImageFont.load_default()
        font_sm = font_lg
        font_md = font_lg

    def center_text(text, y, font, fill):
        bbox = draw.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0]
        draw.text(((size - w) / 2, y), text, font=font, fill=fill)

    center_text("POSCO GROUP", 150, font_sm, navy)
    center_text("UNIVERSITY", 185, font_sm, navy)
    center_text("PGU", 240, font_lg, red)
    center_text("OFFICIAL SEAL", 320, font_md, navy)
    center_text("INCHEON · KOREA", 365, font_sm, navy)
    img.save(path)
