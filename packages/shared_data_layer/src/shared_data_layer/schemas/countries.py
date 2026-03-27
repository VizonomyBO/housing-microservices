"""Country/region helpers for Pydantic schemas.

Data pulled from https://github.com/lukes/ISO-3166-Countries-with-Regional-Codes
(retrieved 2025-11-26) and baked into the codebase to keep schema validation
deterministic.
"""

from __future__ import annotations

from enum import Enum


class CountryISOAlpha3(str, Enum):
    """ISO 3166-1 alpha-3 codes mapped to human-readable names."""

    label: str

    def __new__(cls, code: str, label: str):
        obj = str.__new__(cls, code)
        obj._value_ = code
        obj.label = label
        return obj

    AFGHANISTAN = ("AFG", "Afghanistan")
    ALAND_ISLANDS = ("ALA", "Aland Islands")
    ALBANIA = ("ALB", "Albania")
    ALGERIA = ("DZA", "Algeria")
    AMERICAN_SAMOA = ("ASM", "American Samoa")
    ANDORRA = ("AND", "Andorra")
    ANGOLA = ("AGO", "Angola")
    ANGUILLA = ("AIA", "Anguilla")
    ANTARCTICA = ("ATA", "Antarctica")
    ANTIGUA_AND_BARBUDA = ("ATG", "Antigua and Barbuda")
    ARGENTINA = ("ARG", "Argentina")
    ARMENIA = ("ARM", "Armenia")
    ARUBA = ("ABW", "Aruba")
    AUSTRALIA = ("AUS", "Australia")
    AUSTRIA = ("AUT", "Austria")
    AZERBAIJAN = ("AZE", "Azerbaijan")
    BAHAMAS = ("BHS", "Bahamas")
    BAHRAIN = ("BHR", "Bahrain")
    BANGLADESH = ("BGD", "Bangladesh")
    BARBADOS = ("BRB", "Barbados")
    BELARUS = ("BLR", "Belarus")
    BELGIUM = ("BEL", "Belgium")
    BELIZE = ("BLZ", "Belize")
    BENIN = ("BEN", "Benin")
    BERMUDA = ("BMU", "Bermuda")
    BHUTAN = ("BTN", "Bhutan")
    BOLIVIA_PLURINATIONAL_STATE_OF = ("BOL", "Bolivia, Plurinational State of")
    BONAIRE_SINT_EUSTATIUS_AND_SABA = ("BES", "Bonaire, Sint Eustatius and Saba")
    BOSNIA_AND_HERZEGOVINA = ("BIH", "Bosnia and Herzegovina")
    BOTSWANA = ("BWA", "Botswana")
    BOUVET_ISLAND = ("BVT", "Bouvet Island")
    BRAZIL = ("BRA", "Brazil")
    BRITISH_INDIAN_OCEAN_TERRITORY = ("IOT", "British Indian Ocean Territory")
    BRUNEI_DARUSSALAM = ("BRN", "Brunei Darussalam")
    BULGARIA = ("BGR", "Bulgaria")
    BURKINA_FASO = ("BFA", "Burkina Faso")
    BURUNDI = ("BDI", "Burundi")
    CABO_VERDE = ("CPV", "Cabo Verde")
    CAMBODIA = ("KHM", "Cambodia")
    CAMEROON = ("CMR", "Cameroon")
    CANADA = ("CAN", "Canada")
    CAYMAN_ISLANDS = ("CYM", "Cayman Islands")
    CENTRAL_AFRICAN_REPUBLIC = ("CAF", "Central African Republic")
    CHAD = ("TCD", "Chad")
    CHILE = ("CHL", "Chile")
    CHINA = ("CHN", "China")
    CHRISTMAS_ISLAND = ("CXR", "Christmas Island")
    COCOS_KEELING_ISLANDS = ("CCK", "Cocos (Keeling) Islands")
    COLOMBIA = ("COL", "Colombia")
    COMOROS = ("COM", "Comoros")
    CONGO = ("COG", "Congo")
    CONGO_DEMOCRATIC_REPUBLIC_OF_THE = ("COD", "Congo, Democratic Republic of the")
    COOK_ISLANDS = ("COK", "Cook Islands")
    COSTA_RICA = ("CRI", "Costa Rica")
    COTE_D_IVOIRE = ("CIV", "Cote d'Ivoire")
    CROATIA = ("HRV", "Croatia")
    CUBA = ("CUB", "Cuba")
    CURACAO = ("CUW", "Curacao")
    CYPRUS = ("CYP", "Cyprus")
    CZECHIA = ("CZE", "Czechia")
    DENMARK = ("DNK", "Denmark")
    DJIBOUTI = ("DJI", "Djibouti")
    DOMINICA = ("DMA", "Dominica")
    DOMINICAN_REPUBLIC = ("DOM", "Dominican Republic")
    ECUADOR = ("ECU", "Ecuador")
    EGYPT = ("EGY", "Egypt")
    EL_SALVADOR = ("SLV", "El Salvador")
    EQUATORIAL_GUINEA = ("GNQ", "Equatorial Guinea")
    ERITREA = ("ERI", "Eritrea")
    ESTONIA = ("EST", "Estonia")
    ESWATINI = ("SWZ", "Eswatini")
    ETHIOPIA = ("ETH", "Ethiopia")
    FALKLAND_ISLANDS_MALVINAS = ("FLK", "Falkland Islands (Malvinas)")
    FAROE_ISLANDS = ("FRO", "Faroe Islands")
    FIJI = ("FJI", "Fiji")
    FINLAND = ("FIN", "Finland")
    FRANCE = ("FRA", "France")
    FRENCH_GUIANA = ("GUF", "French Guiana")
    FRENCH_POLYNESIA = ("PYF", "French Polynesia")
    FRENCH_SOUTHERN_TERRITORIES = ("ATF", "French Southern Territories")
    GABON = ("GAB", "Gabon")
    GAMBIA = ("GMB", "Gambia")
    GEORGIA = ("GEO", "Georgia")
    GERMANY = ("DEU", "Germany")
    GHANA = ("GHA", "Ghana")
    GIBRALTAR = ("GIB", "Gibraltar")
    GREECE = ("GRC", "Greece")
    GREENLAND = ("GRL", "Greenland")
    GRENADA = ("GRD", "Grenada")
    GUADELOUPE = ("GLP", "Guadeloupe")
    GUAM = ("GUM", "Guam")
    GUATEMALA = ("GTM", "Guatemala")
    GUERNSEY = ("GGY", "Guernsey")
    GUINEA = ("GIN", "Guinea")
    GUINEA_BISSAU = ("GNB", "Guinea-Bissau")
    GUYANA = ("GUY", "Guyana")
    HAITI = ("HTI", "Haiti")
    HEARD_ISLAND_AND_MCDONALD_ISLANDS = ("HMD", "Heard Island and McDonald Islands")
    HOLY_SEE = ("VAT", "Holy See")
    HONDURAS = ("HND", "Honduras")
    HONG_KONG = ("HKG", "Hong Kong")
    HUNGARY = ("HUN", "Hungary")
    ICELAND = ("ISL", "Iceland")
    INDIA = ("IND", "India")
    INDONESIA = ("IDN", "Indonesia")
    IRAN_ISLAMIC_REPUBLIC_OF = ("IRN", "Iran, Islamic Republic of")
    IRAQ = ("IRQ", "Iraq")
    IRELAND = ("IRL", "Ireland")
    ISLE_OF_MAN = ("IMN", "Isle of Man")
    ISRAEL = ("ISR", "Israel")
    ITALY = ("ITA", "Italy")
    JAMAICA = ("JAM", "Jamaica")
    JAPAN = ("JPN", "Japan")
    JERSEY = ("JEY", "Jersey")
    JORDAN = ("JOR", "Jordan")
    KAZAKHSTAN = ("KAZ", "Kazakhstan")
    KENYA = ("KEN", "Kenya")
    KIRIBATI = ("KIR", "Kiribati")
    KOREA_DEMOCRATIC_PEOPLE_S_REPUBLIC_OF = (
        "PRK",
        "Korea, Democratic People's Republic of",
    )
    KOREA_REPUBLIC_OF = ("KOR", "Korea, Republic of")
    KUWAIT = ("KWT", "Kuwait")
    KYRGYZSTAN = ("KGZ", "Kyrgyzstan")
    LAO_PEOPLE_S_DEMOCRATIC_REPUBLIC = ("LAO", "Lao People's Democratic Republic")
    LATVIA = ("LVA", "Latvia")
    LEBANON = ("LBN", "Lebanon")
    LESOTHO = ("LSO", "Lesotho")
    LIBERIA = ("LBR", "Liberia")
    LIBYA = ("LBY", "Libya")
    LIECHTENSTEIN = ("LIE", "Liechtenstein")
    LITHUANIA = ("LTU", "Lithuania")
    LUXEMBOURG = ("LUX", "Luxembourg")
    MACAO = ("MAC", "Macao")
    MADAGASCAR = ("MDG", "Madagascar")
    MALAWI = ("MWI", "Malawi")
    MALAYSIA = ("MYS", "Malaysia")
    MALDIVES = ("MDV", "Maldives")
    MALI = ("MLI", "Mali")
    MALTA = ("MLT", "Malta")
    MARSHALL_ISLANDS = ("MHL", "Marshall Islands")
    MARTINIQUE = ("MTQ", "Martinique")
    MAURITANIA = ("MRT", "Mauritania")
    MAURITIUS = ("MUS", "Mauritius")
    MAYOTTE = ("MYT", "Mayotte")
    MEXICO = ("MEX", "Mexico")
    MICRONESIA_FEDERATED_STATES_OF = ("FSM", "Micronesia, Federated States of")
    MOLDOVA_REPUBLIC_OF = ("MDA", "Moldova, Republic of")
    MONACO = ("MCO", "Monaco")
    MONGOLIA = ("MNG", "Mongolia")
    MONTENEGRO = ("MNE", "Montenegro")
    MONTSERRAT = ("MSR", "Montserrat")
    MOROCCO = ("MAR", "Morocco")
    MOZAMBIQUE = ("MOZ", "Mozambique")
    MYANMAR = ("MMR", "Myanmar")
    NAMIBIA = ("NAM", "Namibia")
    NAURU = ("NRU", "Nauru")
    NEPAL = ("NPL", "Nepal")
    NETHERLANDS_KINGDOM_OF_THE = ("NLD", "Netherlands, Kingdom of the")
    NEW_CALEDONIA = ("NCL", "New Caledonia")
    NEW_ZEALAND = ("NZL", "New Zealand")
    NICARAGUA = ("NIC", "Nicaragua")
    NIGER = ("NER", "Niger")
    NIGERIA = ("NGA", "Nigeria")
    NIUE = ("NIU", "Niue")
    NORFOLK_ISLAND = ("NFK", "Norfolk Island")
    NORTHERN_MARIANA_ISLANDS = ("MNP", "Northern Mariana Islands")
    NORTH_MACEDONIA = ("MKD", "North Macedonia")
    NORWAY = ("NOR", "Norway")
    OMAN = ("OMN", "Oman")
    PAKISTAN = ("PAK", "Pakistan")
    PALAU = ("PLW", "Palau")
    PALESTINE_STATE_OF = ("PSE", "Palestine, State of")
    PANAMA = ("PAN", "Panama")
    PAPUA_NEW_GUINEA = ("PNG", "Papua New Guinea")
    PARAGUAY = ("PRY", "Paraguay")
    PERU = ("PER", "Peru")
    PHILIPPINES = ("PHL", "Philippines")
    PITCAIRN = ("PCN", "Pitcairn")
    POLAND = ("POL", "Poland")
    PORTUGAL = ("PRT", "Portugal")
    PUERTO_RICO = ("PRI", "Puerto Rico")
    QATAR = ("QAT", "Qatar")
    REUNION = ("REU", "Reunion")
    ROMANIA = ("ROU", "Romania")
    RUSSIAN_FEDERATION = ("RUS", "Russian Federation")
    RWANDA = ("RWA", "Rwanda")
    SAINT_BARTHELEMY = ("BLM", "Saint Barthelemy")
    SAINT_HELENA_ASCENSION_AND_TRISTAN_DA_CUNHA = (
        "SHN",
        "Saint Helena, Ascension and Tristan da Cunha",
    )
    SAINT_KITTS_AND_NEVIS = ("KNA", "Saint Kitts and Nevis")
    SAINT_LUCIA = ("LCA", "Saint Lucia")
    SAINT_MARTIN_FRENCH_PART = ("MAF", "Saint Martin (French part)")
    SAINT_PIERRE_AND_MIQUELON = ("SPM", "Saint Pierre and Miquelon")
    SAINT_VINCENT_AND_THE_GRENADINES = ("VCT", "Saint Vincent and the Grenadines")
    SAMOA = ("WSM", "Samoa")
    SAN_MARINO = ("SMR", "San Marino")
    SAO_TOME_AND_PRINCIPE = ("STP", "Sao Tome and Principe")
    SAUDI_ARABIA = ("SAU", "Saudi Arabia")
    SENEGAL = ("SEN", "Senegal")
    SERBIA = ("SRB", "Serbia")
    SEYCHELLES = ("SYC", "Seychelles")
    SIERRA_LEONE = ("SLE", "Sierra Leone")
    SINGAPORE = ("SGP", "Singapore")
    SINT_MAARTEN_DUTCH_PART = ("SXM", "Sint Maarten (Dutch part)")
    SLOVAKIA = ("SVK", "Slovakia")
    SLOVENIA = ("SVN", "Slovenia")
    SOLOMON_ISLANDS = ("SLB", "Solomon Islands")
    SOMALIA = ("SOM", "Somalia")
    SOUTH_AFRICA = ("ZAF", "South Africa")
    SOUTH_GEORGIA_AND_THE_SOUTH_SANDWICH_ISLANDS = (
        "SGS",
        "South Georgia and the South Sandwich Islands",
    )
    SOUTH_SUDAN = ("SSD", "South Sudan")
    SPAIN = ("ESP", "Spain")
    SRI_LANKA = ("LKA", "Sri Lanka")
    SUDAN = ("SDN", "Sudan")
    SURINAME = ("SUR", "Suriname")
    SVALBARD_AND_JAN_MAYEN = ("SJM", "Svalbard and Jan Mayen")
    SWEDEN = ("SWE", "Sweden")
    SWITZERLAND = ("CHE", "Switzerland")
    SYRIAN_ARAB_REPUBLIC = ("SYR", "Syrian Arab Republic")
    TAIWAN_PROVINCE_OF_CHINA = ("TWN", "Taiwan, Province of China")
    TAJIKISTAN = ("TJK", "Tajikistan")
    TANZANIA_UNITED_REPUBLIC_OF = ("TZA", "Tanzania, United Republic of")
    THAILAND = ("THA", "Thailand")
    TIMOR_LESTE = ("TLS", "Timor-Leste")
    TOGO = ("TGO", "Togo")
    TOKELAU = ("TKL", "Tokelau")
    TONGA = ("TON", "Tonga")
    TRINIDAD_AND_TOBAGO = ("TTO", "Trinidad and Tobago")
    TUNISIA = ("TUN", "Tunisia")
    TURKIYE = ("TUR", "Türkiye")
    TURKMENISTAN = ("TKM", "Turkmenistan")
    TURKS_AND_CAICOS_ISLANDS = ("TCA", "Turks and Caicos Islands")
    TUVALU = ("TUV", "Tuvalu")
    UGANDA = ("UGA", "Uganda")
    UKRAINE = ("UKR", "Ukraine")
    UNITED_ARAB_EMIRATES = ("ARE", "United Arab Emirates")
    UNITED_KINGDOM_OF_GREAT_BRITAIN_AND_NORTHERN_IRELAND = (
        "GBR",
        "United Kingdom of Great Britain and Northern Ireland",
    )
    UNITED_STATES_MINOR_OUTLYING_ISLANDS = (
        "UMI",
        "United States Minor Outlying Islands",
    )
    UNITED_STATES_OF_AMERICA = ("USA", "United States of America")
    URUGUAY = ("URY", "Uruguay")
    UZBEKISTAN = ("UZB", "Uzbekistan")
    VANUATU = ("VUT", "Vanuatu")
    VENEZUELA_BOLIVARIAN_REPUBLIC_OF = ("VEN", "Venezuela, Bolivarian Republic of")
    VIET_NAM = ("VNM", "Viet Nam")
    VIRGIN_ISLANDS_BRITISH = ("VGB", "Virgin Islands (British)")
    VIRGIN_ISLANDS_U_S = ("VIR", "Virgin Islands (U.S.)")
    WALLIS_AND_FUTUNA = ("WLF", "Wallis and Futuna")
    WESTERN_SAHARA = ("ESH", "Western Sahara")
    YEMEN = ("YEM", "Yemen")
    LUATOPIA = ("LUA", "Luatopia")
    ZAMBIA = ("ZMB", "Zambia")
    ZIMBABWE = ("ZWE", "Zimbabwe")


COUNTRY_NAME_BY_ALPHA3 = {member.value: member.label for member in CountryISOAlpha3}


class Region(str, Enum):
    """World Bank regional classifications plus Global."""

    AFR = "AFR"  # Africa
    EAP = "EAP"  # East Asia & Pacific
    ECA = "ECA"  # Europe & Central Asia
    LAC = "LAC"  # Latin America and the Caribbean
    MNA = "MNA"  # Middle East, North Africa, Afghanistan & Pakistan
    SAR = "SAR"  # South Asia
    GLO = "GLO"  # Global (applies to all countries)


REGION_BY_COUNTRY_ALPHA3: dict[str, Region] = {
    # Africa (AFR)
    "AGO": Region.AFR,  # Angola
    "BFA": Region.AFR,  # Burkina Faso
    "CMR": Region.AFR,  # Cameroon
    "COM": Region.AFR,  # Comoros
    "COD": Region.AFR,  # Congo, Democratic Republic of
    "SWZ": Region.AFR,  # Eswatini
    "GMB": Region.AFR,  # Gambia
    "GNB": Region.AFR,  # Guinea-Bissau
    "LBR": Region.AFR,  # Liberia
    "MLI": Region.AFR,  # Mali
    "MOZ": Region.AFR,  # Mozambique
    "NGA": Region.AFR,  # Nigeria
    "SEN": Region.AFR,  # Senegal
    "SOM": Region.AFR,  # Somalia, Federal Republic of
    "SDN": Region.AFR,  # Sudan
    "UGA": Region.AFR,  # Uganda
    "BEN": Region.AFR,  # Benin
    "BDI": Region.AFR,  # Burundi
    "CAF": Region.AFR,  # Central African Republic
    "CIV": Region.AFR,  # Cote d'Ivoire
    "GNQ": Region.AFR,  # Equatorial Guinea
    "ETH": Region.AFR,  # Ethiopia
    "GHA": Region.AFR,  # Ghana
    "KEN": Region.AFR,  # Kenya
    "MDG": Region.AFR,  # Madagascar
    "MRT": Region.AFR,  # Mauritania
    "NAM": Region.AFR,  # Namibia
    "RWA": Region.AFR,  # Rwanda
    "SYC": Region.AFR,  # Seychelles
    "ZAF": Region.AFR,  # South Africa
    "TZA": Region.AFR,  # Tanzania
    "ZMB": Region.AFR,  # Zambia
    "BWA": Region.AFR,  # Botswana
    "CPV": Region.AFR,  # Cabo Verde
    "TCD": Region.AFR,  # Chad
    "COG": Region.AFR,  # Congo, Republic of
    "ERI": Region.AFR,  # Eritrea
    "GAB": Region.AFR,  # Gabon
    "GIN": Region.AFR,  # Guinea
    "LSO": Region.AFR,  # Lesotho
    "MWI": Region.AFR,  # Malawi
    "MUS": Region.AFR,  # Mauritius
    "NER": Region.AFR,  # Niger
    "STP": Region.AFR,  # Sao Tome & Principe
    "SLE": Region.AFR,  # Sierra Leone
    "SSD": Region.AFR,  # South Sudan
    "TGO": Region.AFR,  # Togo
    "ZWE": Region.AFR,  # Zimbabwe
    # East Asia & Pacific (EAP)
    "KHM": Region.EAP,  # Cambodia
    "KOR": Region.EAP,  # Korea
    "MNG": Region.EAP,  # Mongolia
    "PHL": Region.EAP,  # Philippines
    "TLS": Region.EAP,  # Timor-Leste
    "CHN": Region.EAP,  # China
    "LAO": Region.EAP,  # Lao PDR
    "MMR": Region.EAP,  # Myanmar
    "SGP": Region.EAP,  # Singapore
    "VNM": Region.EAP,  # Viet Nam
    "IDN": Region.EAP,  # Indonesia
    "MYS": Region.EAP,  # Malaysia
    "PNG": Region.EAP,  # Papua New Guinea
    "THA": Region.EAP,  # Thailand
    # Europe & Central Asia (ECA)
    "ALB": Region.ECA,  # Albania
    "BLR": Region.ECA,  # Belarus
    "HRV": Region.ECA,  # Croatia
    "XKX": Region.ECA,  # Kosovo
    "MNE": Region.ECA,  # Montenegro
    "ROU": Region.ECA,  # Romania
    "TJK": Region.ECA,  # Tajikistan
    "UKR": Region.ECA,  # Ukraine
    "ARM": Region.ECA,  # Armenia
    "BIH": Region.ECA,  # Bosnia and Herzegovina
    "GEO": Region.ECA,  # Georgia
    "KGZ": Region.ECA,  # Kyrgyz Republic
    "MKD": Region.ECA,  # North Macedonia
    "RUS": Region.ECA,  # Russian Federation
    "TUR": Region.ECA,  # Türkiye
    "UZB": Region.ECA,  # Uzbekistan
    "AZE": Region.ECA,  # Azerbaijan
    "BGR": Region.ECA,  # Bulgaria
    "KAZ": Region.ECA,  # Kazakhstan
    "MDA": Region.ECA,  # Moldova
    "POL": Region.ECA,  # Poland
    "SRB": Region.ECA,  # Serbia
    "TKM": Region.ECA,  # Turkmenistan
    # Latin America and the Caribbean (LAC)
    "ARG": Region.LAC,  # Argentina
    "COL": Region.LAC,  # Colombia
    "DOM": Region.LAC,  # Dominican Republic
    "GTM": Region.LAC,  # Guatemala
    "JAM": Region.LAC,  # Jamaica
    "PAN": Region.LAC,  # Panama
    "SXM": Region.LAC,  # Sint Maarten
    "VEN": Region.LAC,  # Venezuela
    "BOL": Region.LAC,  # Bolivia
    "CHL": Region.LAC,  # Chile
    "ECU": Region.LAC,  # Ecuador
    "HTI": Region.LAC,  # Haiti
    "MEX": Region.LAC,  # Mexico
    "PRY": Region.LAC,  # Paraguay
    "SUR": Region.LAC,  # Suriname
    "BRA": Region.LAC,  # Brazil
    "CRI": Region.LAC,  # Costa Rica
    "SLV": Region.LAC,  # El Salvador
    "HND": Region.LAC,  # Honduras
    "NIC": Region.LAC,  # Nicaragua
    "PER": Region.LAC,  # Peru
    "URY": Region.LAC,  # Uruguay
    # Middle East, North Africa, Afghanistan & Pakistan (MNA)
    "AFG": Region.MNA,  # Afghanistan
    "EGY": Region.MNA,  # Egypt
    "JOR": Region.MNA,  # Jordan
    "MAR": Region.MNA,  # Morocco
    "SYR": Region.MNA,  # Syria
    "YEM": Region.MNA,  # Yemen
    "DZA": Region.MNA,  # Algeria
    "IRN": Region.MNA,  # Iran
    "LBN": Region.MNA,  # Lebanon
    "PAK": Region.MNA,  # Pakistan
    "TUN": Region.MNA,  # Tunisia
    "DJI": Region.MNA,  # Djibouti
    "IRQ": Region.MNA,  # Iraq
    "LBY": Region.MNA,  # Libya
    "SAU": Region.MNA,  # Saudi Arabia
    "PSE": Region.MNA,  # West Bank and Gaza
    # South Asia (SAR)
    "IND": Region.SAR,  # India
    "BGD": Region.SAR,  # Bangladesh
    "MDV": Region.SAR,  # Maldives
    "LKA": Region.SAR,  # Sri Lanka
    "BTN": Region.SAR,  # Bhutan
    "NPL": Region.SAR,  # Nepal
}
