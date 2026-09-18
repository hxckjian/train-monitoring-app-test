"""Singapore MRT network reference: station codes per line, in running order.

DataMall's TrainServiceAlerts (`Stations`: "NS1,NS2,...") and the real-time
Platform Crowd Density feed (`Station`: "NS1") both speak in station codes, and
the PS2 GeoJSON speaks in names. This table joins them. Branches are listed
separately so a drawn path never jumps across the island.
"""
from __future__ import annotations

LINE_NAME = {"NSL": "North–South", "EWL": "East–West", "NEL": "North East",
             "CCL": "Circle", "DTL": "Downtown", "TEL": "Thomson–East Coast"}
LINE_HEX = {"NSL": "#d42e12", "EWL": "#009645", "NEL": "#9900aa",
            "CCL": "#fa9e0d", "DTL": "#005ec4", "TEL": "#9d5b25"}

# (code, name) in running order; each inner list is one drawable path.
SEGMENTS: dict[str, list[list[tuple[str, str]]]] = {
    "NSL": [[("NS1", "JURONG EAST"), ("NS2", "BUKIT BATOK"), ("NS3", "BUKIT GOMBAK"), ("NS4", "CHOA CHU KANG"),
             ("NS5", "YEW TEE"), ("NS7", "KRANJI"), ("NS8", "MARSILING"), ("NS9", "WOODLANDS"), ("NS10", "ADMIRALTY"),
             ("NS11", "SEMBAWANG"), ("NS12", "CANBERRA"), ("NS13", "YISHUN"), ("NS14", "KHATIB"), ("NS15", "YIO CHU KANG"),
             ("NS16", "ANG MO KIO"), ("NS17", "BISHAN"), ("NS18", "BRADDELL"), ("NS19", "TOA PAYOH"), ("NS20", "NOVENA"),
             ("NS21", "NEWTON"), ("NS22", "ORCHARD"), ("NS23", "SOMERSET"), ("NS24", "DHOBY GHAUT"), ("NS25", "CITY HALL"),
             ("NS26", "RAFFLES PLACE"), ("NS27", "MARINA BAY"), ("NS28", "MARINA SOUTH PIER")]],
    "EWL": [[("EW1", "PASIR RIS"), ("EW2", "TAMPINES"), ("EW3", "SIMEI"), ("EW4", "TANAH MERAH"), ("EW5", "BEDOK"),
             ("EW6", "KEMBANGAN"), ("EW7", "EUNOS"), ("EW8", "PAYA LEBAR"), ("EW9", "ALJUNIED"), ("EW10", "KALLANG"),
             ("EW11", "LAVENDER"), ("EW12", "BUGIS"), ("EW13", "CITY HALL"), ("EW14", "RAFFLES PLACE"),
             ("EW15", "TANJONG PAGAR"), ("EW16", "OUTRAM PARK"), ("EW17", "TIONG BAHRU"), ("EW18", "REDHILL"),
             ("EW19", "QUEENSTOWN"), ("EW20", "COMMONWEALTH"), ("EW21", "BUONA VISTA"), ("EW22", "DOVER"),
             ("EW23", "CLEMENTI"), ("EW24", "JURONG EAST"), ("EW25", "CHINESE GARDEN"), ("EW26", "LAKESIDE"),
             ("EW27", "BOON LAY"), ("EW28", "PIONEER"), ("EW29", "JOO KOON"), ("EW30", "GUL CIRCLE"),
             ("EW31", "TUAS CRESCENT"), ("EW32", "TUAS WEST ROAD"), ("EW33", "TUAS LINK")],
            [("EW4", "TANAH MERAH"), ("CG1", "EXPO"), ("CG2", "CHANGI AIRPORT")]],
    "NEL": [[("NE1", "HARBOURFRONT"), ("NE3", "OUTRAM PARK"), ("NE4", "CHINATOWN"), ("NE5", "CLARKE QUAY"),
             ("NE6", "DHOBY GHAUT"), ("NE7", "LITTLE INDIA"), ("NE8", "FARRER PARK"), ("NE9", "BOON KENG"),
             ("NE10", "POTONG PASIR"), ("NE11", "WOODLEIGH"), ("NE12", "SERANGOON"), ("NE13", "KOVAN"),
             ("NE14", "HOUGANG"), ("NE15", "BUANGKOK"), ("NE16", "SENGKANG"), ("NE17", "PUNGGOL")]],
    "CCL": [[("CC1", "DHOBY GHAUT"), ("CC2", "BRAS BASAH"), ("CC3", "ESPLANADE"), ("CC4", "PROMENADE"),
             ("CC5", "NICOLL HIGHWAY"), ("CC6", "STADIUM"), ("CC7", "MOUNTBATTEN"), ("CC8", "DAKOTA"),
             ("CC9", "PAYA LEBAR"), ("CC10", "MACPHERSON"), ("CC11", "TAI SENG"), ("CC12", "BARTLEY"),
             ("CC13", "SERANGOON"), ("CC14", "LORONG CHUAN"), ("CC15", "BISHAN"), ("CC16", "MARYMOUNT"),
             ("CC17", "CALDECOTT"), ("CC19", "BOTANIC GARDENS"), ("CC20", "FARRER ROAD"), ("CC21", "HOLLAND VILLAGE"),
             ("CC22", "BUONA VISTA"), ("CC23", "ONE NORTH"), ("CC24", "KENT RIDGE"), ("CC25", "HAW PAR VILLA"),
             ("CC26", "PASIR PANJANG"), ("CC27", "LABRADOR PARK"), ("CC28", "TELOK BLANGAH"), ("CC29", "HARBOURFRONT")],
            [("CC4", "PROMENADE"), ("CE1", "BAYFRONT"), ("CE2", "MARINA BAY")]],
    "DTL": [[("DT1", "BUKIT PANJANG"), ("DT2", "CASHEW"), ("DT3", "HILLVIEW"), ("DT4", "HUME"), ("DT5", "BEAUTY WORLD"),
             ("DT6", "KING ALBERT PARK"), ("DT7", "SIXTH AVENUE"), ("DT8", "TAN KAH KEE"), ("DT9", "BOTANIC GARDENS"),
             ("DT10", "STEVENS"), ("DT11", "NEWTON"), ("DT12", "LITTLE INDIA"), ("DT13", "ROCHOR"), ("DT14", "BUGIS"),
             ("DT15", "PROMENADE"), ("DT16", "BAYFRONT"), ("DT17", "DOWNTOWN"), ("DT18", "TELOK AYER"),
             ("DT19", "CHINATOWN"), ("DT20", "FORT CANNING"), ("DT21", "BENCOOLEN"), ("DT22", "JALAN BESAR"),
             ("DT23", "BENDEMEER"), ("DT24", "GEYLANG BAHRU"), ("DT25", "MATTAR"), ("DT26", "MACPHERSON"),
             ("DT27", "UBI"), ("DT28", "KAKI BUKIT"), ("DT29", "BEDOK NORTH"), ("DT30", "BEDOK RESERVOIR"),
             ("DT31", "TAMPINES WEST"), ("DT32", "TAMPINES"), ("DT33", "TAMPINES EAST"), ("DT34", "UPPER CHANGI"),
             ("DT35", "EXPO")]],
    "TEL": [[("TE1", "WOODLANDS NORTH"), ("TE2", "WOODLANDS"), ("TE3", "WOODLANDS SOUTH"), ("TE4", "SPRINGLEAF"),
             ("TE5", "LENTOR"), ("TE6", "MAYFLOWER"), ("TE7", "BRIGHT HILL"), ("TE8", "UPPER THOMSON"),
             ("TE9", "CALDECOTT"), ("TE11", "STEVENS"), ("TE12", "NAPIER"), ("TE13", "ORCHARD BOULEVARD"),
             ("TE14", "ORCHARD"), ("TE15", "GREAT WORLD"), ("TE16", "HAVELOCK"), ("TE17", "OUTRAM PARK"),
             ("TE18", "MAXWELL"), ("TE19", "SHENTON WAY"), ("TE20", "MARINA BAY"), ("TE22", "GARDENS BY THE BAY"),
             ("TE23", "TANJONG RHU"), ("TE24", "KATONG PARK"), ("TE25", "TANJONG KATONG"), ("TE26", "MARINE PARADE"),
             ("TE27", "MARINE TERRACE"), ("TE28", "SIGLAP"), ("TE29", "BAYSHORE")]],
}

CODE_TO_NAME: dict[str, str] = {code: name for segs in SEGMENTS.values() for seg in segs for code, name in seg}
NAME_TO_CODES: dict[str, list[str]] = {}
for _code, _name in CODE_TO_NAME.items():
    NAME_TO_CODES.setdefault(_name, []).append(_code)


def stations_of(line: str) -> list[str]:
    """Unique station names on a line, running order, branches appended."""
    seen, out = set(), []
    for seg in SEGMENTS.get(line, []):
        for _, name in seg:
            if name not in seen:
                seen.add(name)
                out.append(name)
    return out


def line_of_code(code: str) -> str | None:
    prefix = "".join(ch for ch in code if ch.isalpha())
    return {"NS": "NSL", "EW": "EWL", "CG": "EWL", "NE": "NEL", "CC": "CCL", "CE": "CCL",
            "DT": "DTL", "TE": "TEL"}.get(prefix)


def codes_to_names(codes: str | list[str]) -> list[str]:
    items = codes.split(",") if isinstance(codes, str) else list(codes)
    return [CODE_TO_NAME[c.strip()] for c in items if c.strip() in CODE_TO_NAME]
