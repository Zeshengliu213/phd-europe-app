"""Keyword-based subject classification for PhD postings.

Each job gets 1–3 tags from a fixed taxonomy. Matches on title + first chunk of
description_html (stripped). Designed to be deterministic and fast (pure regex).
"""
from __future__ import annotations

import re

TAXONOMY: list[tuple[str, list[str]]] = [
    ("AI & Machine Learning", [
        r"\bmachine learning\b", r"\bdeep learning\b", r"\bneural network", r"\bartificial intelligence\b",
        r"\b(LLM|large language model)s?\b", r"\bgenerative AI\b", r"\breinforcement learning\b",
        r"\bcomputer vision\b", r"\bNLP\b", r"\bnatural language processing\b", r"\btransformer",
        r"\bdata[- ]driven\b", r"\b AI\b", r"\bML\b",
        r"\bkunstig intelligens\b", r"\bmaskinl[æa]ring\b", r"\bdataanalyse\b", r"\bKI[- ]",
        r"\bdatadriven\b",
    ]),
    ("Computer Science", [
        r"\bcomputer science\b", r"\bsoftware engineering\b", r"\bcybersecurity\b", r"\bcyber[- ]?security\b",
        r"\bcryptograph", r"\bdistributed system", r"\bdatabase", r"\bHCI\b", r"\bhuman[- ]computer",
        r"\bcompilers?\b", r"\balgorithm", r"\bprogramming language", r"\bformal method",
        r"\bquantum comput", r"\bblockchain\b",
    ]),
    ("Robotics & Autonomous Systems", [
        r"\brobotic", r"\bautonomous system", r"\bdrone", r"\bUAV", r"\bself[- ]driving",
        r"\bmanipulation\b", r"\bmulti[- ]?agent\b", r"\bcontrol system",
    ]),
    ("Mathematics & Statistics", [
        r"\bmathematic", r"\bstatistic", r"\bprobability\b", r"\bstochastic\b",
        r"\bbiostatistic", r"\bnumerical (analysis|methods)\b", r"\boptimi[sz]ation\b",
        r"\bgeometry\b", r"\btopology\b",
        r"\bmatematikk?\b", r"\bstatistikk?\b", r"\bmatematisk\b", r"\banvendt matematikk\b",
        r"\bberegning", r"\bberekning", r"\boptimalisering\b",
    ]),
    ("Physics & Astronomy", [
        r"\bphysics\b", r"\bastronom", r"\bastrophys", r"\bcosmolog", r"\bquantum\b",
        r"\bparticle physic", r"\bcondensed matter\b", r"\bphotonic", r"\boptic",
        r"\bplasma\b", r"\bfluid (mechanics|dynamics)\b", r"\bspace physic",
        r"\bfysikk?\b", r"\bromfysikk\b", r"\bkvante", r"\bfluidmekanikk\b",
        r"\bakustisk\b", r"\batomfysikk\b",
    ]),
    ("Chemistry", [
        r"\bchemistry\b", r"\bchemical\b", r"\bcataly", r"\belectrochem", r"\bphotochem",
        r"\borganic synthesis\b", r"\binorganic\b", r"\bpolymer", r"\bproteomic",
        r"\bkjemi\b", r"\borganisk (kjemi|syntese)\b", r"\bmedisinalkjemi\b",
        r"\bradiokjemi\b", r"\borganometallisk\b",
    ]),
    ("Biology & Life Sciences", [
        r"\bbiolog", r"\bmicrobiolog", r"\bmolecular biology\b", r"\bcell biology\b",
        r"\bgenet", r"\becolog", r"\bzoolog", r"\bbotan", r"\bneuroscien", r"\bbioinformatic",
        r"\bgenom", r"\bprotein\b", r"\bstem cell", r"\bimmun", r"\bvirolog", r"\bbiochem",
        r"\bbiophys", r"\bplant (science|physiology)\b", r"\bhologenom",
        r"\bmikrobiolog", r"\bmolekyl[æa]r\b", r"\bberekningsbiologi\b", r"\bzooplankton\b",
    ]),
    ("Medicine & Health", [
        r"\bmedicine\b", r"\bmedical\b", r"\bclinical\b", r"\bcancer\b", r"\boncolog",
        r"\bepidemiolog", r"\bpharmaceutic", r"\bpharmacolog", r"\bpharmacy\b",
        r"\bpublic health\b", r"\bhealth(care)?\b", r"\bpathology\b", r"\bpsychiatr",
        r"\bnursing\b", r"\bveterinary\b", r"\bdental\b", r"\btoxicolog",
        r"\bmedisin\b", r"\bklinisk\b", r"\bhelse\b", r"\bkreft", r"\bapotek",
        r"\bprehospital\b", r"\btreningsfysiolog", r"\bhelsetjeneste",
        r"\bpsykisk helse\b", r"\bfarmas", r"\bhelseledelse\b",
    ]),
    ("Engineering", [
        r"\belectrical engineering\b", r"\bmechanical engineering\b", r"\bcivil engineering\b",
        r"\bchemical engineering\b", r"\bmaterials science\b", r"\bmaterials engineering\b",
        r"\bbiomedical engineering\b", r"\bindustrial engineering\b", r"\bmanufacturing\b",
        r"\bsensor\b", r"\bsignal processing\b", r"\bwireless\b", r"\btelecommunic",
        r"\bconstruction\b", r"\bmarine technology\b", r"\bstructural\b",
        r"\bpower electronic", r"\belectronics?\b",
        r"\bteknologi\b", r"\bteknikk?\b", r"\bkonstruksjon", r"\bsystems engineering\b",
        r"\bindustriell\b", r"\bbrønnteknolog", r"\bkraftnett", r"\bbroinfrastruktur",
        r"\bstålkonstruk",
    ]),
    ("Energy & Environment", [
        r"\benergy\b", r"\brenewable", r"\bsolar (cell|panel|energy)\b", r"\bwind (energy|turbine|power)\b",
        r"\bgeothermal\b", r"\bhydrogen\b", r"\bbattery\b", r"\bclimate\b", r"\bcarbon\b",
        r"\bemission", r"\bsustainab", r"\bdecarboni[sz]", r"\bgreen\b",
        r"\benergi\b", r"\bvindenergi\b", r"\bgeotermisk\b", r"\bhydrogen\b",
        r"\bklima\b", r"\bblått hydrogen\b", r"\bphotovoltaic",
    ]),
    ("Earth & Environmental Science", [
        r"\bgeoscien", r"\bgeolog", r"\bgeophys", r"\boceanograph", r"\batmospher",
        r"\benvironmental scien", r"\bhydrolog", r"\bpaleo", r"\bglaciolog", r"\bseismolog",
        r"\bmeteorolog", r"\becotoxicolog", r"\bsoil\b", r"\bforest",
        r"\bgeovitenskap\b", r"\boseanograf", r"\bvulkan", r"\bgeodynamikk\b",
        r"\bpaleoseanograf", r"\bpaleoklimat", r"\bfysisk oseanograf",
    ]),
    ("Agriculture & Food", [
        r"\bagricult", r"\bfood (science|microbiology|safety|systems)\b", r"\baquacultur",
        r"\banimal (science|welfare|husband|production)\b", r"\bcrop\b", r"\blivestock\b",
        r"\bhorticultur", r"\bfishery\b", r"\bnutrition\b",
        r"\bmatberedskap\b", r"\bvillrein\b", r"\bnaturforvaltning\b",
    ]),
    ("Social Sciences", [
        r"\bsociolog", r"\banthropolog", r"\bpolitical scien", r"\bpsycholog",
        r"\bcriminolog", r"\bhuman geograph", r"\bsocial work\b", r"\bgender stud",
        r"\bdemograph", r"\bmigration\b",
        r"\bsosiolog", r"\bantropolog", r"\bsamfunns(sikkerhet|fag)", r"\bsosialt arbeid",
        r"\brisikostyring\b", r"\bbarnevern",
    ]),
    ("Economics & Business", [
        r"\beconomic", r"\bfinance\b", r"\bmanagement\b", r"\bbusiness\b",
        r"\bmarketing\b", r"\baccounting\b", r"\bentrepreneur",
        r"\bbedriftsøkonomi\b", r"\bledelse\b", r"\brevisjon\b", r"\bverdikjeder\b",
        r"\binnovasjon\b", r"\bentreprenør", r"\btjenesteinnovasjon\b",
    ]),
    ("Law", [
        r"\blaw\b", r"\blegal\b", r"\bjurisprudence\b", r"\brettsvitenskap\b",
        r"\bjuridisk\b",
    ]),
    ("Education", [
        r"\beducation research\b", r"\beducational (psychology|research|science)",
        r"\bspecial needs education\b", r"\bhigher education research\b",
        r"\bpedagog", r"\bdidactic", r"\blearning scien",
        r"\bteacher (education|training)\b",
        r"\bpedagogikk\b", r"\bdidaktikk?\b", r"\bmusikkpedagogikk\b",
        r"\bfagdidaktikk\b", r"\bfagspråk\b",
    ]),
    ("Humanities", [
        r"\bhistory\b", r"\bphilosoph", r"\blinguistic", r"\bliteratur", r"\barchaeolog",
        r"\bmusic\b", r"\bart history\b", r"\btheolog", r"\bcultural (studies|heritage)\b",
        r"\bhuman rights\b",
        r"\bhistorie\b", r"\bfilosofi\b", r"\bspråk\b", r"\barkeolog", r"\bmusikk\b",
        r"\bkulturarv", r"\bvitskapsteori\b", r"\bkunstnerisk\b", r"\bpersonnamn",
        r"\bflerspråklighet\b", r"\bukrainsk\b",
    ]),
]

_COMPILED: list[tuple[str, list[re.Pattern]]] = [
    (name, [re.compile(p, re.I) for p in patterns]) for name, patterns in TAXONOMY
]

_TAG_STRIP = re.compile(r"<[^>]+>")
_MAX_TAGS = 3


def _strip_html(s: str, limit: int = 2500) -> str:
    return _TAG_STRIP.sub(" ", s or "")[:limit]


def classify(title: str, description_html: str = "") -> list[str]:
    haystack = f"{title}\n{_strip_html(description_html)}"
    scored: list[tuple[int, str]] = []
    for name, patterns in _COMPILED:
        hits = sum(1 for p in patterns if p.search(haystack))
        if hits:
            scored.append((hits, name))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [name for _, name in scored[:_MAX_TAGS]]


def classify_job(job: dict) -> dict:
    if job.get("research_fields"):
        return job
    job["research_fields"] = classify(job.get("title", ""), job.get("description_html", ""))
    return job
