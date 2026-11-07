/**
 * Curated registry of ~200 cities for the World Clock UI.
 *
 * Each entry carries:
 *   - id (kebab-case slug, unique across the registry)
 *   - name: { ptBR, enUS } — display name
 *   - country: { ptBR, enUS } — display country
 *   - continent: 'americas' | 'europe' | 'asia' | 'africa' | 'oceania' | 'antarctica'
 *   - timezone: IANA zone string (validated by tests)
 *   - lat, lng: decimal degrees (used by future day/night arc widgets)
 *   - flag: country emoji
 *
 * Why curated and not "all IANA zones": Intl exposes ~430 timezones with
 * raw names like "America/Argentina/Tucuman" that don't read as cities.
 * This list maps the cities a typical user actually wants to track. The
 * Settings + AddCityModal still let users pick raw IANA zones via search
 * fallback for edge cases.
 *
 * To add a city: ID must be unique, timezone must be a valid IANA zone
 * (test asserts this). Group inside the appropriate continent block to
 * keep the file readable.
 */

// Compact factory — reduces noise; id/tz still readable on each line.
const c = (id, namePt, nameEn, ctryPt, ctryEn, continent, tz, lat, lng, flag) => ({
  id,
  name: { ptBR: namePt, enUS: nameEn },
  country: { ptBR: ctryPt, enUS: ctryEn },
  continent,
  timezone: tz,
  lat,
  lng,
  flag,
})

// prettier-ignore
const CITIES = [
  // ============================================================ AMERICAS ============================================================
  // North America
  c('new-york',       'Nova York',       'New York',       'Estados Unidos', 'United States', 'americas', 'America/New_York',     40.7128,  -74.0060, '🇺🇸'),
  c('los-angeles',    'Los Angeles',     'Los Angeles',    'Estados Unidos', 'United States', 'americas', 'America/Los_Angeles',  34.0522, -118.2437, '🇺🇸'),
  c('chicago',        'Chicago',         'Chicago',        'Estados Unidos', 'United States', 'americas', 'America/Chicago',      41.8781,  -87.6298, '🇺🇸'),
  c('san-francisco',  'São Francisco',   'San Francisco',  'Estados Unidos', 'United States', 'americas', 'America/Los_Angeles',  37.7749, -122.4194, '🇺🇸'),
  c('seattle',        'Seattle',         'Seattle',        'Estados Unidos', 'United States', 'americas', 'America/Los_Angeles',  47.6062, -122.3321, '🇺🇸'),
  c('miami',          'Miami',           'Miami',          'Estados Unidos', 'United States', 'americas', 'America/New_York',     25.7617,  -80.1918, '🇺🇸'),
  c('boston',         'Boston',          'Boston',         'Estados Unidos', 'United States', 'americas', 'America/New_York',     42.3601,  -71.0589, '🇺🇸'),
  c('washington',     'Washington',      'Washington',     'Estados Unidos', 'United States', 'americas', 'America/New_York',     38.9072,  -77.0369, '🇺🇸'),
  c('houston',        'Houston',         'Houston',        'Estados Unidos', 'United States', 'americas', 'America/Chicago',      29.7604,  -95.3698, '🇺🇸'),
  c('dallas',         'Dallas',          'Dallas',         'Estados Unidos', 'United States', 'americas', 'America/Chicago',      32.7767,  -96.7970, '🇺🇸'),
  c('denver',         'Denver',          'Denver',         'Estados Unidos', 'United States', 'americas', 'America/Denver',       39.7392, -104.9903, '🇺🇸'),
  c('phoenix',        'Phoenix',         'Phoenix',        'Estados Unidos', 'United States', 'americas', 'America/Phoenix',      33.4484, -112.0740, '🇺🇸'),
  c('atlanta',        'Atlanta',         'Atlanta',        'Estados Unidos', 'United States', 'americas', 'America/New_York',     33.7490,  -84.3880, '🇺🇸'),
  c('las-vegas',      'Las Vegas',       'Las Vegas',      'Estados Unidos', 'United States', 'americas', 'America/Los_Angeles',  36.1699, -115.1398, '🇺🇸'),
  c('honolulu',       'Honolulu',        'Honolulu',       'Estados Unidos', 'United States', 'americas', 'Pacific/Honolulu',     21.3069, -157.8583, '🇺🇸'),
  c('anchorage',      'Anchorage',       'Anchorage',      'Estados Unidos', 'United States', 'americas', 'America/Anchorage',    61.2181, -149.9003, '🇺🇸'),
  c('toronto',        'Toronto',         'Toronto',        'Canadá',         'Canada',        'americas', 'America/Toronto',      43.6532,  -79.3832, '🇨🇦'),
  c('vancouver',      'Vancouver',       'Vancouver',      'Canadá',         'Canada',        'americas', 'America/Vancouver',    49.2827, -123.1207, '🇨🇦'),
  c('montreal',       'Montreal',        'Montreal',       'Canadá',         'Canada',        'americas', 'America/Toronto',      45.5017,  -73.5673, '🇨🇦'),
  c('calgary',        'Calgary',         'Calgary',        'Canadá',         'Canada',        'americas', 'America/Edmonton',     51.0447, -114.0719, '🇨🇦'),
  c('ottawa',         'Ottawa',          'Ottawa',         'Canadá',         'Canada',        'americas', 'America/Toronto',      45.4215,  -75.6972, '🇨🇦'),
  c('mexico-city',    'Cidade do México','Mexico City',    'México',         'Mexico',        'americas', 'America/Mexico_City',  19.4326,  -99.1332, '🇲🇽'),
  c('cancun',         'Cancún',          'Cancun',         'México',         'Mexico',        'americas', 'America/Cancun',       21.1619,  -86.8515, '🇲🇽'),
  c('guadalajara',    'Guadalajara',     'Guadalajara',    'México',         'Mexico',        'americas', 'America/Mexico_City', 20.6597, -103.3496, '🇲🇽'),
  c('monterrey',      'Monterrey',       'Monterrey',      'México',         'Mexico',        'americas', 'America/Monterrey',    25.6866, -100.3161, '🇲🇽'),
  // Central America + Caribbean
  c('panama-city',    'Cidade do Panamá','Panama City',    'Panamá',         'Panama',        'americas', 'America/Panama',        8.9824,  -79.5199, '🇵🇦'),
  c('san-jose-cr',    'San José',        'San José',       'Costa Rica',     'Costa Rica',    'americas', 'America/Costa_Rica',    9.9281,  -84.0907, '🇨🇷'),
  c('guatemala-city', 'Cidade da Guatemala', 'Guatemala City', 'Guatemala',  'Guatemala',     'americas', 'America/Guatemala',    14.6349,  -90.5069, '🇬🇹'),
  c('santo-domingo',  'Santo Domingo',   'Santo Domingo',  'República Dominicana', 'Dominican Republic', 'americas', 'America/Santo_Domingo', 18.4861, -69.9312, '🇩🇴'),
  c('san-juan',       'San Juan',        'San Juan',       'Porto Rico',     'Puerto Rico',   'americas', 'America/Puerto_Rico',  18.4655,  -66.1057, '🇵🇷'),
  c('havana',         'Havana',          'Havana',         'Cuba',           'Cuba',          'americas', 'America/Havana',       23.1136,  -82.3666, '🇨🇺'),
  c('kingston',       'Kingston',        'Kingston',       'Jamaica',        'Jamaica',       'americas', 'America/Jamaica',      17.9714,  -76.7926, '🇯🇲'),
  // South America
  c('sao-paulo',      'São Paulo',       'São Paulo',      'Brasil',         'Brazil',        'americas', 'America/Sao_Paulo',   -23.5505,  -46.6333, '🇧🇷'),
  c('rio-de-janeiro', 'Rio de Janeiro',  'Rio de Janeiro', 'Brasil',         'Brazil',        'americas', 'America/Sao_Paulo',   -22.9068,  -43.1729, '🇧🇷'),
  c('brasilia',       'Brasília',        'Brasília',       'Brasil',         'Brazil',        'americas', 'America/Sao_Paulo',   -15.7942,  -47.8825, '🇧🇷'),
  c('salvador',       'Salvador',        'Salvador',       'Brasil',         'Brazil',        'americas', 'America/Bahia',       -12.9714,  -38.5014, '🇧🇷'),
  c('fortaleza',      'Fortaleza',       'Fortaleza',      'Brasil',         'Brazil',        'americas', 'America/Fortaleza',    -3.7172,  -38.5433, '🇧🇷'),
  c('belo-horizonte', 'Belo Horizonte',  'Belo Horizonte', 'Brasil',         'Brazil',        'americas', 'America/Sao_Paulo',   -19.9167,  -43.9345, '🇧🇷'),
  c('recife',         'Recife',          'Recife',         'Brasil',         'Brazil',        'americas', 'America/Recife',       -8.0476,  -34.8770, '🇧🇷'),
  c('manaus',         'Manaus',          'Manaus',         'Brasil',         'Brazil',        'americas', 'America/Manaus',       -3.1190,  -60.0217, '🇧🇷'),
  c('curitiba',       'Curitiba',        'Curitiba',       'Brasil',         'Brazil',        'americas', 'America/Sao_Paulo',   -25.4284,  -49.2733, '🇧🇷'),
  c('porto-alegre',   'Porto Alegre',    'Porto Alegre',   'Brasil',         'Brazil',        'americas', 'America/Sao_Paulo',   -30.0346,  -51.2177, '🇧🇷'),
  c('buenos-aires',   'Buenos Aires',    'Buenos Aires',   'Argentina',      'Argentina',     'americas', 'America/Argentina/Buenos_Aires', -34.6037, -58.3816, '🇦🇷'),
  c('santiago',       'Santiago',        'Santiago',       'Chile',          'Chile',         'americas', 'America/Santiago',    -33.4489,  -70.6693, '🇨🇱'),
  c('lima',           'Lima',            'Lima',           'Peru',           'Peru',          'americas', 'America/Lima',        -12.0464,  -77.0428, '🇵🇪'),
  c('bogota',         'Bogotá',          'Bogotá',         'Colômbia',       'Colombia',      'americas', 'America/Bogota',        4.7110,  -74.0721, '🇨🇴'),
  c('caracas',        'Caracas',         'Caracas',        'Venezuela',      'Venezuela',     'americas', 'America/Caracas',      10.4806,  -66.9036, '🇻🇪'),
  c('quito',          'Quito',           'Quito',          'Equador',        'Ecuador',       'americas', 'America/Guayaquil',    -0.1807,  -78.4678, '🇪🇨'),
  c('guayaquil',      'Guayaquil',       'Guayaquil',      'Equador',        'Ecuador',       'americas', 'America/Guayaquil',    -2.1894,  -79.8890, '🇪🇨'),
  c('la-paz',         'La Paz',          'La Paz',         'Bolívia',        'Bolivia',       'americas', 'America/La_Paz',      -16.4897,  -68.1193, '🇧🇴'),
  c('montevideo',     'Montevidéu',      'Montevideo',     'Uruguai',        'Uruguay',       'americas', 'America/Montevideo',  -34.9011,  -56.1645, '🇺🇾'),
  c('asuncion',       'Assunção',        'Asunción',       'Paraguai',       'Paraguay',      'americas', 'America/Asuncion',    -25.2637,  -57.5759, '🇵🇾'),

  // ============================================================ EUROPE ============================================================
  c('london',         'Londres',         'London',         'Reino Unido',    'United Kingdom','europe',   'Europe/London',        51.5074,   -0.1278, '🇬🇧'),
  c('edinburgh',      'Edimburgo',       'Edinburgh',      'Reino Unido',    'United Kingdom','europe',   'Europe/London',        55.9533,   -3.1883, '🇬🇧'),
  c('manchester',     'Manchester',      'Manchester',     'Reino Unido',    'United Kingdom','europe',   'Europe/London',        53.4808,   -2.2426, '🇬🇧'),
  c('glasgow',        'Glasgow',         'Glasgow',        'Reino Unido',    'United Kingdom','europe',   'Europe/London',        55.8642,   -4.2518, '🇬🇧'),
  c('dublin',         'Dublin',          'Dublin',         'Irlanda',        'Ireland',       'europe',   'Europe/Dublin',        53.3498,   -6.2603, '🇮🇪'),
  c('paris',          'Paris',           'Paris',          'França',         'France',        'europe',   'Europe/Paris',         48.8566,    2.3522, '🇫🇷'),
  c('marseille',      'Marselha',        'Marseille',      'França',         'France',        'europe',   'Europe/Paris',         43.2965,    5.3698, '🇫🇷'),
  c('lyon',           'Lyon',            'Lyon',           'França',         'France',        'europe',   'Europe/Paris',         45.7640,    4.8357, '🇫🇷'),
  c('madrid',         'Madri',           'Madrid',         'Espanha',        'Spain',         'europe',   'Europe/Madrid',        40.4168,   -3.7038, '🇪🇸'),
  c('barcelona',      'Barcelona',       'Barcelona',      'Espanha',        'Spain',         'europe',   'Europe/Madrid',        41.3851,    2.1734, '🇪🇸'),
  c('valencia',       'Valência',        'Valencia',       'Espanha',        'Spain',         'europe',   'Europe/Madrid',        39.4699,   -0.3763, '🇪🇸'),
  c('seville',        'Sevilha',         'Seville',        'Espanha',        'Spain',         'europe',   'Europe/Madrid',        37.3891,   -5.9845, '🇪🇸'),
  c('lisbon',         'Lisboa',          'Lisbon',         'Portugal',       'Portugal',      'europe',   'Europe/Lisbon',        38.7223,   -9.1393, '🇵🇹'),
  c('porto',          'Porto',           'Porto',          'Portugal',       'Portugal',      'europe',   'Europe/Lisbon',        41.1579,   -8.6291, '🇵🇹'),
  c('rome',           'Roma',            'Rome',           'Itália',         'Italy',         'europe',   'Europe/Rome',          41.9028,   12.4964, '🇮🇹'),
  c('milan',          'Milão',           'Milan',          'Itália',         'Italy',         'europe',   'Europe/Rome',          45.4642,    9.1900, '🇮🇹'),
  c('naples',         'Nápoles',         'Naples',         'Itália',         'Italy',         'europe',   'Europe/Rome',          40.8518,   14.2681, '🇮🇹'),
  c('florence',       'Florença',        'Florence',       'Itália',         'Italy',         'europe',   'Europe/Rome',          43.7696,   11.2558, '🇮🇹'),
  c('venice',         'Veneza',          'Venice',         'Itália',         'Italy',         'europe',   'Europe/Rome',          45.4408,   12.3155, '🇮🇹'),
  c('berlin',         'Berlim',          'Berlin',         'Alemanha',       'Germany',       'europe',   'Europe/Berlin',        52.5200,   13.4050, '🇩🇪'),
  c('munich',         'Munique',         'Munich',         'Alemanha',       'Germany',       'europe',   'Europe/Berlin',        48.1351,   11.5820, '🇩🇪'),
  c('hamburg',        'Hamburgo',        'Hamburg',        'Alemanha',       'Germany',       'europe',   'Europe/Berlin',        53.5511,    9.9937, '🇩🇪'),
  c('frankfurt',      'Frankfurt',       'Frankfurt',      'Alemanha',       'Germany',       'europe',   'Europe/Berlin',        50.1109,    8.6821, '🇩🇪'),
  c('cologne',        'Colônia',         'Cologne',        'Alemanha',       'Germany',       'europe',   'Europe/Berlin',        50.9375,    6.9603, '🇩🇪'),
  c('amsterdam',      'Amsterdã',        'Amsterdam',      'Países Baixos',  'Netherlands',   'europe',   'Europe/Amsterdam',     52.3676,    4.9041, '🇳🇱'),
  c('brussels',       'Bruxelas',        'Brussels',       'Bélgica',        'Belgium',       'europe',   'Europe/Brussels',      50.8503,    4.3517, '🇧🇪'),
  c('vienna',         'Viena',           'Vienna',         'Áustria',        'Austria',       'europe',   'Europe/Vienna',        48.2082,   16.3738, '🇦🇹'),
  c('zurich',         'Zurique',         'Zurich',         'Suíça',          'Switzerland',   'europe',   'Europe/Zurich',        47.3769,    8.5417, '🇨🇭'),
  c('geneva',         'Genebra',         'Geneva',         'Suíça',          'Switzerland',   'europe',   'Europe/Zurich',        46.2044,    6.1432, '🇨🇭'),
  c('stockholm',      'Estocolmo',       'Stockholm',      'Suécia',         'Sweden',        'europe',   'Europe/Stockholm',     59.3293,   18.0686, '🇸🇪'),
  c('oslo',           'Oslo',            'Oslo',           'Noruega',        'Norway',        'europe',   'Europe/Oslo',          59.9139,   10.7522, '🇳🇴'),
  c('copenhagen',     'Copenhague',      'Copenhagen',     'Dinamarca',      'Denmark',       'europe',   'Europe/Copenhagen',    55.6761,   12.5683, '🇩🇰'),
  c('helsinki',       'Helsinque',       'Helsinki',       'Finlândia',      'Finland',       'europe',   'Europe/Helsinki',      60.1699,   24.9384, '🇫🇮'),
  c('reykjavik',      'Reykjavik',       'Reykjavik',      'Islândia',       'Iceland',       'europe',   'Atlantic/Reykjavik',   64.1466,  -21.9426, '🇮🇸'),
  c('athens',         'Atenas',          'Athens',         'Grécia',         'Greece',        'europe',   'Europe/Athens',        37.9838,   23.7275, '🇬🇷'),
  c('warsaw',         'Varsóvia',        'Warsaw',         'Polônia',        'Poland',        'europe',   'Europe/Warsaw',        52.2297,   21.0122, '🇵🇱'),
  c('prague',         'Praga',           'Prague',         'República Tcheca','Czech Republic','europe',  'Europe/Prague',        50.0755,   14.4378, '🇨🇿'),
  c('budapest',       'Budapeste',       'Budapest',       'Hungria',        'Hungary',       'europe',   'Europe/Budapest',      47.4979,   19.0402, '🇭🇺'),
  c('bucharest',      'Bucareste',       'Bucharest',      'Romênia',        'Romania',       'europe',   'Europe/Bucharest',     44.4268,   26.1025, '🇷🇴'),
  c('sofia',          'Sófia',           'Sofia',          'Bulgária',       'Bulgaria',      'europe',   'Europe/Sofia',         42.6977,   23.3219, '🇧🇬'),
  c('moscow',         'Moscou',          'Moscow',         'Rússia',         'Russia',        'europe',   'Europe/Moscow',        55.7558,   37.6173, '🇷🇺'),
  c('saint-petersburg','São Petersburgo','Saint Petersburg','Rússia',        'Russia',        'europe',   'Europe/Moscow',        59.9311,   30.3609, '🇷🇺'),
  c('kyiv',           'Kiev',            'Kyiv',           'Ucrânia',        'Ukraine',       'europe',   'Europe/Kyiv',          50.4501,   30.5234, '🇺🇦'),
  c('belgrade',       'Belgrado',        'Belgrade',       'Sérvia',         'Serbia',        'europe',   'Europe/Belgrade',      44.7866,   20.4489, '🇷🇸'),
  c('zagreb',         'Zagreb',          'Zagreb',         'Croácia',        'Croatia',       'europe',   'Europe/Zagreb',        45.8150,   15.9819, '🇭🇷'),
  c('ljubljana',      'Liubliana',       'Ljubljana',      'Eslovênia',      'Slovenia',      'europe',   'Europe/Ljubljana',     46.0569,   14.5058, '🇸🇮'),
  c('bratislava',     'Bratislava',      'Bratislava',     'Eslováquia',     'Slovakia',      'europe',   'Europe/Bratislava',    48.1486,   17.1077, '🇸🇰'),
  c('tallinn',        'Tallinn',         'Tallinn',        'Estônia',        'Estonia',       'europe',   'Europe/Tallinn',       59.4370,   24.7536, '🇪🇪'),
  c('riga',           'Riga',            'Riga',           'Letônia',        'Latvia',        'europe',   'Europe/Riga',          56.9496,   24.1052, '🇱🇻'),
  c('vilnius',        'Vilnius',         'Vilnius',        'Lituânia',       'Lithuania',     'europe',   'Europe/Vilnius',       54.6872,   25.2797, '🇱🇹'),
  c('istanbul',       'Istambul',        'Istanbul',       'Turquia',        'Turkey',        'europe',   'Europe/Istanbul',      41.0082,   28.9784, '🇹🇷'),
  c('ankara',         'Ancara',          'Ankara',         'Turquia',        'Turkey',        'europe',   'Europe/Istanbul',      39.9334,   32.8597, '🇹🇷'),

  // ============================================================ ASIA ============================================================
  c('tokyo',          'Tóquio',          'Tokyo',          'Japão',          'Japan',         'asia',     'Asia/Tokyo',           35.6762,  139.6503, '🇯🇵'),
  c('osaka',          'Osaka',           'Osaka',          'Japão',          'Japan',         'asia',     'Asia/Tokyo',           34.6937,  135.5023, '🇯🇵'),
  c('kyoto',          'Quioto',          'Kyoto',          'Japão',          'Japan',         'asia',     'Asia/Tokyo',           35.0116,  135.7681, '🇯🇵'),
  c('beijing',        'Pequim',          'Beijing',        'China',          'China',         'asia',     'Asia/Shanghai',        39.9042,  116.4074, '🇨🇳'),
  c('shanghai',       'Xangai',          'Shanghai',       'China',          'China',         'asia',     'Asia/Shanghai',        31.2304,  121.4737, '🇨🇳'),
  c('hong-kong',      'Hong Kong',       'Hong Kong',      'Hong Kong',      'Hong Kong',     'asia',     'Asia/Hong_Kong',       22.3193,  114.1694, '🇭🇰'),
  c('macau',          'Macau',           'Macau',          'Macau',          'Macao',         'asia',     'Asia/Macau',           22.1987,  113.5439, '🇲🇴'),
  c('taipei',         'Taipei',          'Taipei',         'Taiwan',         'Taiwan',        'asia',     'Asia/Taipei',          25.0330,  121.5654, '🇹🇼'),
  c('seoul',          'Seul',            'Seoul',          'Coreia do Sul',  'South Korea',   'asia',     'Asia/Seoul',           37.5665,  126.9780, '🇰🇷'),
  c('busan',          'Busan',           'Busan',          'Coreia do Sul',  'South Korea',   'asia',     'Asia/Seoul',           35.1796,  129.0756, '🇰🇷'),
  c('pyongyang',      'Pyongyang',       'Pyongyang',      'Coreia do Norte','North Korea',   'asia',     'Asia/Pyongyang',       39.0392,  125.7625, '🇰🇵'),
  c('singapore',      'Singapura',       'Singapore',      'Singapura',      'Singapore',     'asia',     'Asia/Singapore',        1.3521,  103.8198, '🇸🇬'),
  c('kuala-lumpur',   'Kuala Lumpur',    'Kuala Lumpur',   'Malásia',        'Malaysia',      'asia',     'Asia/Kuala_Lumpur',     3.1390,  101.6869, '🇲🇾'),
  c('bangkok',        'Bangkok',         'Bangkok',        'Tailândia',      'Thailand',      'asia',     'Asia/Bangkok',         13.7563,  100.5018, '🇹🇭'),
  c('jakarta',        'Jacarta',         'Jakarta',        'Indonésia',      'Indonesia',     'asia',     'Asia/Jakarta',         -6.2088,  106.8456, '🇮🇩'),
  c('manila',         'Manila',          'Manila',         'Filipinas',      'Philippines',   'asia',     'Asia/Manila',          14.5995,  120.9842, '🇵🇭'),
  c('ho-chi-minh',    'Cidade de Ho Chi Minh', 'Ho Chi Minh City', 'Vietnã', 'Vietnam',       'asia',     'Asia/Ho_Chi_Minh',     10.8231,  106.6297, '🇻🇳'),
  c('hanoi',          'Hanói',           'Hanoi',          'Vietnã',         'Vietnam',       'asia',     'Asia/Ho_Chi_Minh',     21.0285,  105.8542, '🇻🇳'),
  c('phnom-penh',     'Phnom Penh',      'Phnom Penh',     'Camboja',        'Cambodia',      'asia',     'Asia/Phnom_Penh',      11.5564,  104.9282, '🇰🇭'),
  c('vientiane',      'Vientiane',       'Vientiane',      'Laos',           'Laos',          'asia',     'Asia/Vientiane',       17.9757,  102.6331, '🇱🇦'),
  c('yangon',         'Yangon',          'Yangon',         'Mianmar',        'Myanmar',       'asia',     'Asia/Yangon',          16.8409,   96.1735, '🇲🇲'),
  c('mumbai',         'Mumbai',          'Mumbai',         'Índia',          'India',         'asia',     'Asia/Kolkata',         19.0760,   72.8777, '🇮🇳'),
  c('delhi',          'Delhi',           'Delhi',          'Índia',          'India',         'asia',     'Asia/Kolkata',         28.7041,   77.1025, '🇮🇳'),
  c('bangalore',      'Bangalore',       'Bangalore',      'Índia',          'India',         'asia',     'Asia/Kolkata',         12.9716,   77.5946, '🇮🇳'),
  c('chennai',        'Chennai',         'Chennai',        'Índia',          'India',         'asia',     'Asia/Kolkata',         13.0827,   80.2707, '🇮🇳'),
  c('kolkata',        'Calcutá',         'Kolkata',        'Índia',          'India',         'asia',     'Asia/Kolkata',         22.5726,   88.3639, '🇮🇳'),
  c('hyderabad',      'Hyderabad',       'Hyderabad',      'Índia',          'India',         'asia',     'Asia/Kolkata',         17.3850,   78.4867, '🇮🇳'),
  c('karachi',        'Karachi',         'Karachi',        'Paquistão',      'Pakistan',      'asia',     'Asia/Karachi',         24.8607,   67.0011, '🇵🇰'),
  c('lahore',         'Lahore',          'Lahore',         'Paquistão',      'Pakistan',      'asia',     'Asia/Karachi',         31.5497,   74.3436, '🇵🇰'),
  c('islamabad',      'Islamabad',       'Islamabad',      'Paquistão',      'Pakistan',      'asia',     'Asia/Karachi',         33.6844,   73.0479, '🇵🇰'),
  c('dhaka',          'Daca',            'Dhaka',          'Bangladesh',     'Bangladesh',    'asia',     'Asia/Dhaka',           23.8103,   90.4125, '🇧🇩'),
  c('colombo',        'Colombo',         'Colombo',        'Sri Lanka',      'Sri Lanka',     'asia',     'Asia/Colombo',          6.9271,   79.8612, '🇱🇰'),
  c('kathmandu',      'Catmandu',        'Kathmandu',      'Nepal',          'Nepal',         'asia',     'Asia/Kathmandu',       27.7172,   85.3240, '🇳🇵'),
  c('kabul',          'Cabul',           'Kabul',          'Afeganistão',    'Afghanistan',   'asia',     'Asia/Kabul',           34.5553,   69.2075, '🇦🇫'),
  c('tehran',         'Teerã',           'Tehran',         'Irã',            'Iran',          'asia',     'Asia/Tehran',          35.6892,   51.3890, '🇮🇷'),
  c('baghdad',        'Bagdá',           'Baghdad',        'Iraque',         'Iraq',          'asia',     'Asia/Baghdad',         33.3152,   44.3661, '🇮🇶'),
  c('riyadh',         'Riade',           'Riyadh',         'Arábia Saudita', 'Saudi Arabia',  'asia',     'Asia/Riyadh',          24.7136,   46.6753, '🇸🇦'),
  c('mecca',          'Meca',            'Mecca',          'Arábia Saudita', 'Saudi Arabia',  'asia',     'Asia/Riyadh',          21.3891,   39.8579, '🇸🇦'),
  c('jeddah',         'Jeddah',          'Jeddah',         'Arábia Saudita', 'Saudi Arabia',  'asia',     'Asia/Riyadh',          21.4858,   39.1925, '🇸🇦'),
  c('dubai',          'Dubai',           'Dubai',          'Emirados Árabes Unidos', 'United Arab Emirates', 'asia', 'Asia/Dubai', 25.2048, 55.2708, '🇦🇪'),
  c('abu-dhabi',      'Abu Dhabi',       'Abu Dhabi',      'Emirados Árabes Unidos', 'United Arab Emirates', 'asia', 'Asia/Dubai', 24.4539, 54.3773, '🇦🇪'),
  c('doha',           'Doha',            'Doha',           'Catar',          'Qatar',         'asia',     'Asia/Qatar',           25.2854,   51.5310, '🇶🇦'),
  c('kuwait-city',    'Cidade do Kuwait','Kuwait City',    'Kuwait',         'Kuwait',        'asia',     'Asia/Kuwait',          29.3759,   47.9774, '🇰🇼'),
  c('manama',         'Manama',          'Manama',         'Barein',         'Bahrain',       'asia',     'Asia/Bahrain',         26.2235,   50.5876, '🇧🇭'),
  c('muscat',         'Mascate',         'Muscat',         'Omã',            'Oman',          'asia',     'Asia/Muscat',          23.5859,   58.4059, '🇴🇲'),
  c('amman',          'Amã',             'Amman',          'Jordânia',       'Jordan',        'asia',     'Asia/Amman',           31.9454,   35.9284, '🇯🇴'),
  c('beirut',         'Beirute',         'Beirut',         'Líbano',         'Lebanon',       'asia',     'Asia/Beirut',          33.8938,   35.5018, '🇱🇧'),
  c('damascus',       'Damasco',         'Damascus',       'Síria',          'Syria',         'asia',     'Asia/Damascus',        33.5138,   36.2765, '🇸🇾'),
  c('jerusalem',      'Jerusalém',       'Jerusalem',      'Israel',         'Israel',        'asia',     'Asia/Jerusalem',       31.7683,   35.2137, '🇮🇱'),
  c('tel-aviv',       'Tel Aviv',        'Tel Aviv',       'Israel',         'Israel',        'asia',     'Asia/Jerusalem',       32.0853,   34.7818, '🇮🇱'),
  c('tbilisi',        'Tbilisi',         'Tbilisi',        'Geórgia',        'Georgia',       'asia',     'Asia/Tbilisi',         41.7151,   44.8271, '🇬🇪'),
  c('yerevan',        'Erevan',          'Yerevan',        'Armênia',        'Armenia',       'asia',     'Asia/Yerevan',         40.1872,   44.5152, '🇦🇲'),
  c('baku',           'Baku',            'Baku',           'Azerbaijão',     'Azerbaijan',    'asia',     'Asia/Baku',            40.4093,   49.8671, '🇦🇿'),
  c('tashkent',       'Tashkent',        'Tashkent',       'Uzbequistão',    'Uzbekistan',    'asia',     'Asia/Tashkent',        41.2995,   69.2401, '🇺🇿'),
  c('almaty',         'Almaty',          'Almaty',         'Cazaquistão',    'Kazakhstan',    'asia',     'Asia/Almaty',          43.2220,   76.8512, '🇰🇿'),
  c('astana',         'Astana',          'Astana',         'Cazaquistão',    'Kazakhstan',    'asia',     'Asia/Almaty',          51.1605,   71.4704, '🇰🇿'),
  c('vladivostok',    'Vladivostok',     'Vladivostok',    'Rússia',         'Russia',        'asia',     'Asia/Vladivostok',     43.1198,  131.8869, '🇷🇺'),
  c('yekaterinburg',  'Ecaterimburgo',   'Yekaterinburg',  'Rússia',         'Russia',        'asia',     'Asia/Yekaterinburg',   56.8431,   60.6454, '🇷🇺'),
  c('novosibirsk',    'Novosibirsk',     'Novosibirsk',    'Rússia',         'Russia',        'asia',     'Asia/Novosibirsk',     55.0084,   82.9357, '🇷🇺'),
  c('ulaanbaatar',    'Ulã Bator',       'Ulaanbaatar',    'Mongólia',       'Mongolia',      'asia',     'Asia/Ulaanbaatar',     47.8864,  106.9057, '🇲🇳'),

  // ============================================================ AFRICA ============================================================
  c('cairo',          'Cairo',           'Cairo',          'Egito',          'Egypt',         'africa',   'Africa/Cairo',         30.0444,   31.2357, '🇪🇬'),
  c('alexandria',     'Alexandria',      'Alexandria',     'Egito',          'Egypt',         'africa',   'Africa/Cairo',         31.2001,   29.9187, '🇪🇬'),
  c('lagos',          'Lagos',           'Lagos',          'Nigéria',        'Nigeria',       'africa',   'Africa/Lagos',          6.5244,    3.3792, '🇳🇬'),
  c('abuja',          'Abuja',           'Abuja',          'Nigéria',        'Nigeria',       'africa',   'Africa/Lagos',          9.0765,    7.3986, '🇳🇬'),
  c('johannesburg',   'Joanesburgo',     'Johannesburg',   'África do Sul',  'South Africa',  'africa',   'Africa/Johannesburg', -26.2041,   28.0473, '🇿🇦'),
  c('cape-town',      'Cidade do Cabo',  'Cape Town',      'África do Sul',  'South Africa',  'africa',   'Africa/Johannesburg', -33.9249,   18.4241, '🇿🇦'),
  c('pretoria',       'Pretória',        'Pretoria',       'África do Sul',  'South Africa',  'africa',   'Africa/Johannesburg', -25.7479,   28.2293, '🇿🇦'),
  c('nairobi',        'Nairóbi',         'Nairobi',        'Quênia',         'Kenya',         'africa',   'Africa/Nairobi',       -1.2921,   36.8219, '🇰🇪'),
  c('addis-ababa',    'Adis Abeba',      'Addis Ababa',    'Etiópia',        'Ethiopia',      'africa',   'Africa/Addis_Ababa',    9.0320,   38.7469, '🇪🇹'),
  c('dar-es-salaam',  'Dar es Salaam',   'Dar es Salaam',  'Tanzânia',       'Tanzania',      'africa',   'Africa/Dar_es_Salaam', -6.7924,   39.2083, '🇹🇿'),
  c('kampala',        'Kampala',         'Kampala',        'Uganda',         'Uganda',        'africa',   'Africa/Kampala',        0.3476,   32.5825, '🇺🇬'),
  c('khartoum',       'Cartum',          'Khartoum',       'Sudão',          'Sudan',         'africa',   'Africa/Khartoum',      15.5007,   32.5599, '🇸🇩'),
  c('algiers',        'Argel',           'Algiers',        'Argélia',        'Algeria',       'africa',   'Africa/Algiers',       36.7372,    3.0866, '🇩🇿'),
  c('casablanca',     'Casablanca',      'Casablanca',     'Marrocos',       'Morocco',       'africa',   'Africa/Casablanca',    33.5731,   -7.5898, '🇲🇦'),
  c('marrakech',      'Marraquexe',      'Marrakech',      'Marrocos',       'Morocco',       'africa',   'Africa/Casablanca',    31.6295,   -7.9811, '🇲🇦'),
  c('tunis',          'Túnis',           'Tunis',          'Tunísia',        'Tunisia',       'africa',   'Africa/Tunis',         36.8065,   10.1815, '🇹🇳'),
  c('tripoli',        'Trípoli',         'Tripoli',        'Líbia',          'Libya',         'africa',   'Africa/Tripoli',       32.8872,   13.1913, '🇱🇾'),
  c('accra',          'Acra',            'Accra',          'Gana',           'Ghana',         'africa',   'Africa/Accra',          5.6037,   -0.1870, '🇬🇭'),
  c('dakar',          'Dakar',           'Dakar',          'Senegal',        'Senegal',       'africa',   'Africa/Dakar',         14.7167,  -17.4677, '🇸🇳'),
  c('abidjan',        'Abidjã',          'Abidjan',        'Costa do Marfim','Ivory Coast',   'africa',   'Africa/Abidjan',        5.3600,   -4.0083, '🇨🇮'),
  c('luanda',         'Luanda',          'Luanda',         'Angola',         'Angola',        'africa',   'Africa/Luanda',        -8.8390,   13.2894, '🇦🇴'),
  c('maputo',         'Maputo',          'Maputo',         'Moçambique',     'Mozambique',    'africa',   'Africa/Maputo',       -25.9692,   32.5732, '🇲🇿'),
  c('harare',         'Harare',          'Harare',         'Zimbábue',       'Zimbabwe',      'africa',   'Africa/Harare',       -17.8252,   31.0335, '🇿🇼'),
  c('lusaka',         'Lusaca',          'Lusaka',         'Zâmbia',         'Zambia',        'africa',   'Africa/Lusaka',       -15.3875,   28.3228, '🇿🇲'),
  c('kinshasa',       'Quinxassa',       'Kinshasa',       'República Democrática do Congo', 'DR Congo', 'africa', 'Africa/Kinshasa', -4.4419, 15.2663, '🇨🇩'),

  // ============================================================ OCEANIA ============================================================
  c('sydney',         'Sydney',          'Sydney',         'Austrália',      'Australia',     'oceania',  'Australia/Sydney',    -33.8688,  151.2093, '🇦🇺'),
  c('melbourne',      'Melbourne',       'Melbourne',      'Austrália',      'Australia',     'oceania',  'Australia/Melbourne', -37.8136,  144.9631, '🇦🇺'),
  c('brisbane',       'Brisbane',        'Brisbane',       'Austrália',      'Australia',     'oceania',  'Australia/Brisbane',  -27.4698,  153.0251, '🇦🇺'),
  c('perth',          'Perth',           'Perth',          'Austrália',      'Australia',     'oceania',  'Australia/Perth',     -31.9505,  115.8605, '🇦🇺'),
  c('adelaide',       'Adelaide',        'Adelaide',       'Austrália',      'Australia',     'oceania',  'Australia/Adelaide',  -34.9285,  138.6007, '🇦🇺'),
  c('canberra',       'Camberra',        'Canberra',       'Austrália',      'Australia',     'oceania',  'Australia/Sydney',    -35.2809,  149.1300, '🇦🇺'),
  c('hobart',         'Hobart',          'Hobart',         'Austrália',      'Australia',     'oceania',  'Australia/Hobart',    -42.8821,  147.3272, '🇦🇺'),
  c('darwin',         'Darwin',          'Darwin',         'Austrália',      'Australia',     'oceania',  'Australia/Darwin',    -12.4634,  130.8456, '🇦🇺'),
  c('auckland',       'Auckland',        'Auckland',       'Nova Zelândia',  'New Zealand',   'oceania',  'Pacific/Auckland',    -36.8485,  174.7633, '🇳🇿'),
  c('wellington',     'Wellington',      'Wellington',     'Nova Zelândia',  'New Zealand',   'oceania',  'Pacific/Auckland',    -41.2865,  174.7762, '🇳🇿'),
  c('suva',           'Suva',            'Suva',           'Fiji',           'Fiji',          'oceania',  'Pacific/Fiji',        -18.1248,  178.4501, '🇫🇯'),
  c('port-moresby',   'Port Moresby',    'Port Moresby',   'Papua-Nova Guiné','Papua New Guinea','oceania','Pacific/Port_Moresby', -9.4438,  147.1803, '🇵🇬'),

  // ============================================================ ANTARCTICA ============================================================
  c('mcmurdo',        'Estação McMurdo', 'McMurdo Station','Antártida',      'Antarctica',    'antarctica', 'Antarctica/McMurdo', -77.8419, 166.6863, '🇦🇶'),
  c('palmer',         'Estação Palmer',  'Palmer Station', 'Antártida',      'Antarctica',    'antarctica', 'Antarctica/Palmer',  -64.7745, -64.0530, '🇦🇶'),
  c('rothera',        'Estação Rothera', 'Rothera',        'Antártida',      'Antarctica',    'antarctica', 'Antarctica/Rothera', -67.5675, -68.1330, '🇦🇶'),
]

// Frozen so consumers can't mutate accidentally.
Object.freeze(CITIES)

// Index for O(1) lookups by id.
const _byId = new Map(CITIES.map((city) => [city.id, city]))

// Index by timezone (multiple cities share zones — value is array).
const _byTimezone = new Map()
for (const city of CITIES) {
  if (!_byTimezone.has(city.timezone)) _byTimezone.set(city.timezone, [])
  _byTimezone.get(city.timezone).push(city)
}

export const ALL_CITIES = CITIES

export const CONTINENTS = ['americas', 'europe', 'asia', 'africa', 'oceania', 'antarctica']

/**
 * Look up a city by its id. Returns null if not found.
 */
export const findCityById = (id) => _byId.get(id) || null

/**
 * All cities that share the given IANA timezone, sorted by name (en-US).
 * Useful when the user picked a custom IANA zone — we can offer a
 * representative city for the day/night dot.
 */
export const findCitiesByTimezone = (tz) => {
  const list = _byTimezone.get(tz)
  return list ? [...list] : []
}

/**
 * First city associated with the given timezone, for cases where any
 * representative is acceptable (lat/lng for solar calc, etc.).
 */
export const findRepresentativeCityForTimezone = (tz) => {
  const list = _byTimezone.get(tz)
  return list && list[0] ? list[0] : null
}

/**
 * Group cities by continent. Each group is sorted alphabetically by
 * the city's en-US name (stable across locales — UI can resort if needed).
 */
export const groupByContinent = () => {
  const groups = {}
  for (const cont of CONTINENTS) groups[cont] = []
  for (const city of CITIES) {
    if (groups[city.continent]) groups[city.continent].push(city)
  }
  for (const cont of CONTINENTS) {
    groups[cont].sort((a, b) => a.name.enUS.localeCompare(b.name.enUS))
  }
  return groups
}

/**
 * Search cities by free-text query against name (both locales) and country.
 * Case-insensitive, accent-insensitive (basic NFD normalization).
 */
export const searchCities = (query) => {
  const q = (query || '').toString().trim()
  if (!q) return []
  const normalized = q.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
  const matches = []
  for (const city of CITIES) {
    const haystack = [city.name.ptBR, city.name.enUS, city.country.ptBR, city.country.enUS, city.id]
      .join(' ')
      .normalize('NFD')
      .replace(/[̀-ͯ]/g, '')
      .toLowerCase()
    if (haystack.includes(normalized)) matches.push(city)
  }
  return matches
}

/**
 * Pick the localized name for a city given a vue-i18n locale string.
 * Falls back to en-US for any locale outside pt-BR (matches the
 * comm-materials policy in 96-comm-materials-policy.md).
 */
export const cityName = (city, locale = 'en-US') => {
  if (!city) return ''
  if (locale && locale.startsWith('pt')) return city.name.ptBR
  return city.name.enUS
}

export const cityCountry = (city, locale = 'en-US') => {
  if (!city) return ''
  if (locale && locale.startsWith('pt')) return city.country.ptBR
  return city.country.enUS
}

// ============================ FLAG HELPERS ============================

// Converte o flag emoji do registro (composto por 2 Regional Indicator
// codepoints, U+1F1E6..U+1F1FF = A..Z) no código ISO 3166-1 alpha-2
// correspondente. Necessário no Windows porque Segoe UI Emoji não
// renderiza bandeiras — temos que servir PNG via flagcdn.com (mesmo
// padrão usado no ROSLanguageSelector).
const FLAG_BASE = 0x1f1e6
export const flagToIso2 = (flag) => {
  if (!flag) return null
  const cps = [...flag].map((c) => c.codePointAt(0))
  if (cps.length !== 2) return null
  const a = cps[0] - FLAG_BASE
  const b = cps[1] - FLAG_BASE
  if (a < 0 || a > 25 || b < 0 || b > 25) return null
  return String.fromCharCode(65 + a) + String.fromCharCode(65 + b)
}

// URL CDN de bandeira PNG. w40 = 40px wide (~suficiente pra qualquer
// uso atual; flagcdn.com cacheia agressivamente, ~1KB cada).
export const flagUrl = (iso2) => {
  if (!iso2) return null
  return `https://flagcdn.com/w40/${iso2.toLowerCase()}.png`
}

// Helper composto: city → URL pronta. Retorna null se a cidade não
// tiver flag emoji válido (caller mostra placeholder).
export const cityFlagUrl = (city) => {
  if (!city?.flag) return null
  const iso = flagToIso2(city.flag)
  return iso ? flagUrl(iso) : null
}
